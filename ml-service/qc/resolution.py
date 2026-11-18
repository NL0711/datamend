"""Time-resolution layer: daily rainfall blocks -> monthly, seasonal and yearly periods, plus decades.

STATUS: new, unit-tested on generated arrays only. No model uses it yet and nothing has run on real RF25.

Why it exists. The daily components (``qc.models``, ``qc.trained``) see days. The planned coarser models need
the same data aggregated the same way for every caller, with the same leakage rules, and they need synthetic
faults whose labels say whether the fault is still visible at that scale. This module is that one place.

Interface (everything a caller must know):

  ``aggregate(block, year, scale)``      (T, n_land) mm for ONE calendar year -> ``Periods``
  ``aggregate_labels(clean, corrupted, day_labels, year, scale)`` -> ``PeriodLabels``
  ``fit_scale_stats(periods_by_year, years, split, cell_client, scale)`` -> ``ScaleStats`` (training years only)
  ``ScaleStats.zscore(periods)``         how far each period total is from the cell's own climatology
  ``corrupt_periods(periods, rng, rate)``  faults that only exist at period level (a whole month scaled or lost)
  ``yearly_to_decades(years, totals)``   decade means; the decadal scale is tested, not trained

Rules that hold everywhere:

* Scales: ``daily`` (identity), ``monthly`` (12 periods), ``seasonal`` (one period, June-September by default;
  the June-September season is the meaningful rain unit in India), ``yearly`` (one period).
* A period total is NEVER filled. If a cell has too few finite days in a period (``min_valid_frac``, default all
  days) its total, wet-day count and maximum are NaN.
* A block whose length is not the number of days of that calendar year is refused, not padded or cut.
* Fitted statistics may use training years only (``qc.splits.assert_years_allowed``).
* A fault is labelled at a scale only if it actually changed that period's total. A fault that changes days but
  not the total is "present" but not "visible" at that scale; both are reported.
* Faults made here are SYNTHETIC stress tests, not real QC labels.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from qc.splits import Split, assert_years_allowed

SCALES: Tuple[str, ...] = ("daily", "monthly", "seasonal", "yearly")
SEASON_MONTHS: Tuple[int, ...] = (6, 7, 8, 9)       # June-September, months numbered 1-12
WET_MM = 0.1
PERIOD_KINDS: Tuple[str, ...] = ("scale", "dropout")


def _check_scale(scale: str) -> None:
    if scale not in SCALES:
        raise ValueError(f"unknown scale {scale!r}; choose from {SCALES}")


def n_periods(scale: str) -> int:
    """Periods per calendar year; the daily scale has one per day, so it has no fixed number."""
    _check_scale(scale)
    if scale == "daily":
        raise ValueError("the daily scale has one period per day; use the block length")
    return {"monthly": 12, "seasonal": 1, "yearly": 1}[scale]


def days_in_year(year: int) -> int:
    return 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365


def period_ids(year: int, n_days: int, scale: str, season: Sequence[int] = SEASON_MONTHS) -> np.ndarray:
    """(n_days,) int: the period each day belongs to, -1 for days outside every period (seasonal scale only)."""
    _check_scale(scale)
    if n_days != days_in_year(year):
        raise ValueError(f"year {year} has {days_in_year(year)} days but the block has {n_days}; refusing to align it")
    if scale == "daily":
        return np.arange(n_days, dtype=np.int32)
    if scale == "yearly":
        return np.zeros(n_days, np.int32)
    days = np.datetime64(f"{year}-01-01") + np.arange(n_days)
    month = days.astype("datetime64[M]").astype(int) % 12 + 1          # 1..12
    if scale == "monthly":
        return (month - 1).astype(np.int32)
    return np.where(np.isin(month, list(season)), 0, -1).astype(np.int32)


@dataclass
class Periods:
    """Period summaries of one year, per land cell. Axis 0 is the period, axis 1 the land cell."""
    scale: str
    year: int
    total: np.ndarray        # (P, n_land) mm, NaN where the period is not valid for that cell
    wet_days: np.ndarray     # (P, n_land) float, NaN where not valid
    max_mm: np.ndarray       # (P, n_land) largest daily value, NaN where not valid
    n_days: np.ndarray       # (P,) number of days in each period
    valid: np.ndarray        # (P, n_land) bool

    def copy(self) -> "Periods":
        return Periods(self.scale, self.year, self.total.copy(), self.wet_days.copy(), self.max_mm.copy(),
                       self.n_days.copy(), self.valid.copy())


def aggregate(block: np.ndarray, year: int, scale: str, min_valid_frac: float = 1.0,
              season: Sequence[int] = SEASON_MONTHS, wet_mm: float = WET_MM) -> Periods:
    """Summarise one calendar year of daily rainfall. ``block`` is (days, n_land) mm; NaN is missing."""
    if block.ndim != 2:
        raise ValueError("block must be (days, n_land)")
    if not 0.0 < min_valid_frac <= 1.0:
        raise ValueError("min_valid_frac must be in (0, 1]")
    ids = period_ids(year, block.shape[0], scale, season)
    n_cells = block.shape[1]
    P = block.shape[0] if scale == "daily" else n_periods(scale)
    total = np.full((P, n_cells), np.nan, np.float32)
    wet = np.full((P, n_cells), np.nan, np.float32)
    peak = np.full((P, n_cells), np.nan, np.float32)
    valid = np.zeros((P, n_cells), bool)
    n_days = np.zeros(P, np.int32)
    for p in range(P):
        sel = ids == p
        n_days[p] = int(sel.sum())
        if n_days[p] == 0:
            continue
        sub = block[sel]
        fin = np.isfinite(sub)
        ok = fin.any(axis=0) & (fin.mean(axis=0) >= min_valid_frac)
        valid[p] = ok
        if not ok.any():
            continue
        z = np.where(fin, sub, 0.0)
        total[p, ok] = z.sum(axis=0, dtype=np.float64)[ok]
        wet[p, ok] = ((z > wet_mm) & fin).sum(axis=0)[ok]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            peak[p, ok] = np.nanmax(np.where(fin, sub, np.nan), axis=0)[ok]
    return Periods(scale, int(year), total, wet, peak, n_days, valid)


@dataclass
class PeriodLabels:
    """Where injected daily faults show up at one scale."""
    scale: str
    present: np.ndarray      # (P, n_land) bool: at least one faulty day falls in the period
    visible: np.ndarray      # (P, n_land) bool: ... and the period total changed by more than the tolerance
    fault_days: np.ndarray   # (P, n_land) int: number of faulty days in the period


def aggregate_labels(clean: np.ndarray, corrupted: np.ndarray, day_labels: np.ndarray, year: int, scale: str,
                     rel_tol: float = 0.01, abs_tol_mm: float = 0.5, min_valid_frac: float = 1.0,
                     season: Sequence[int] = SEASON_MONTHS) -> PeriodLabels:
    """Turn daily fault labels into period labels. ``visible`` needs the total to move by more than
    ``max(abs_tol_mm, rel_tol * clean total)``, so a fault that does not change the period is not counted as detectable."""
    if not (clean.shape == corrupted.shape == day_labels.shape):
        raise ValueError("clean, corrupted and day_labels must have the same shape")
    ids = period_ids(year, clean.shape[0], scale, season)
    c = aggregate(clean, year, scale, min_valid_frac, season)
    k = aggregate(corrupted, year, scale, min_valid_frac, season)
    P = c.total.shape[0]
    days = np.zeros(c.total.shape, np.int32)
    for p in range(P):
        sel = ids == p
        if sel.any():
            days[p] = day_labels[sel].sum(axis=0)
    both = c.valid & k.valid
    diff = np.abs(np.nan_to_num(k.total) - np.nan_to_num(c.total))
    tol = np.maximum(abs_tol_mm, rel_tol * np.abs(np.nan_to_num(c.total)))
    present = days > 0
    visible = present & both & (diff > tol)
    return PeriodLabels(scale, present, visible, days)


# ------------------------------------------------------------------------------------------- statistics
@dataclass
class ScaleStats:
    """Statistics of period totals fitted on training years only."""
    scale: str
    years: Tuple[int, ...]
    clim_mean: np.ndarray     # (P, n_land) mean total over the training years
    clim_spread: np.ndarray   # (P, n_land) robust spread (1.4826 x MAD), floored
    norm_scale: np.ndarray    # (n_land,) per-client scale of log1p(total): the 99.9th percentile of training totals

    def normalize(self, total: np.ndarray) -> np.ndarray:
        """log1p(total) / scale. Rescales only; negative totals are floored at 0 and large ones are never clipped."""
        return np.log1p(np.clip(total, 0, None)) / self.norm_scale

    def zscore(self, periods: Periods) -> np.ndarray:
        """(P, n_land): (total - climatological mean) / spread. NaN where the period is not valid."""
        if periods.scale != self.scale:
            raise ValueError(f"stats are for scale {self.scale!r}, periods are {periods.scale!r}")
        return (periods.total - self.clim_mean) / self.clim_spread

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, scale=np.array(self.scale), years=np.array(self.years), clim_mean=self.clim_mean,
                            clim_spread=self.clim_spread, norm_scale=self.norm_scale)

    @classmethod
    def load(cls, path: Path) -> "ScaleStats":
        z = np.load(path)
        return cls(str(z["scale"]), tuple(int(y) for y in z["years"]), z["clim_mean"], z["clim_spread"], z["norm_scale"])


def fit_scale_stats(periods_by_year: Dict[int, Periods], years: Sequence[int], split: Split, cell_client: np.ndarray,
                    scale: str, wet_quantile: float = 99.9, min_rel_spread: float = 0.05,
                    min_spread_mm: float = 1.0) -> ScaleStats:
    """Fit on ``years`` (must all be training years). ``cell_client`` is (n_land,) client id of each land cell."""
    _check_scale(scale)
    if scale == "daily":
        raise ValueError("daily statistics are fitted by qc.stats.fit_train_stats")
    assert_years_allowed("scale statistics", years, split, "train")
    if not years:
        raise ValueError("no training years given")
    for y in years:
        if periods_by_year[y].scale != scale:
            raise ValueError(f"year {y} holds scale {periods_by_year[y].scale!r}, expected {scale!r}")
    stack = np.stack([periods_by_year[y].total for y in years], axis=0)           # (Y, P, n)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(stack, axis=0)
        med = np.nanmedian(stack, axis=0)
        mad = np.nanmedian(np.abs(stack - med[None]), axis=0)
    spread = np.maximum(1.4826 * mad, np.maximum(min_rel_spread * np.abs(mean), min_spread_mm))
    spread = np.where(np.isfinite(spread), spread, min_spread_mm)
    n_land = cell_client.size
    norm = np.ones(n_land, np.float32)
    for c in sorted(int(v) for v in np.unique(cell_client)):
        sel = cell_client == c
        vals = stack[:, :, sel]
        vals = vals[np.isfinite(vals) & (vals > WET_MM)]
        if vals.size == 0:
            raise ValueError(f"client {c} has no positive period total in the training years")
        norm[sel] = float(np.log1p(np.percentile(vals, wet_quantile)))
    return ScaleStats(scale, tuple(int(y) for y in years), mean.astype(np.float32), spread.astype(np.float32), norm)


# ------------------------------------------------------------------------- faults that exist at period level
@dataclass
class PeriodFaults:
    """Synthetic faults on period summaries. ``kind`` is an index into ``PERIOD_KINDS``, -1 where none."""
    labels: np.ndarray       # (P, n_land) bool: the total actually changed
    kind: np.ndarray         # (P, n_land) int8
    factor: np.ndarray       # (P, n_land) float32: corrupted / original total (0 for a dropout), NaN where none


def corrupt_periods(periods: Periods, rng: np.random.Generator, rate: float = 0.01,
                    kinds: Sequence[str] = PERIOD_KINDS) -> Tuple[Periods, PeriodFaults]:
    """Single-cell faults on whole periods: ``scale`` multiplies a period's total (and largest day) by a factor drawn
    from 0.4-0.8 or 1.25-2.5; ``dropout`` sets it to zero. A fault is labelled only if the total changed, so a
    dropout on a period that was already dry is not a fault. The input is not modified. SYNTHETIC."""
    bad = [k for k in kinds if k not in PERIOD_KINDS]
    if bad or not kinds:
        raise ValueError(f"unknown or empty fault kinds {list(kinds)}; choose from {PERIOD_KINDS}")
    if not 0.0 <= rate <= 1.0:
        raise ValueError("rate must be in [0, 1]")
    out = periods.copy()
    shape = periods.total.shape
    pick = periods.valid & (rng.random(shape) < rate)
    which = np.asarray(rng.integers(0, len(kinds), shape))
    mag = np.where(rng.random(shape) < 0.5, rng.uniform(0.4, 0.8, shape), rng.uniform(1.25, 2.5, shape))
    factor = np.full(shape, np.nan, np.float32)
    kind = np.full(shape, -1, np.int8)
    for i, name in enumerate(kinds):
        sel = pick & (which == i)
        f = np.zeros(shape, np.float32) if name == "dropout" else mag.astype(np.float32)
        factor[sel] = f[sel]
        kind[sel] = PERIOD_KINDS.index(name)
    hit = pick
    out.total[hit] = periods.total[hit] * factor[hit]
    out.max_mm[hit] = periods.max_mm[hit] * factor[hit]
    dropped = hit & (factor == 0)
    out.wet_days[dropped] = 0.0
    changed = hit & (np.abs(out.total - periods.total) > 1e-6)
    kind = np.where(changed, kind, -1).astype(np.int8)
    factor = np.where(changed, factor, np.nan).astype(np.float32)
    return out, PeriodFaults(changed, kind, factor)


# ----------------------------------------------------------------------------------------------- decades
def yearly_to_decades(years: Sequence[int], yearly_total: np.ndarray, min_years: int = 10) -> Tuple[np.ndarray, np.ndarray]:
    """Mean yearly total per calendar decade (1951-1960 is not a decade here: decades are 1950-1959, 1960-1969, ...).
    ``yearly_total`` is (len(years), n_land). A decade with fewer than ``min_years`` finite years for a cell gives NaN
    for that cell; missing years are never interpolated. Returns (decade start years, (D, n_land) means)."""
    ys = np.asarray(years, int)
    if yearly_total.shape[0] != ys.size:
        raise ValueError("yearly_total must have one row per year")
    if min_years < 1:
        raise ValueError("min_years must be at least 1")
    starts = np.array(sorted({int(y) // 10 * 10 for y in ys}), int)
    means = np.full((starts.size, yearly_total.shape[1]), np.nan, np.float32)
    for i, d in enumerate(starts):
        sel = (ys >= d) & (ys < d + 10)
        sub = yearly_total[sel]
        n_ok = np.isfinite(sub).sum(axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            m = np.nanmean(sub, axis=0)
        means[i] = np.where(n_ok >= min_years, m, np.nan)
    return starts, means
