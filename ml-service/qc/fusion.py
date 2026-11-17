"""Gate 5: fuse four component scores into one score per cell-day.

Features  rules, slow, spatial_s<seed>, temporal_s<seed>. Each score is mapped with log1p (scores are >= 0
          and heavy-tailed) and standardized with the mean and standard deviation of the fit rows. A missing
          component score becomes 0 after standardizing (the average case), never a fault signal.
Fit data  Synthetic faults of the validation years ``years.fusion_fit``, cells of training clients only.
          Positives: fault cell-days. Negatives: every other scored cell-day, protected extremes included (so
          the fusion learns that agreement among components, not a large value alone, signals a fault);
          ambiguous extremes are left out. Thresholds are NOT set here: see ``thresholds_for`` in qc.evaluate,
          which uses clean threshold-year scores.

Variants (spec section 7), all fitted on the same rows:
  logistic    one shared logistic regression (the main fusion). Score = the log-odds.
  mean        plain average of the four standardized scores (no fitting beyond the standardization).
  or          OR of component flags: every component's score becomes the tail probability of that score on
              clean threshold years; the fused score is the smallest tail probability, as -log10. A cell-day
              is flagged when any component is that rare.
  boosted     histogram gradient-boosted trees on the four standardized scores. Score = log-odds.
  per_client  one logistic regression per training client; unseen clients use the shared one.

Fitted fusions are saved to ``<run>/fusion/<variant>_s<seed>.*``; fused scores go in the score store as
``fusion_<variant>_s<seed>`` so every metric in qc.evaluate applies unchanged.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

from qc.evaluate import group_cells, score_store
from qc.extremes import find_extremes
from qc.prepare import Prepared
from qc.scoring import ScoreStore
from qc.splits import assert_years_allowed

log = logging.getLogger(__name__)
BASE = ("rules", "slow", "spatial", "temporal")
VARIANTS = ("logistic", "mean", "or", "boosted", "per_client")
FED_SOURCES = ("fedpers", "fedavg", "fedft")      # federated variants that score every cell, so a fusion can use them


def component_names(seed: int, base: Sequence[str] = BASE, source: str = "central", prox_mu: float = 0.0) -> List[str]:
    """Store names of the four inputs: rules and slow are untrained; spatial and temporal carry the seed.
    ``source`` is "central" (the centralized components) or a federated variant: then spatial and temporal are that
    variant's scores (``fedpers_spatial_s0``), so the fusion is fitted on what the federated components produce."""
    if source != "central" and source not in FED_SOURCES:
        raise ValueError(f"fusion source {source!r}: use central or one of {FED_SOURCES} (local-only leaves unseen cells unscored)")
    from qc.federated import run_label

    def one(b: str) -> str:
        if b in ("rules", "slow", "neighbour_baseline"):          # untrained: no seed
            return b
        return f"{b}_s{seed}" if source == "central" else run_label(source, b, seed, prox_mu)
    return [one(b) for b in base]


def load_features(store: ScoreStore, names: Sequence[str], tag: str, year: int) -> np.ndarray:
    """(T, n_land, F) log1p of the component scores of one year; NaN where a component did not score."""
    return np.log1p(np.stack([store.load(n, tag, year) for n in names], axis=-1))


