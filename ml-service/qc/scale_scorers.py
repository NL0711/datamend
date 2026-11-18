"""Scorers for the coarser time scales (monthly, seasonal, yearly): baselines and candidates behind one interface.

STATUS: new, unit-tested on generated arrays only; nothing has run on real RF25. Which candidate is kept is decided by
``qc.scale_select`` on validation years, not here. Spec: docs/qc-multires-pipeline-spec.md section 3 and 4.

Interface (everything a caller must know):

  ``scorer.fit(train, ctx, seed) -> scorer``   ``train`` is ``{year: Periods}`` of TRAINING years only.
  ``scorer.score(periods, prev, ctx) -> (P, n_land)``   higher = more suspicious; NaN where the period is not valid or the
        scorer has too little to go on. ``prev`` is the previous year's ``Periods`` (or None): the only thing from another year
        that a scorer may read, and only for the cell's own earlier periods.
  ``scorer.name`` and ``scorer.complexity`` (0 = simplest) are used by the selection rule.

What a scorer may see: the cell's own earlier periods, the same period of its neighbours with the target and a hidden disc
removed (``ctx.near_idx`` starts outside the hidden radius), the cell's training-year climatology, season, position. It never
sees the target period's own value in its inputs and never a later period.

Baselines (no or almost no training): ``gamma_zero`` (zero probability plus a gamma per cell and period) and ``loo_median``
(leave-one-out neighbour residual against the MEDIAN of the neighbours' anomalies, so one faulty cell does not flag the healthy
cells around it; the kriging variant named in the spec is NOT IMPLEMENTED). A first version used an inverse-distance weighted
mean; a test showed it smeared a single bad cell into its neighbours (a neighbour scored about half as high as the bad cell),
so the median was used instead. Candidates: ``gbm_neighbour`` (pooled gradient-boosted regression, no rainfall-QC precedent
found) and ``mlp_neighbour`` (small pooled scikit-learn MLP, not the Gamma-head network of the spec).
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
from scipy import stats as sps
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.neural_network import MLPRegressor

from qc.grid import Grid
from qc.neighbours import ring_index, ring_offsets
from qc.resolution import Periods, ScaleStats, WET_MM

ZERO_MM = WET_MM
MIN_NEIGHBOURS = 3
MIN_SPREAD = 0.05            # floor of the residual spread, in log1p units


@dataclass
class ScaleContext:
    scale: str
    stats: ScaleStats
    cell_client: np.ndarray      # (n,) client id
    lat: np.ndarray              # (n,) degrees
    lon: np.ndarray              # (n,)
    near_idx: np.ndarray         # (n, K1) land-cell indices between the hidden radius and ``near``; -1 = none
    near_w: np.ndarray           # (n, K1) inverse-square-distance weights
    far_idx: np.ndarray          # (n, K2) land-cell indices between ``near`` and ``far``
    target_ok: np.ndarray        # (n,) bool: cells that may be fitting targets
    read_ok: np.ndarray          # (n,) bool: cells whose values may be read during fitting


def make_context(grid: Grid, cell_client: np.ndarray, stats: ScaleStats, hidden_radius: float = 2.0, near: float = 4.0,
                 far: float = 8.0, target_ok: Optional[np.ndarray] = None, read_ok: Optional[np.ndarray] = None) -> ScaleContext:
    if not hidden_radius < near < far:
        raise ValueError("need hidden_radius < near < far")
    n = grid.n_land
    ni = ring_index(grid, hidden_radius, near)
    off = ring_offsets(hidden_radius, near)
    d = np.hypot(off[:, 0], off[:, 1])
    w = np.where(ni >= 0, 1.0 / np.maximum(d[None, :], 1e-6) ** 2, 0.0).astype(np.float32)
    fi = ring_index(grid, near, far)
    ones = np.ones(n, bool)
    return ScaleContext(stats.scale, stats, np.asarray(cell_client), grid.lat[grid.rows], grid.lon[grid.cols], ni, w, fi,
                        ones if target_ok is None else np.asarray(target_ok, bool), ones if read_ok is None else np.asarray(read_ok, bool))


# ------------------------------------------------------------------------------------------------ helpers
def anomaly(total: np.ndarray, clim: np.ndarray) -> np.ndarray:
    """log1p(total) - log1p(climatological mean): a ratio-like anomaly that is defined for dry periods."""
    return np.log1p(np.clip(total, 0, None)) - np.log1p(np.clip(clim, 0, None))


def _gather(a: np.ndarray, idx: np.ndarray) -> np.ndarray:
    padded = np.concatenate([a, np.full((a.shape[0], 1), np.nan, a.dtype)], axis=1)
    return padded[:, idx]                                  # index -1 picks the NaN column


def lagged_totals(periods: Periods, prev: Optional[Periods]) -> np.ndarray:
    """The cell's own previous period total: the previous period of the same year, or the last of the previous year."""
    out = np.full(periods.total.shape, np.nan, np.float32)
    if periods.total.shape[0] > 1:
        out[1:] = periods.total[:-1]
    if prev is not None and prev.scale == periods.scale and prev.total.shape == periods.total.shape:
        out[0] = prev.total[-1]
    return out


