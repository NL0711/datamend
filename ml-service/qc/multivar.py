"""Temperature, relative humidity and pressure on the ERA5 daily fields: untrained and lightly fitted experts, a
cross-variable consistency expert, a small fusion, and a synthetic-fault validation. A separate path from the rainfall
pipeline (which stays rain-specific: zero-inflated Gamma head, protected extremes, RF25 client map).

Per variable (``VARIABLES``) there is one expert: the largest of four rule scores, each divided by its own reference:
  anomaly   |x - climatology(day of year)| / climatological sd      reference: 99.9th percentile on clean threshold years
  step      |x_t - x_(t-1)| / the cell's day-to-day sd              reference: 99.9th percentile on clean threshold years
  bound     distance outside the physical range / day-to-day sd     reference: 1 (any exceedance)
  stuck     number of exactly repeated values in a row              reference: 2 (three equal days in a row)
Plus ONE cross-variable consistency expert: the Mahalanobis distance of the day's standardized anomaly vector
(temperature, humidity, pressure) under a covariance fitted on training years, pooled over cells.
The fusion is a logistic regression on log1p of the expert scores, fitted on synthetic faults of the fusion-fit
years. Climatology, day-to-day sd, covariance and references use training or threshold years only.

Neighbour regression experts (``fit_gbm``, on by default): per variable, a gradient-boosted regressor predicts the cell's anomaly
from its neighbours, its own last two days, the neighbours' other variables, season and position (never the cell's own
current value, nor its other variables); the score is the residual over its robust spread. CPU only, minutes to train.

Synthetic faults (``inject``): spike, stuck, drift, amplitude error ("scale"), single cell, one variable at a time,
values clipped to the physical range so the bound rule is not trivially perfect. Not frozen or hashed.

NOT IMPLEMENTED here (listed in every output): footprint faults of more than one cell, spatial
footprint faults, per-variable false-removal protection for genuine extremes (the rain "protected extreme" idea has no
counterpart yet for heat waves or cold spells), the federated variants, and a frozen benchmark with a single-use test
pass. ERA5 is modelled, not measured, so every recall here is optimistic relative to real station faults.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.ndimage import uniform_filter1d
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression

from qc.era5 import Era5Daily
from qc.metrics import budget_thresholds
from qc.runs import write_json

log = logging.getLogger(__name__)
KINDS = ("spike", "stuck", "drift", "scale")
LIMITS = [
    "ERA5 is a reanalysis (modelled), not a measurement: injected faults are easier to detect than real sensor faults.",
    "Synthetic faults only; no real labels exist. Faults are single-cell, one variable at a time, and the benchmark is not frozen.",
    "NOT IMPLEMENTED: footprint faults of more than one cell, protection of genuine extremes (heat waves, cold spells), "
    "federated variants, a single-use test pass.",
    "Consistency covariance is pooled over all cells; regional differences in the relationship are not modelled.",
]


@dataclass(frozen=True)
class VarSpec:
    key: str
    field: str          # daily variable name in ERA5D files
    units: str
    lo: float           # physical plausibility range of a daily mean (generous)
    hi: float


VARIABLES: Dict[str, VarSpec] = {
    "temperature": VarSpec("temperature", "TEMP_MEAN", "degC", -60.0, 65.0),
    "humidity": VarSpec("humidity", "RH_MEAN", "%", 0.0, 100.0),
    "pressure": VarSpec("pressure", "PRES_MEAN", "hPa", 450.0, 1090.0),   # high plateau surface pressure is near 500 hPa
}
NAMES = tuple(VARIABLES)


# ---------------------------------------------------------------------------------------------- statistics

@dataclass
class Stats:
    mean: Dict[str, np.ndarray]       # (366, H, W)
    sd: Dict[str, np.ndarray]         # (366, H, W)
    step_sd: Dict[str, np.ndarray]    # (H, W)
    cov: np.ndarray                   # (3, 3) of standardized anomalies
    years: List[int]


def _fields(data: Era5Daily, year: int) -> Dict[str, np.ndarray]:
    return {n: data.year(year, v.field) for n, v in VARIABLES.items()}


def fit_stats(data: Era5Daily, years: Sequence[int]) -> Stats:
    """Climatology, day-to-day sd and anomaly covariance from ``years`` (training years), one year in memory at a time."""
    H, W = data.grid(years[0])[0].size, data.grid(years[0])[1].size
    s1 = {n: np.zeros((366, H, W)) for n in NAMES}
    s2 = {n: np.zeros((366, H, W)) for n in NAMES}
    cn = {n: np.zeros((366, H, W)) for n in NAMES}
    d2 = {n: np.zeros((H, W)) for n in NAMES}
    dn = {n: np.zeros((H, W)) for n in NAMES}
    for y in years:
        for n, x in _fields(data, y).items():
            T, ok = x.shape[0], np.isfinite(x)
            xz = np.where(ok, x, 0.0).astype(np.float64)
            s1[n][:T] += xz; s2[n][:T] += xz ** 2; cn[n][:T] += ok
            dd = np.diff(x, axis=0)
            fd = np.isfinite(dd)
            d2[n] += (np.where(fd, dd, 0.0).astype(np.float64) ** 2).sum(0)
            dn[n] += fd.sum(0)
    mean, sd, step = {}, {}, {}
    for n in NAMES:
        with np.errstate(invalid="ignore", divide="ignore"):
            m = s1[n] / cn[n]
            v = np.maximum(s2[n] / cn[n] - m ** 2, 0.0)
        for arr in (m, v):
            miss = cn[n][365] == 0
            arr[365] = np.where(miss, arr[364], arr[365])
        mean[n] = uniform_filter1d(np.nan_to_num(m), size=15, axis=0, mode="wrap").astype(np.float32)
        sd[n] = np.maximum(np.sqrt(uniform_filter1d(np.nan_to_num(v), size=15, axis=0, mode="wrap")), 1e-3).astype(np.float32)
        with np.errstate(invalid="ignore", divide="ignore"):
            step[n] = np.maximum(np.sqrt(d2[n] / np.maximum(dn[n], 1)), 1e-3).astype(np.float32)
    st = Stats(mean, sd, step, np.eye(3), list(years))
    acc, tot = np.zeros((3, 3)), 0.0
    for y in years:
        a = anomalies(st, _fields(data, y))
        ok = np.all([np.isfinite(a[n]) for n in NAMES], axis=0)
        mat = np.stack([a[n][ok] for n in NAMES], axis=1).astype(np.float64)
        acc += mat.T @ mat; tot += mat.shape[0]
    st.cov = acc / max(tot, 1.0) + 1e-6 * np.eye(3)
    return st


def anomalies(st: Stats, fields: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    out = {}
    for n, x in fields.items():
        T = x.shape[0]
        out[n] = (x - st.mean[n][:T]) / st.sd[n][:T]
    return out


# ---------------------------------------------------------------------------------------------- experts

def _parts(x: np.ndarray, n: str, st: Stats) -> Dict[str, np.ndarray]:
    spec, T = VARIABLES[n], x.shape[0]
    z = np.abs(x - st.mean[n][:T]) / st.sd[n][:T]
    step = np.zeros_like(x)
    step[1:] = np.abs(x[1:] - x[:-1]) / st.step_sd[n]
    bound = np.maximum(np.maximum(spec.lo - x, x - spec.hi), 0.0) / st.step_sd[n]
    run = np.zeros_like(x)
    for t in range(1, T):
        run[t] = np.where(x[t] == x[t - 1], run[t - 1] + 1.0, 0.0)
    return {"anomaly": z, "step": step, "bound": bound, "stuck": run}


@dataclass
class Experts:
    st: Stats
    ref: Dict[str, Dict[str, float]]       # variable -> rule -> reference

    def scores(self, fields: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        out = {}
        for n in NAMES:
            parts = _parts(fields[n], n, self.st)
            norm = [np.nan_to_num(parts[k] / self.ref[n][k], nan=0.0) for k in parts]
            out[n] = np.where(np.isfinite(fields[n]), np.max(norm, axis=0), np.nan).astype(np.float32)
        a = anomalies(self.st, fields)
        vec = np.stack([a[n] for n in NAMES], axis=-1)
        ok = np.isfinite(vec).all(axis=-1)
        inv = np.linalg.inv(self.st.cov)
        d2 = np.einsum("...i,ij,...j->...", np.nan_to_num(vec), inv, np.nan_to_num(vec))
        out["consistency"] = np.where(ok, np.sqrt(np.maximum(d2, 0.0)), np.nan).astype(np.float32)
        return out


def fit_experts(data: Era5Daily, st: Stats, threshold_years: Sequence[int]) -> Experts:
    """References for the rule scores: 99.9th percentile of the clean score on threshold years. ``bound`` and ``stuck``
    use fixed references (1 and 2): their clean distribution is all zeros."""
    pool: Dict[str, Dict[str, List[np.ndarray]]] = {n: {"anomaly": [], "step": []} for n in NAMES}
    rng = np.random.default_rng(0)
    for y in threshold_years:
        for n, x in _fields(data, y).items():
            parts = _parts(x, n, st)
            for k in ("anomaly", "step"):
                v = parts[k][np.isfinite(x)]
                pool[n][k].append(rng.choice(v, min(v.size, 400000), replace=False))
    ref = {n: {"anomaly": max(float(np.quantile(np.concatenate(pool[n]["anomaly"]), 0.999)), 1e-3),
               "step": max(float(np.quantile(np.concatenate(pool[n]["step"]), 0.999)), 1e-3), "bound": 1.0, "stuck": 2.0} for n in NAMES}
    return Experts(st, ref)


# ---------------------------------------------------------------------------------------------- synthetic faults

def inject(fields: Dict[str, np.ndarray], st: Stats, rng_seed: Sequence[int], rate: float = 0.01) -> Tuple[Dict[str, np.ndarray], Dict[str, Dict[str, np.ndarray]]]:
    """Corrupted copy of ``fields`` and labels[variable][kind] -> (T,H,W) bool. Deterministic in ``rng_seed``."""
    out, labels = {}, {}
    for vi, n in enumerate(NAMES):
        x = fields[n]
        T, H, W = x.shape
        rng = np.random.default_rng([*rng_seed, vi])
        bad = x.copy()
        lab = {k: np.zeros(x.shape, bool) for k in KINDS}
        spec = VARIABLES[n]
        dur_range = {"spike": (1, 1), "stuck": (5, 30), "drift": (10, 60), "scale": (5, 30)}
        for kind in KINDS:
            lo, hi = dur_range[kind]
            n_ev = max(int(round(rate / len(KINDS) * T * H * W / ((lo + hi) / 2))), 1)
            for _ in range(n_ev):
                r, c = int(rng.integers(H)), int(rng.integers(W))
                d = int(rng.integers(lo, hi + 1))
                t0 = int(rng.integers(1, max(T - d, 2)))
                t1 = min(t0 + d, T)
                seg = slice(t0, t1)
                if not np.isfinite(x[seg, r, c]).all():
                    continue
                sign = rng.choice([-1.0, 1.0])
                if kind == "spike":
                    bad[t0, r, c] = x[t0, r, c] + sign * rng.uniform(8, 20) * st.step_sd[n][r, c]
                elif kind == "stuck":
                    bad[seg, r, c] = x[t0 - 1, r, c]
                elif kind == "drift":
                    ramp = np.linspace(0, 1, t1 - t0)
                    bad[seg, r, c] = x[seg, r, c] + sign * rng.uniform(3, 8) * st.sd[n][t0:t1, r, c] * ramp
                else:
                    f = rng.choice([rng.uniform(0.1, 0.5), rng.uniform(1.5, 3.0)])
                    cl = st.mean[n][t0:t1, r, c]
                    bad[seg, r, c] = cl + f * (x[seg, r, c] - cl)
                lab[kind][seg, r, c] = True
        np.clip(bad, spec.lo, spec.hi, out=bad)
        out[n], labels[n] = bad, lab
    return out, labels


# ---------------------------------------------------------------------------------------------- neighbour regression experts

GBM_NAMES = tuple(f"gbm_{n}" for n in NAMES)


_RING1 = [(i, j) for i in (-1, 0, 1) for j in (-1, 0, 1) if (i, j) != (0, 0)]
_RING2 = [(i, j) for i in range(-2, 3) for j in range(-2, 3) if max(abs(i), abs(j)) == 2]


def _ring_median(a: np.ndarray, offsets, chunk: int = 48) -> np.ndarray:
    """Median over the cells at the given (row, column) offsets, per day, with the grid edge replicated. A median, not a
    mean, so that one faulty neighbour does not drag the prediction of its healthy neighbours."""
    T, H, W = a.shape
    pad = np.pad(a, ((0, 0), (2, 2), (2, 2)), mode="edge")
    out = np.empty_like(a)
    for t0 in range(0, T, chunk):
        blk = pad[t0:t0 + chunk]
        stack = np.stack([blk[:, 2 + i:2 + i + H, 2 + j:2 + j + W] for i, j in offsets])
        out[t0:t0 + chunk] = np.median(stack, axis=0)
    return out


def _neighbour_means(a: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Median of the 8 cells around each cell (centre excluded) and of the 16 cells in the ring after that, per day."""
    return _ring_median(a, _RING1), _ring_median(a, _RING2)