@dataclass
class FusionFit:
    seed: int
    names: List[str]
    mu: np.ndarray
    sd: np.ndarray
    fit_years: List[int]
    n_rows: int
    n_positive: int
    logistic: Dict                       # coef (F,), intercept
    boosted: HistGradientBoostingClassifier
    per_client: Dict[int, Dict]          # client -> coef, intercept
    tail_sorted: List[np.ndarray]        # per component, sorted clean threshold-year scores (the "or" variant)
    scale_limit: float = 50.0
    logistic_fed: Optional[Dict] = None  # logistic regression fitted by federated averaging (see fit_fusion_federated)
    source: str = "central"              # which spatial and temporal scores the fusion was fitted on (central or a federated variant)

    @property
    def tag(self) -> str:
        return "" if self.source == "central" else f"_{self.source}"

    def standardize(self, feats: np.ndarray) -> np.ndarray:
        z = (feats - self.mu) / self.sd
        return np.nan_to_num(z, nan=0.0)

    def score(self, variant: str, feats: np.ndarray, cell_client: Optional[np.ndarray] = None) -> np.ndarray:
        """feats (T, n, F) from ``load_features``. Returns (T, n) float32; NaN where no component scored."""
        z = self.standardize(feats)
        if variant == "logistic":
            out = z @ self.logistic["coef"] + self.logistic["intercept"]
        elif variant == "logistic_fed":
            if self.logistic_fed is None:
                raise ValueError("no federated fusion fitted; call fit_fusion_federated first")
            out = z @ self.logistic_fed["coef"] + self.logistic_fed["intercept"]
        elif variant == "mean":
            out = z.mean(axis=-1)
        elif variant == "or":
            u = []
            for f in range(feats.shape[-1]):
                s = self.tail_sorted[f]
                raw = np.expm1(feats[..., f])
                frac = 1.0 - np.searchsorted(s, np.nan_to_num(raw, nan=0.0), side="left") / s.size
                u.append(-np.log10(np.maximum(frac, 0.5 / s.size)))
            out = np.max(u, axis=0)
        elif variant == "boosted":
            flat = z.reshape(-1, z.shape[-1])
            p = np.clip(self.boosted.predict_proba(flat)[:, 1], 1e-6, 1 - 1e-6)
            out = np.log(p / (1 - p)).reshape(z.shape[:-1])
        elif variant == "per_client":
            if cell_client is None:
                raise ValueError("per_client fusion needs cell_client")
            out = z @ self.logistic["coef"] + self.logistic["intercept"]          # unseen clients: the shared fusion
            for c, m in self.per_client.items():
                sel = cell_client == c
                out[:, sel] = z[:, sel] @ m["coef"] + m["intercept"]
        else:
            raise ValueError(f"unknown variant {variant!r}")
        out = np.asarray(out, np.float32)
        out[~np.isfinite(feats).any(axis=-1)] = np.nan
        return out

    def probability(self, feats: np.ndarray) -> np.ndarray:
        """Fault probability of the shared logistic fusion, calibrated to the synthetic fault rate only."""
        return 1.0 / (1.0 + np.exp(-self.score("logistic", feats).astype(np.float64)))

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        doc = {"seed": self.seed, "source": self.source, "names": self.names, "mu": self.mu.tolist(), "sd": self.sd.tolist(),
               "fit_years": self.fit_years, "n_rows": self.n_rows, "n_positive": self.n_positive,
               "logistic": {"coef": self.logistic["coef"].tolist(), "intercept": float(self.logistic["intercept"])},
               "logistic_fed": None if self.logistic_fed is None else {"coef": self.logistic_fed["coef"].tolist(), "intercept": float(self.logistic_fed["intercept"])},
               "per_client": {str(c): {"coef": m["coef"].tolist(), "intercept": float(m["intercept"])} for c, m in self.per_client.items()}}
        (folder / f"logistic{self.tag}_s{self.seed}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
        joblib.dump({"boosted": self.boosted, "tail_sorted": self.tail_sorted}, folder / f"other{self.tag}_s{self.seed}.joblib")

    @classmethod
    def load(cls, folder: Path, seed: int, source: str = "central") -> "FusionFit":
        tag = "" if source == "central" else f"_{source}"
        doc = json.loads((folder / f"logistic{tag}_s{seed}.json").read_text(encoding="utf-8"))
        other = joblib.load(folder / f"other{tag}_s{seed}.joblib")
        return cls(seed, doc["names"], np.array(doc["mu"]), np.array(doc["sd"]), doc["fit_years"], doc["n_rows"], doc["n_positive"],
                   {"coef": np.array(doc["logistic"]["coef"]), "intercept": doc["logistic"]["intercept"]}, other["boosted"],
                   {int(c): {"coef": np.array(m["coef"]), "intercept": m["intercept"]} for c, m in doc["per_client"].items()},
                   other["tail_sorted"],
                   logistic_fed=None if not doc.get("logistic_fed") else {"coef": np.array(doc["logistic_fed"]["coef"]), "intercept": doc["logistic_fed"]["intercept"]},
                   source=doc.get("source", "central"))


def _logit_fit(x, y, w, C):
    m = LogisticRegression(C=C, max_iter=500).fit(x, y, sample_weight=w)
    return {"coef": m.coef_[0].astype(np.float64), "intercept": float(m.intercept_[0])}


def fusion_rows(p: Prepared, seed: int, store: ScoreStore, names: Sequence[str]):
    """Fit rows: (x (N, F) log1p scores, y (N,), weight (N,), client (N,)) from the synthetic faults of ``years.fusion_fit``,
    cells of training clients only. Clean rows are subsampled to ``fusion.max_rows`` and reweighted."""
    from qc.benchmark import load_bench_year
    cfg = p.cfg
    years = list(p.split.years["fusion_fit"])
    assert_years_allowed("fusion fit", years, p.split, "val")
    if set(years) & set(p.split.years["threshold"]):
        raise RuntimeError("fusion fit years overlap the threshold years")
    cells = group_cells(p, "seen")
    rng = np.random.default_rng([int(cfg.seed), seed, 5])
    xs, ys, ws, cl = [], [], [], []
    per_year = max(int(cfg.fusion.max_rows) // len(years), 1)
    for y in years:
        feats = load_features(store, names, "val", y)
        bench = load_bench_year(p, "val", y)
        lab = bench.faults.labels()
        keep = np.isfinite(feats).any(axis=-1) & ~bench.extremes.ambiguous & cells[None, :]
        pos = np.nonzero((keep & lab).ravel())[0]
        neg = np.nonzero((keep & ~lab).ravel())[0]
        take = min(neg.size, max(per_year - pos.size, 1))
        neg_s = rng.choice(neg, take, replace=False) if take < neg.size else neg
        w_neg = neg.size / max(neg_s.size, 1)                    # undo the subsampling so probabilities stay calibrated
        flat = feats.reshape(-1, feats.shape[-1])
        for idx, lab_value, w in ((pos, 1, 1.0), (neg_s, 0, w_neg)):
            xs.append(flat[idx]); ys.append(np.full(idx.size, lab_value, np.int8)); ws.append(np.full(idx.size, w, np.float32))
            cl.append(p.cell_client[idx % feats.shape[1]])
    x, yv, w, client = np.concatenate(xs), np.concatenate(ys), np.concatenate(ws), np.concatenate(cl)
    if yv.sum() == 0:
        raise RuntimeError("no fault cell-days in the fusion fit years")
    return x, yv, w, client


def fit_fusion(p: Prepared, seed: int, store: Optional[ScoreStore] = None, base: Sequence[str] = BASE,
               source: str = "central") -> FusionFit:
    """Fit every variant on the synthetic faults of ``years.fusion_fit``. Uses no test-year or threshold-year benchmark data
    (the "or" variant uses clean threshold-year scores, never labels)."""
    cfg, store = p.cfg, store or score_store(p)
    years = list(p.split.years["fusion_fit"])
    names = component_names(seed, base, source, float(cfg.federated.prox_mu))
    cells = group_cells(p, "seen")
    x, yv, w, client = fusion_rows(p, seed, store, names)
    mu, sd = np.nanmean(x, axis=0, dtype=np.float64), np.nanstd(x, axis=0, dtype=np.float64) + 1e-6
    z = np.nan_to_num((x - mu) / sd, nan=0.0)
    C = float(cfg.fusion.C)
    shared = _logit_fit(z, yv, w, C)
    boosted = HistGradientBoostingClassifier(max_iter=int(cfg.fusion.boosted_iter), learning_rate=0.1, max_depth=4,
                                             random_state=seed).fit(z, yv, sample_weight=w)
    per_client = {}
    for c in p.split.train_clients:
        m = client == c
        if yv[m].sum() >= 10 and (yv[m] == 0).any():
            per_client[c] = _logit_fit(z[m], yv[m], w[m], C)
    tails = []
    for f, n in enumerate(names):
        ref = []
        for y in p.split.years["threshold"]:
            ex = find_extremes(p.store.year(y), p.stats.heavy_mm, p.grid, int(cfg.extremes.min_cells))
            s = store.load(n, "clean", y)
            keep = ~ex.protected & ~ex.ambiguous & cells[None, :] & np.isfinite(s)
            ref.append(s[keep])
        tails.append(np.sort(np.concatenate(ref)))
    return FusionFit(seed, names, mu, sd, years, int(yv.size), int(yv.sum()), shared, boosted, per_client, tails, source=source)


def fused_name(variant: str, seed: int, source: str = "central") -> str:
    """Score-store name. A fusion fitted on federated components gets ``@<variant>`` so it never overwrites the main one."""
    return f"fusion_{variant}_s{seed}" if source == "central" else f"fusion_{variant}@{source}_s{seed}"


def apply_fusion(p: Prepared, fit: FusionFit, splits: Sequence[str] = ("val",), variants: Sequence[str] = VARIANTS,
                 store: Optional[ScoreStore] = None, overwrite: bool = False) -> None:
    """Write fused scores for the benchmark years of ``splits`` and for the clean threshold years."""
    store = store or score_store(p)
    jobs = [(s, y) for s in splits for y in p.split.years[s]] + [("clean", y) for y in p.split.years["threshold"]]
    for tag, year in jobs:
        todo = [v for v in variants if overwrite or not store.has(fused_name(v, fit.seed, fit.source), tag, year)]
        if not todo:
            continue
        feats = load_features(store, fit.names, tag, year)
        for v in todo:
            store.save(fused_name(v, fit.seed, fit.source), tag, year, fit.score(v, feats, p.cell_client))


def fit_fusion_federated(p: Prepared, fit: FusionFit, store: Optional[ScoreStore] = None, rounds: Optional[int] = None,
                         local_iters: int = 3) -> Dict:
    """Fit the shared logistic fusion by federated averaging and store it as ``fit.logistic_fed``.

    Each training client holds only its own fit rows. The server first aggregates per-client sums to get the
    standardizer (it equals the pooled one), then for ``rounds`` rounds every client takes ``local_iters``
    Newton steps on its own regularized logistic loss starting from the global weights, and the server averages
    the results weighted by each client's total row weight. Simulation only; no privacy claim.
    """
    store = store or score_store(p)
    cfg = p.cfg
    rounds = int(rounds or cfg.federated.fusion_rounds)
    x, yv, w, client = fusion_rows(p, fit.seed, store, fit.names)
    clients = [c for c in p.split.train_clients if (client == c).any()]
    n = x.shape[1]
    cnt, tot, sq = np.zeros(n), np.zeros(n), np.zeros(n)
    for c in clients:                                              # what each client reports: counts and sums
        xc = x[client == c].astype(np.float64)
        ok = np.isfinite(xc)
        cnt += ok.sum(0); tot += np.where(ok, xc, 0).sum(0); sq += (np.where(ok, xc, 0) ** 2).sum(0)
    mu = tot / cnt
    sd = np.sqrt(np.maximum(sq / cnt - mu ** 2, 0.0)) + 1e-6
    local = {}
    for c in clients:
        m = client == c
        z = np.nan_to_num((x[m] - mu) / sd, nan=0.0)
        local[c] = (np.hstack([z, np.ones((z.shape[0], 1))]), yv[m].astype(float), w[m].astype(float))
    w_total = float(sum(v[2].sum() for v in local.values()))
    lam = 1.0 / (float(cfg.fusion.C) * w_total)                    # sklearn: 0.5 ||b||^2 + C * sum(w * loss)
    beta = np.zeros(n + 1)
    for _ in range(rounds):
        updates, weights = [], []
        for c, (xa, ya, wa) in local.items():
            b = beta.copy()
            for _ in range(local_iters):
                pr = 1.0 / (1.0 + np.exp(-np.clip(xa @ b, -30, 30)))
                reg = np.r_[np.full(n, lam), 0.0]                  # the intercept is not regularized
                grad = xa.T @ (wa * (pr - ya)) / wa.sum() + reg * b
                hess = (xa * (wa * pr * (1 - pr))[:, None]).T @ xa / wa.sum() + np.diag(reg) + 1e-8 * np.eye(n + 1)
                b = b - np.linalg.solve(hess, grad)
            updates.append(b); weights.append(wa.sum())
        beta = np.average(updates, axis=0, weights=weights)
    fit.logistic_fed = {"coef": beta[:n], "intercept": float(beta[n]), "mu": mu, "sd": sd, "rounds": rounds}
    return fit.logistic_fed
