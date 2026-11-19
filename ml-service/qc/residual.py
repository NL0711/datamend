"""Neighbour-residual evidence for the faults the existing components miss: zeroed values, scale errors and slow drift.

Why this exists. The fusion only sees each component's single score. None of them says "this cell is dry while its neighbours are
wet" (zeroed), or "this value is far from what its neighbours imply" (scale), or "this cell has been drifting away from its
neighbours for weeks" (drift). Per fault kind, the ceiling check (qc/ceiling.py) found recall of 0 to 0.3 on strong faults for these.

Two untrained-style scores (fitted tables on TRAINING years only, then fixed):

  ``nbr_surprise``  Let m be the median of the same-day values of the usable neighbours (ring outside the hidden disc, so a fault
                    footprint cannot vouch for itself). For the neighbour state (m in 9 bins, monsoon or not) the training years give
                    the distribution of the cell's own value: P(dry) and the distribution of wet values. The score is
                    -log10 of the probability of a value at least as extreme on the more extreme side:
                       dry own value:  -log10 P(dry | state)                     (high when neighbours are wet: zeroed)
                       wet own value:  -log10 min(P(own <= x), P(own >= x))     (high far above or below the neighbours: scale, phantom rain)
                    Capped at 6. A cell with fewer than MIN_NEIGHBOURS usable neighbours scores 0 (no judgement).
  ``drift_cusum``   d = (r - median_state(r)) / spread_state(r) with r = log1p(own) - log1p(m), the cell's standing against its
                    neighbours. A two-sided CUSUM, S+ = max(0, S+ + d - K) and S- = max(0, S- - d - K), run over the history rows of the
                    block and the scored year, causal (day t uses days up to t only). The score is max(S+, S-).

Both are non-negative, NaN where the cell's own value is missing, and are meant for the learned fusion variants (the fusion takes
log1p of every score). Limits, stated honestly: a fault whose footprint covers the neighbours too (radius up to 4 cells, more in test)
shifts the neighbours as well and weakens the evidence; the season split is monsoon (June to September) against the rest, nothing finer;
the tables are fitted on a sample of training-client cells. Validation-only until the architecture is chosen. SYNTHETIC faults only.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from qc import paths
from qc.neighbours import gather, ring_index
from qc.prepare import Prepared
from qc.scoring import Block

RESIDUAL = ("nbr_surprise", "drift_cusum")
RADIUS = 4.0                  # outer ring radius, cells; the inner radius is components.hidden_radius
MIN_NEIGHBOURS = 3
WET_MM = 0.1
EDGES = np.array([0.1, 1.0, 2.5, 5.0, 10.0, 20.0, 40.0, 80.0])      # neighbour-median bins: 9
N_BINS = len(EDGES) + 1
N_TABLES = 2 * N_BINS                                                # x (off-monsoon, monsoon)
CAP = 6.0
CUSUM_K = 0.5
SD_FLOOR = 0.25
MIN_SAMPLES = 200
MONSOON = (151, 273)          # 0-based day of year, about 1 June to 30 September


def table_index(med: np.ndarray, doy: np.ndarray) -> np.ndarray:
    """(rows, n) neighbour medians and (rows,) day of year -> (rows, n) table number."""
    mons = ((doy >= MONSOON[0]) & (doy < MONSOON[1]))[:, None]
    return np.searchsorted(EDGES, med, side="right") + N_BINS * mons


def neighbour_median(chunk: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """(c, n) -> (c, n) median of the usable neighbours, NaN with fewer than MIN_NEIGHBOURS."""
    nb = gather(chunk, ring)
    ok = np.isfinite(nb)
    cnt = ok.sum(axis=2)
    srt = np.sort(np.where(ok, nb, np.inf), axis=2)
    lo = np.take_along_axis(srt, np.clip((cnt - 1) // 2, 0, None)[..., None], axis=2)[..., 0]
    hi = np.take_along_axis(srt, np.clip(cnt // 2, 0, None)[..., None], axis=2)[..., 0]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = 0.5 * (lo + hi)
    return np.where(cnt >= MIN_NEIGHBOURS, med, np.nan).astype(np.float32)


@dataclass
class Reference:
    p0: np.ndarray            # (N_TABLES,) share of dry own values
    n: np.ndarray             # (N_TABLES,) samples behind each table
    wet: List[np.ndarray]     # sorted wet own values per table
    mu: np.ndarray            # (N_TABLES,) median of r
    sd: np.ndarray            # (N_TABLES,) robust spread of r, floored

    @property
    def valid(self) -> np.ndarray:
        return self.n >= MIN_SAMPLES

    def save(self, path: Path, years: List[int]) -> None:
        sizes = np.array([w.size for w in self.wet])
        np.savez_compressed(path, p0=self.p0, n=self.n, mu=self.mu, sd=self.sd, sizes=sizes,
                            wet=np.concatenate(self.wet) if sizes.sum() else np.zeros(0, np.float32), years=np.array(years))

    @staticmethod
    def load(path: Path) -> "Reference":
        z = np.load(path)
        edges = np.concatenate([[0], np.cumsum(z["sizes"])])
        wet = [z["wet"][edges[i]:edges[i + 1]] for i in range(len(z["sizes"]))]
        ref = Reference(z["p0"], z["n"], wet, z["mu"], z["sd"])
        ref._years = [int(y) for y in z["years"]]                    # type: ignore[attr-defined]
        return ref


def build_reference(own: np.ndarray, med: np.ndarray, doy: np.ndarray, rng: np.random.Generator, max_wet: int = 100_000) -> Reference:
    """Tables from clean values (rows, m) with their neighbour medians and day of year. Pure: arrays in, Reference out."""
    tab = table_index(med, doy)
    fin = np.isfinite(own) & np.isfinite(med)
    r = np.log1p(np.clip(own, 0, None)) - np.log1p(np.clip(med, 0, None))
    p0, n, mu, sd, wet = (np.full(N_TABLES, np.nan), np.zeros(N_TABLES, np.int64), np.zeros(N_TABLES), np.ones(N_TABLES), [])
    for t in range(N_TABLES):
        m = fin & (tab == t)
        x = own[m]
        n[t] = x.size
        if x.size >= 1:
            p0[t] = float((x < WET_MM).mean())
        w = np.sort(x[x >= WET_MM]).astype(np.float32)
        if w.size > max_wet:
            w = np.sort(rng.choice(w, max_wet, replace=False))
        wet.append(w)
        if x.size >= MIN_SAMPLES:
            rr = r[m]
            mu[t] = float(np.median(rr))
            sd[t] = max(float(1.4826 * np.median(np.abs(rr - mu[t]))), SD_FLOOR)
    return Reference(p0, n, wet, mu, sd)


def surprise(ref: Reference, own: np.ndarray, med: np.ndarray, tab: np.ndarray) -> np.ndarray:
    out = np.zeros(own.shape, np.float32)
    fin = np.isfinite(own) & np.isfinite(med)
    for t in np.nonzero(ref.valid)[0]:
        m = fin & (tab == t)
        if not m.any():
            continue
        x = own[m].astype(np.float64)
        p0, w = float(ref.p0[t]), ref.wet[t]
        dry = x < WET_MM
        pl, pg = np.ones(x.size), np.ones(x.size)
        pl[dry], pg[dry] = p0, 1.0
        xw = x[~dry]
        if w.size:
            f_le = np.searchsorted(w, xw, side="right") / w.size
            f_ge = 1.0 - np.searchsorted(w, xw, side="left") / w.size
        else:
            f_le = f_ge = np.ones(xw.size)
        pl[~dry], pg[~dry] = p0 + (1.0 - p0) * f_le, (1.0 - p0) * f_ge
        p = np.minimum(pl, pg)
        out[m] = np.minimum(-np.log10(np.maximum(p, 10.0 ** -CAP)), CAP)
    return np.where(np.isfinite(own), out, np.nan).astype(np.float32)


def cusum(d: np.ndarray, k: float = CUSUM_K) -> np.ndarray:
    """(rows, n) standardised residuals -> (rows, n) two-sided CUSUM, causal; NaN counts as 0."""
    d = np.nan_to_num(d, nan=0.0)
    sp = np.zeros(d.shape[1])
    sm = np.zeros(d.shape[1])
    out = np.empty(d.shape, np.float32)
    for t in range(d.shape[0]):
        sp = np.maximum(0.0, sp + d[t] - k)
        sm = np.maximum(0.0, sm - d[t] - k)
        out[t] = np.maximum(sp, sm)
    return out


def score_arrays(ref: Reference, own: np.ndarray, med: np.ndarray, doy: np.ndarray, pad: int):
    """(surprise, drift) for the rows after ``pad`` of (pad + T, n) arrays."""
    tab = table_index(med, doy)
    sur = surprise(ref, own[pad:], med[pad:], tab[pad:])
    r = np.log1p(np.clip(own, 0, None)) - np.log1p(np.clip(med, 0, None))
    ok = ref.valid[tab]
    d = np.where(ok & np.isfinite(r), (r - ref.mu[tab]) / ref.sd[tab], 0.0)
    drift = cusum(d)[pad:]
    drift = np.where(np.isfinite(own[pad:]), drift, np.nan).astype(np.float32)
    return sur, drift


# ---------------------------------------------------------------------------------------------- with the prepared data

def _ring(p: Prepared) -> np.ndarray:
    return ring_index(p.grid, float(p.cfg.components.hidden_radius), RADIUS)


def reference_path(p: Prepared) -> Path:
    return paths.work_dir(p.cfg) / "splits" / f"residual_reference_{p.manifest['hash']}.npz"


def fit_reference(p: Prepared, n_cells: int = 600, chunk: int = 30) -> Reference:
    """Fitted once on TRAINING years (clean values, training-client cells sampled), cached next to the split manifest."""
    from qc.evaluate import group_cells
    path = reference_path(p)
    years = list(p.split.years["train"])
    if path.is_file():
        ref = Reference.load(path)
        if getattr(ref, "_years", None) == years:
            return ref
    seen = np.nonzero(group_cells(p, "seen"))[0]
    rng = np.random.default_rng([int(p.cfg.seed), 4242])
    sub = np.sort(rng.choice(seen, min(n_cells, seen.size), replace=False))
    ring = _ring(p)[sub]
    own_all, med_all, doy_all = [], [], []
    for y in years:
        a = p.store.year(y)
        med = np.concatenate([neighbour_median(a[s:s + chunk], ring) for s in range(0, a.shape[0], chunk)])
        own_all.append(a[:, sub])
        med_all.append(med)
        doy_all.append(np.arange(a.shape[0]))
    ref = build_reference(np.concatenate(own_all), np.concatenate(med_all), np.concatenate(doy_all), rng)
    ref.save(path, years)
    ref._years = years                                                                   # type: ignore[attr-defined]
    return ref


def residual_functions(p: Prepared, chunk: int = 30) -> Dict:
    """name -> ScoreFn (Block -> (T, n_land)). Both come from one pass over the same block object."""
    ref = fit_reference(p)
    ring = _ring(p)
    cache: Dict = {}

    def pair(block: Block):
        if cache.get("block") is not block:
            obs = block.obs
            med = np.concatenate([neighbour_median(obs[s:s + chunk], ring) for s in range(0, obs.shape[0], chunk)])
            cache["block"], cache["val"] = block, score_arrays(ref, obs, med, block.doy, block.pad)
        return cache["val"]

    return {"nbr_surprise": lambda b: pair(b)[0], "drift_cusum": lambda b: pair(b)[1]}
