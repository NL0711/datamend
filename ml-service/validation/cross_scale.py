"""Cross-scale consistency rules for the rule engine (deterministic; no neural network involved).

Checks that daily values reconcile with aggregates at other scales:
  monthly_total_mismatch / pentad_total_mismatch   daily sum differs from a provided total beyond tolerance
  daily_exceeds_period_total                       a single day is larger than the period total it belongs to
  monthly_aggregate_out_of_range                   a monthly sum is outside the cell's climatological range
  period_incomplete                                missing days make a provided total unreconcilable (low severity)

Every flag carries a name and a numeric severity in [0, 1]. Provided totals, pentads and climatological
ranges are optional: with none of them, no cross-scale flag can fire (nothing is invented).

Assumptions to confirm for real data: a pentad is ``(day_of_year - 1) // 5`` (73 per year, a leap-day
folds into a 74th index), and daily/period totals use the same rain-day convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


@dataclass
class RuleFlag:
    name: str
    severity: float          # 0-1
    start: int               # index into the daily series
    end: int                 # inclusive
    detail: Dict = field(default_factory=dict)


def _severity(diff: float, ref: float, tol_abs: float) -> float:
    return float(np.clip(abs(diff) / max(abs(ref), 10.0 * tol_abs), 0.0, 1.0))


def _check_period(flags: List[RuleFlag], name: str, key, idx: np.ndarray, daily: np.ndarray, provided: float,
                  tol_rel: float, tol_abs: float) -> None:
    seg = daily[idx]
    start, end = int(idx[0]), int(idx[-1])
    if np.isnan(seg).any():
        flags.append(RuleFlag("period_incomplete", 0.2, start, end,
                              {"period": str(key), "missing_days": int(np.isnan(seg).sum())}))
        return
    total = float(seg.sum())
    tol = max(tol_abs, tol_rel * abs(provided))
    if abs(total - provided) > tol:
        flags.append(RuleFlag(name, _severity(total - provided, provided, tol_abs), start, end,
                              {"period": str(key), "daily_sum": total, "provided": float(provided), "tolerance": tol}))
    over = np.flatnonzero(seg > provided + tol)
    for j in over:
        flags.append(RuleFlag("daily_exceeds_period_total", 1.0, int(idx[j]), int(idx[j]),
                              {"period": str(key), "value": float(seg[j]), "provided_total": float(provided)}))


def cross_scale_flags(
    daily: np.ndarray,
    dates: pd.DatetimeIndex,
    monthly_totals: Optional[Dict[str, float]] = None,
    pentad_totals: Optional[Dict[Tuple[int, int], float]] = None,
    monthly_range: Optional[Dict[int, Tuple[float, float]]] = None,
    tol_rel: float = 0.05,
    tol_abs: float = 1.0,
) -> List[RuleFlag]:
    """Run the cross-scale rules on one daily series. ``monthly_totals`` is keyed ``"YYYY-MM"``,
    ``pentad_totals`` by ``(year, pentad_index)``, ``monthly_range`` by month number -> (low, high) mm."""
    daily = np.asarray(daily, float)
    dates = pd.DatetimeIndex(dates)
    if len(daily) != len(dates):
        raise ValueError("daily and dates must have the same length")
    flags: List[RuleFlag] = []
    month_key = dates.strftime("%Y-%m").to_numpy()
    for key in dict.fromkeys(month_key):
        idx = np.flatnonzero(month_key == key)
        if monthly_totals and key in monthly_totals:
            _check_period(flags, "monthly_total_mismatch", key, idx, daily, monthly_totals[key], tol_rel, tol_abs)
        if monthly_range and int(key[5:]) in monthly_range and not np.isnan(daily[idx]).any():
            lo, hi = monthly_range[int(key[5:])]
            total = float(daily[idx].sum())
            if total < lo or total > hi:
                ref = hi if total > hi else lo
                flags.append(RuleFlag("monthly_aggregate_out_of_range", _severity(total - ref, max(hi, 1.0), tol_abs),
                                      int(idx[0]), int(idx[-1]),
                                      {"period": key, "monthly_sum": total, "range": (float(lo), float(hi))}))
    if pentad_totals:
        pent = ((dates.dayofyear.to_numpy() - 1) // 5)
        for (year, p), provided in pentad_totals.items():
            idx = np.flatnonzero((dates.year.to_numpy() == year) & (pent == p))
            if idx.size:
                _check_period(flags, "pentad_total_mismatch", (year, p), idx, daily, provided, tol_rel, tol_abs)
    return flags


def monthly_clim_range(series: Sequence[Tuple[pd.DatetimeIndex, np.ndarray]], q: Tuple[float, float] = (0.01, 0.99)) -> Dict[int, Tuple[float, float]]:
    """Per-month (low, high) quantiles of monthly totals from the given (dates, daily) series.
    Pass **training-year** series only; complete months only."""
    by_month: Dict[int, List[float]] = {m: [] for m in range(1, 13)}
    for dates, daily in series:
        s = pd.Series(np.asarray(daily, float), index=pd.DatetimeIndex(dates))
        for (y, m), g in s.groupby([s.index.year, s.index.month]):
            if len(g) == g.index[0].days_in_month and not g.isna().any():
                by_month[m].append(float(g.sum()))
    return {m: (float(np.quantile(v, q[0])), float(np.quantile(v, q[1]))) for m, v in by_month.items() if len(v) >= 2}


def severity_per_day(flags: Sequence[RuleFlag], n: int) -> np.ndarray:
    """Max flag severity covering each day (0 where no flag applies); feeds the rule branch score."""
    out = np.zeros(n)
    for f in flags:
        out[f.start: f.end + 1] = np.maximum(out[f.start: f.end + 1], f.severity)
    return out