def _lag(a: np.ndarray, k: int) -> np.ndarray:
    out = np.full_like(a, np.nan)
    out[k:] = a[:-k]
    return out


def _gbm_features(A: Dict[str, np.ndarray], v: str, plane: Tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """(T, H, W, F) features for predicting the anomaly of variable ``v`` at a cell WITHOUT using its own current value:
    the median anomaly of the ring-1 and ring-2 neighbours, the cell's own previous two days, the ring-1 neighbour anomaly
    of the other two variables, season (sin, cos of day of year) and position. The other variables at the cell itself
    are left out on purpose: a fault in one variable then cannot move another variable's prediction (smearing)."""
    T = A[v].shape[0]
    nb1, nb2 = _neighbour_means(A[v])
    others = [u for u in NAMES if u != v]
    doy = 2 * np.pi * np.arange(T, dtype=np.float32) / 365.25
    sh = (T, A[v].shape[1], A[v].shape[2])
    feats = [nb1, nb2, _lag(A[v], 1), _lag(A[v], 2), _neighbour_means(A[others[0]])[0], _neighbour_means(A[others[1]])[0],
             np.broadcast_to(np.sin(doy)[:, None, None], sh), np.broadcast_to(np.cos(doy)[:, None, None], sh),
             np.broadcast_to(plane[0][None], sh), np.broadcast_to(plane[1][None], sh)]
    return np.stack(feats, axis=-1).astype(np.float32)


@dataclass
class GbmExperts:
    """One gradient-boosted regressor per variable: predict the cell's anomaly from its neighbours, its own recent days,
    the neighbours' other variables, season and position; the score is the residual divided by its robust spread
    (median absolute deviation on clean threshold years). Trains in minutes on a CPU; no GPU, no tuning."""
    st: Stats
    models: Dict[str, object]
    mad: Dict[str, float]
    plane: Tuple[np.ndarray, np.ndarray]

    def scores(self, fields: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        A = anomalies(self.st, fields)
        out = {}
        for v in NAMES:
            X = _gbm_features(A, v, self.plane)
            pred = self.models[v].predict(X.reshape(-1, X.shape[-1])).reshape(A[v].shape)
            s = np.abs(A[v] - pred) / self.mad[v]
            out[f"gbm_{v}"] = np.where(np.isfinite(A[v]), s, np.nan).astype(np.float32)
        return out


def fit_gbm(data: Era5Daily, st: Stats, train_years: Sequence[int], threshold_years: Sequence[int], rows_per_year: int = 20000,
            seed: int = 0, max_iter: int = 150) -> GbmExperts:
    """Fit on a random sample of cell-days of the training years; set the residual scale on the clean threshold years."""
    lat, lon = data.grid(train_years[0])
    la = (lat - lat.min()) / max(float(np.ptp(lat)), 1e-6)
    lo = (lon - lon.min()) / max(float(np.ptp(lon)), 1e-6)
    plane = (np.broadcast_to(la[:, None], (lat.size, lon.size)).astype(np.float32),
             np.broadcast_to(lo[None, :], (lat.size, lon.size)).astype(np.float32))
    rng = np.random.default_rng([seed, 7])
    xs: Dict[str, List[np.ndarray]] = {v: [] for v in NAMES}
    ys: Dict[str, List[np.ndarray]] = {v: [] for v in NAMES}
    for y in train_years:
        A = anomalies(st, _fields(data, y))
        for v in NAMES:
            X = _gbm_features(A, v, plane)
            flat, tgt = X.reshape(-1, X.shape[-1]), A[v].reshape(-1)
            ok = np.nonzero(np.isfinite(tgt))[0]
            pick = rng.choice(ok, min(rows_per_year, ok.size), replace=False)
            xs[v].append(flat[pick])
            ys[v].append(tgt[pick])
    models = {v: HistGradientBoostingRegressor(max_iter=max_iter, learning_rate=0.1, max_depth=6, early_stopping=False,
                                               random_state=seed).fit(np.concatenate(xs[v]), np.concatenate(ys[v])) for v in NAMES}
    g = GbmExperts(st, models, {v: 1.0 for v in NAMES}, plane)
    resid: Dict[str, List[np.ndarray]] = {v: [] for v in NAMES}
    for y in threshold_years:
        A = anomalies(st, _fields(data, y))
        for v in NAMES:
            X = _gbm_features(A, v, plane)
            r = np.abs(A[v] - models[v].predict(X.reshape(-1, X.shape[-1])).reshape(A[v].shape))
            resid[v].append(r[np.isfinite(r)][::7])
    g.mad = {v: max(float(1.4826 * np.median(np.concatenate(resid[v]))), 1e-3) for v in NAMES}
    return g


# ---------------------------------------------------------------------------------------------- fusion and evaluation

@dataclass
class Scorer:
    """The experts that feed the fusion: the rule experts and the consistency expert, plus the neighbour regression
    experts when ``gbm`` is given."""
    ex: Experts
    gbm: Optional[GbmExperts] = None
    nn: Optional[object] = None                      # qc.multivar_nn.NnExperts

    @property
    def names(self) -> Tuple[str, ...]:
        from qc.multivar_nn import NN_NAMES
        return NAMES + ("consistency",) + (GBM_NAMES if self.gbm else ()) + (NN_NAMES if self.nn else ())

    @property
    def st(self) -> Stats:
        return self.ex.st

    def scores(self, fields: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        out = self.ex.scores(fields)
        if self.gbm:
            out.update(self.gbm.scores(fields))
        if self.nn:
            out.update(self.nn.scores(fields))
        return out


SCORE_NAMES = NAMES + ("consistency",)


def _stack(sc: Dict[str, np.ndarray], names: Sequence[str] = SCORE_NAMES) -> np.ndarray:
    return np.log1p(np.stack([sc[n] for n in names], axis=-1))


@dataclass
class Fusion:
    mu: np.ndarray
    sd: np.ndarray
    coef: np.ndarray
    intercept: float
    names: Tuple[str, ...] = SCORE_NAMES

    def score(self, sc: Dict[str, np.ndarray]) -> np.ndarray:
        x = _stack(sc, self.names)
        z = np.nan_to_num((x - self.mu) / self.sd, nan=0.0)
        out = z @ self.coef + self.intercept
        return np.where(np.isfinite(x).all(axis=-1), out, np.nan).astype(np.float32)


def fit_fusion(scorer, data: Era5Daily, years: Sequence[int], rate: float, seed: int, max_rows: int = 600000) -> Fusion:
    names = tuple(getattr(scorer, "names", SCORE_NAMES))
    xs, ys = [], []
    rng = np.random.default_rng([seed, 99])
    for y in years:
        clean = _fields(data, y)
        bad, labels = inject(clean, scorer.st, [seed, y], rate)
        sc = scorer.scores(bad)
        any_fault = np.zeros(next(iter(bad.values())).shape, bool)
        for n in NAMES:
            for k in KINDS:
                any_fault |= labels[n][k]
        x = _stack(sc, names)
        ok = np.isfinite(x).all(axis=-1)
        pos, neg = np.nonzero((ok & any_fault).ravel())[0], np.nonzero((ok & ~any_fault).ravel())[0]
        neg = rng.choice(neg, min(neg.size, max(max_rows // max(len(years), 1) - pos.size, 1)), replace=False)
        flat = x.reshape(-1, x.shape[-1])
        xs += [flat[pos], flat[neg]]
        ys += [np.ones(pos.size), np.zeros(neg.size)]
    X, Y = np.concatenate(xs), np.concatenate(ys)
    if Y.sum() == 0:
        raise RuntimeError("no fault cell-days in the fusion fit years")
    mu, sd = X.mean(0), X.std(0) + 1e-6
    m = LogisticRegression(C=1.0, max_iter=500, class_weight="balanced").fit((X - mu) / sd, Y)
    return Fusion(mu, sd, m.coef_[0], float(m.intercept_[0]), names)


def _recall(score: np.ndarray, label: np.ndarray, thr: float) -> Optional[float]:
    ok = label & np.isfinite(score)
    return float((score[ok] > thr).mean()) if ok.any() else None


def run_validation(data: Era5Daily, years: Dict[str, Sequence[int]], rate: float = 0.01, seed: int = 0,
                   budgets: Sequence[float] = (0.5, 1.0, 2.0, 5.0), out_path: Optional[Path] = None, gbm: bool = True,
                   nn: Optional[Dict] = None) -> Dict:
    """Fit on ``years['train']`` (statistics and, with ``gbm``, the neighbour regression experts), ``years['fusion_fit']``
    (fusion); thresholds from clean and evaluation on corrupted ``years['threshold']``. Years must not overlap across
    roles: train < fusion_fit, and threshold is disjoint."""
    tr, ff, th = list(years["train"]), list(years["fusion_fit"]), list(years["threshold"])
    if set(tr) & set(ff) or set(tr) & set(th) or set(ff) & set(th):
        raise ValueError("train, fusion_fit and threshold years must be disjoint")
    st = fit_stats(data, tr)
    ex = fit_experts(data, st, th)
    gbm_years = tr[::max(1, len(tr) // 12)]                       # at most about 12 evenly spaced training years: plenty for the regressors, and fast
    nn_experts = None
    if nn:                                           # neural experts (GPU if there is one): tuned on clean fusion-fit years, never on faults
        from qc.multivar_nn import NnConfig, fit_nn
        nn_experts = fit_nn(data, st, tr, ff, NnConfig(steps=int(nn.get("steps", 3000))), trials=int(nn.get("trials", 0)),
                            max_years=int(nn.get("max_years", 8)), seed=seed, time_cap_hours=nn.get("time_cap_hours"))
    scorer = Scorer(ex, fit_gbm(data, st, gbm_years, th, seed=seed) if gbm else None, nn_experts)
    fu = fit_fusion(scorer, data, ff, rate, seed)
    clean_scores: Dict[str, List[np.ndarray]] = {k: [] for k in scorer.names + ("fusion", "fusion_max")}
    clean_years = []
    for y in th:
        sc = scorer.scores(_fields(data, y))
        sc["fusion"] = fu.score(sc)
        clean_years.append(sc)
        for k, v in sc.items():
            clean_scores[k].append(v[np.isfinite(v)])
    # "fusion_max": no fitting. Each expert is standardized on the clean threshold years and the largest value wins, so a
    # fault that only one expert sees (a temperature fault seen by the temperature expert) is not diluted by the others.
    zmu = {k: float(np.mean(np.log1p(np.concatenate(clean_scores[k])))) for k in scorer.names}
    zsd = {k: float(np.std(np.log1p(np.concatenate(clean_scores[k])))) + 1e-6 for k in scorer.names}
    maxz = lambda sc: np.max([(np.log1p(sc[k]) - zmu[k]) / zsd[k] for k in scorer.names], axis=0).astype(np.float32)
    for sc in clean_years:
        v = maxz(sc)
        clean_scores["fusion_max"].append(v[np.isfinite(v)])
    del clean_years
    thr = {k: budget_thresholds(np.concatenate(v), list(budgets)) for k, v in clean_scores.items()}
    hits = {k: {b: {n: {kk: [0, 0] for kk in KINDS} for n in NAMES} for b in budgets} for k in thr}
    false = {k: {b: [0, 0] for b in budgets} for k in thr}
    for y in th:
        bad, labels = inject(_fields(data, y), st, [seed, 1000 + y], rate)
        sc = scorer.scores(bad)
        sc["fusion"] = fu.score(sc)
        sc["fusion_max"] = maxz(sc)
        anyf = np.zeros(sc["fusion"].shape, bool)
        for n in NAMES:
            for kk in KINDS:
                anyf |= labels[n][kk]
        for k in thr:
            for b in budgets:
                for n in NAMES:
                    for kk in KINDS:
                        m = labels[n][kk] & np.isfinite(sc[k])
                        hits[k][b][n][kk][0] += int((sc[k][m] > thr[k][b]).sum()); hits[k][b][n][kk][1] += int(m.sum())
                cl = ~anyf & np.isfinite(sc[k])
                false[k][b][0] += int((sc[k][cl] > thr[k][b]).sum()); false[k][b][1] += int(cl.sum())
    res = {"years": {"train": tr, "fusion_fit": ff, "threshold_and_evaluation": th}, "rate": rate, "seed": seed,
           "budgets": list(budgets), "label_tier": "synthetic faults on ERA5 daily means (modelled data)", "limits": LIMITS,
           "references": ex.ref, "consistency_cov": st.cov.tolist(), "gbm": bool(gbm),
           "nn": None if nn_experts is None else nn_experts.history,
           "fusion": {"names": list(fu.names), "coef": fu.coef.tolist()}, "scores": {}}
    for k in thr:
        res["scores"][k] = {}
        for b in budgets:
            h = hits[k][b]
            res["scores"][k][str(b)] = {
                "false_per_1000_clean": 1000.0 * false[k][b][0] / max(false[k][b][1], 1),
                "recall": {n: {kk: (h[n][kk][0] / h[n][kk][1] if h[n][kk][1] else None) for kk in KINDS} for n in NAMES}}
    if out_path:
        write_json(out_path, res)
    return res