def _phase(P: int) -> np.ndarray:
    if P <= 1:
        return np.zeros((P, 2), np.float32)
    ang = 2 * np.pi * np.arange(P) / P
    return np.stack([np.sin(ang), np.cos(ang)], axis=1).astype(np.float32)


def neighbour_features(ctx: ScaleContext, periods: Periods, prev: Optional[Periods], read_ok: Optional[np.ndarray] = None):
    """(X (P, n, F), anomaly (P, n), n_near (P, n)). The target's own value is never an input; ``read_ok`` hides cells."""
    clim = ctx.stats.clim_mean
    an = anomaly(periods.total, clim)
    an_read = an if read_ok is None else np.where(read_ok[None, :], an, np.nan)
    near = _gather(an_read, ctx.near_idx)                                   # (P, n, K1)
    far = _gather(an_read, ctx.far_idx)
    fin = np.isfinite(near)
    n_near = fin.sum(axis=2).astype(np.float32)
    w = np.where(fin, ctx.near_w[None], 0.0)
    wsum = w.sum(axis=2)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        near_med = np.nanmedian(near, axis=2)
        far_med = np.nanmedian(far, axis=2)
        near_w = np.where(wsum > 0, np.nansum(np.where(fin, near, 0.0) * w, axis=2) / np.where(wsum > 0, wsum, 1.0), np.nan)
    lag = lagged_totals(periods, prev)
    own_lag = anomaly(lag, np.roll(clim, 1, axis=0) if clim.shape[0] > 1 else clim)
    P, n = an.shape
    ph = _phase(P)
    X = np.stack([near_med, near_w, n_near, far_med, own_lag, ctx.stats.normalize(clim),
                  np.broadcast_to(ph[:, :1], (P, n)), np.broadcast_to(ph[:, 1:], (P, n)),
                  np.broadcast_to(ctx.lat[None, :], (P, n)), np.broadcast_to(ctx.lon[None, :], (P, n))], axis=2).astype(np.float32)
    return X, an, n_near


def _client_spread(resid: np.ndarray, valid: np.ndarray, col_client: np.ndarray, cell_client: np.ndarray,
                   floor: float = MIN_SPREAD) -> np.ndarray:
    """(P, n) robust spread (1.4826 x MAD) of ``resid`` (P, M) pooled per (period, client). ``col_client`` is the client of each
    of the M columns; ``cell_client`` (n,) says which client's spread each of the n cells gets."""
    P = resid.shape[0]
    out = np.full((P, cell_client.size), floor, np.float32)
    for c in np.unique(cell_client):
        cols = col_client == c
        tgt = cell_client == c
        for p in range(P):
            r = resid[p, cols][valid[p, cols]]
            if r.size >= 10:
                out[p, tgt] = max(floor, 1.4826 * float(np.median(np.abs(r - np.median(r)))))
    return out


# ------------------------------------------------------------------------------------------------ scorers
class ScaleScorer:
    name = "base"
    complexity = 0

    def fit(self, train: Dict[int, Periods], ctx: ScaleContext, seed: int = 0) -> "ScaleScorer":
        raise NotImplementedError

    def score(self, periods: Periods, prev: Optional[Periods], ctx: ScaleContext) -> np.ndarray:
        raise NotImplementedError


class GammaZeroScorer(ScaleScorer):
    """Zero probability plus a gamma fitted to the positive totals of each cell and period (documented practice for
    totals that can be zero). Score = -log10 of the two-sided tail probability under that mixed distribution."""
    name = "gamma_zero"
    complexity = 0

    def fit(self, train, ctx, seed=0):
        years = sorted(train)
        stack = np.stack([train[y].total for y in years], axis=0)             # (Y, P, n)
        fin = np.isfinite(stack)
        zero = fin & (stack <= ZERO_MM)
        pos = fin & (stack > ZERO_MM)
        nv = fin.sum(axis=0)
        self.p0 = (zero.sum(axis=0) + 0.5) / (nv + 1.0)
        npos = pos.sum(axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            mean_pos = np.where(npos > 0, np.nansum(np.where(pos, stack, 0.0), axis=0) / np.maximum(npos, 1), np.nan)
            ratio = np.where(pos, stack / mean_pos[None], np.nan)             # mean of the ratios is 1 per cell and period
        P, n = mean_pos.shape
        shape = np.full((P, n), 2.0, np.float32)
        for c in np.unique(ctx.cell_client):
            sel = ctx.cell_client == c
            for p in range(P):
                r = ratio[:, p, sel]
                r = r[np.isfinite(r)]
                if r.size >= 10 and r.var() > 0:
                    shape[p, sel] = float(np.clip(1.0 / r.var(), 0.3, 100.0))
        self.shape = shape
        self.scale = (mean_pos / shape).astype(np.float32)
        return self

    def score(self, periods, prev, ctx):
        y = periods.total
        out = np.full(y.shape, np.nan, np.float32)
        ok = np.isfinite(y) & np.isfinite(self.scale)
        zero = ok & (y <= ZERO_MM)
        posm = ok & (y > ZERO_MM)
        out[zero] = -np.log10(np.clip(self.p0[zero], 1e-12, 1.0))
        cdf = sps.gamma.cdf(np.where(posm, y, 1.0), a=self.shape, scale=np.where(np.isfinite(self.scale), self.scale, 1.0))
        F = self.p0 + (1.0 - self.p0) * cdf
        tail = 2.0 * np.minimum(F, 1.0 - F)
        out[posm] = -np.log10(np.clip(tail[posm], 1e-12, 1.0))
        out[~periods.valid] = np.nan
        return out


class LooResidualScorer(ScaleScorer):
    """Leave-one-out neighbour residual: predict the cell's anomaly as the median of its neighbours' anomalies (target and hidden
    disc left out); score = |residual| / robust spread of training-year residuals. The spec's "ratio cut of 3" is applied when
    thresholds are chosen. Kriging is NOT IMPLEMENTED."""
    name = "loo_median"
    complexity = 1
    default_cut = 3.0

    def fit(self, train, ctx, seed=0):
        res, ok = [], []
        for y in sorted(train):
            X, an, n_near = neighbour_features(ctx, train[y], None, ctx.read_ok)
            pred = X[:, :, 0]                                   # median of the neighbours' anomalies
            r = an - pred
            good = np.isfinite(r) & (n_near >= MIN_NEIGHBOURS) & ctx.target_ok[None, :]
            res.append(r)
            ok.append(good)
        r = np.stack(res, axis=0)                                                            # (Y, P, n)
        g = np.stack(ok, axis=0)
        Y, P, n = r.shape
        self.spread = _client_spread(np.moveaxis(r, 0, 1).reshape(P, Y * n), np.moveaxis(g, 0, 1).reshape(P, Y * n),
                                     np.tile(ctx.cell_client, Y), ctx.cell_client)
        return self

    def score(self, periods, prev, ctx):
        X, an, n_near = neighbour_features(ctx, periods, prev)
        r = an - X[:, :, 0]
        out = np.abs(r) / self.spread
        out[(n_near < MIN_NEIGHBOURS) | ~periods.valid] = np.nan
        return out.astype(np.float32)


class _RegressionScorer(ScaleScorer):
    max_rows = 250_000

    def make_model(self, seed: int):
        raise NotImplementedError

    def _prep(self, X: np.ndarray, fit: bool = False) -> np.ndarray:
        return X

    def fit(self, train, ctx, seed=0):
        years = sorted(train)
        rng = np.random.default_rng(seed)
        n_fit = max(1, int(np.ceil(0.8 * len(years)))) if len(years) > 1 else 1
        fit_years, spread_years = years[:n_fit], (years[n_fit:] or years[-1:])
        rows_X, rows_y = [], []
        per_year: Dict[int, tuple] = {}
        for y in years:
            X, an, n_near = neighbour_features(ctx, train[y], train.get(y - 1), ctx.read_ok)
            good = np.isfinite(an) & (n_near >= MIN_NEIGHBOURS) & ctx.target_ok[None, :]
            per_year[y] = (X, an, good)
        for y in fit_years:
            X, an, good = per_year[y]
            rows_X.append(X[good])
            rows_y.append(an[good])
        Xf, yf = np.concatenate(rows_X), np.concatenate(rows_y)
        if Xf.shape[0] > self.max_rows:
            pick = rng.choice(Xf.shape[0], self.max_rows, replace=False)
            Xf, yf = Xf[pick], yf[pick]
        if Xf.shape[0] < 50:
            raise ValueError(f"only {Xf.shape[0]} usable training rows for {self.name}; not enough to fit")
        self._prep(Xf, fit=True)
        self.model = self.make_model(seed).fit(self._prep(Xf), yf)
        res, ok = [], []
        for y in spread_years:                                   # residual spread measured on years the model did not fit
            X, an, good = per_year[y]
            r = np.full(an.shape, np.nan, np.float32)
            r[good] = an[good] - self.model.predict(self._prep(X[good]))
            res.append(r)
            ok.append(good)
        Y, P, n = len(res), res[0].shape[0], res[0].shape[1]
        r, g = np.stack(res), np.stack(ok)
        self.spread = _client_spread(np.moveaxis(r, 0, 1).reshape(P, Y * n), np.moveaxis(g, 0, 1).reshape(P, Y * n),
                                     np.tile(ctx.cell_client, Y), ctx.cell_client)
        return self

    def score(self, periods, prev, ctx):
        X, an, n_near = neighbour_features(ctx, periods, prev)
        good = np.isfinite(an) & (n_near >= MIN_NEIGHBOURS) & periods.valid
        out = np.full(an.shape, np.nan, np.float32)
        if good.any():
            pred = self.model.predict(self._prep(X[good]))
            r = np.abs(an[good] - pred)
            out[good] = r / self.spread[good]
        return out


class GbmNeighbourScorer(_RegressionScorer):
    """Pooled gradient-boosted regression of the cell's anomaly from neighbour, own-lag, climate and position features.
    No rainfall-QC precedent was found for this; it is an experiment kept only if it beats the baselines on validation."""
    name = "gbm_neighbour"
    complexity = 2

    def make_model(self, seed):
        return HistGradientBoostingRegressor(max_iter=150, learning_rate=0.08, max_leaf_nodes=15, random_state=seed)


class MlpNeighbourScorer(_RegressionScorer):
    """Small pooled MLP on the same features (scikit-learn; not the zero-inflated Gamma head named in the spec)."""
    name = "mlp_neighbour"
    complexity = 3

    def make_model(self, seed):
        return MLPRegressor(hidden_layer_sizes=(32, 16), max_iter=80, early_stopping=True, random_state=seed)

    def _prep(self, X, fit=False):
        if fit:
            Z = np.where(np.isfinite(X), X, np.nan)
            self._mu = np.nanmean(Z, axis=0)
            self._sd = np.nanstd(Z, axis=0) + 1e-6
            return X
        return np.nan_to_num((X - self._mu) / self._sd, nan=0.0)


CANDIDATES: Dict[str, type] = {c.name: c for c in (GammaZeroScorer, LooResidualScorer, GbmNeighbourScorer, MlpNeighbourScorer)}


def make_scorer(name: str) -> ScaleScorer:
    if name not in CANDIDATES:
        raise KeyError(f"unknown scorer {name!r}; choose from {sorted(CANDIDATES)}")
    return CANDIDATES[name]()
