"""Day-of-year normals of a cell from a daily history (mean and standard deviation per variable, 15-day circular smoothing),
and wet-day statistics for rainfall. Built once per cell and stored; nothing here is fitted to a model."""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Sequence

import numpy as np

VARIABLES = ("temperature", "humidity", "pressure")
WET_MM = 0.1                       # a wet day: more than this many millimetres
SMOOTH_DAYS = 15
MIN_YEARS = 10                     # fewer than this many years of data: no normals


class NormalsError(ValueError):
    pass


def doy_index(d: date) -> int:
    """0-based day of year; 29 February is index 59 of a leap year, so index 365 exists only in leap years."""
    return d.timetuple().tm_yday - 1


def _smooth(a: np.ndarray, size: int = SMOOTH_DAYS) -> np.ndarray:
    k = np.ones(size) / size
    pad = size // 2
    ext = np.concatenate([a[-pad:], a, a[:pad]])
    return np.convolve(ext, k, mode="valid")


def _fill_leap(a: np.ndarray) -> np.ndarray:
    """Index 365 (31 December of a leap year) is sparse; borrow index 364 if it has no data."""
    a = a.copy()
    if not np.isfinite(a[365]):
        a[365] = a[364]
    return a


def build_normals(history: Dict[str, Any], min_years: int = MIN_YEARS) -> Dict[str, Any]:
    """``history``: {"time": [ISO dates], "temperature": [...], "humidity": [...], "pressure": [...], "precipitation": [...]} (NaN allowed).
    Returns JSON-safe lists: per variable ``mean`` and ``sd`` (366 values), rainfall ``wet_p95``, ``wet_p99``, ``wet_fraction`` (366)."""
    days = [date.fromisoformat(t) for t in history["time"]]
    years = {d.year for d in days}
    if len(years) < min_years:
        raise NormalsError(f"only {len(years)} years of history; at least {min_years} are needed for normals")
    idx = np.array([doy_index(d) for d in days])
    out: Dict[str, Any] = {"years": [min(years), max(years)], "n_days": len(days)}
    for v in VARIABLES:
        x = np.asarray(history[v], dtype=float)
        mean, sd = np.full(366, np.nan), np.full(366, np.nan)
        for i in range(366):
            s = x[(idx == i) & np.isfinite(x)]
            if s.size >= 3:
                mean[i], sd[i] = s.mean(), s.std(ddof=1)
        mean, sd = _fill_leap(mean), _fill_leap(sd)
        if not np.isfinite(mean).all():
            raise NormalsError(f"{v}: some days of the year have no data")
        out[v] = {"mean": [round(float(m), 4) for m in _smooth(mean)],
                  "sd": [round(float(max(s, 1e-3)), 4) for s in np.sqrt(_smooth(np.nan_to_num(sd) ** 2))]}
    r = np.asarray(history["precipitation"], dtype=float)
    ok = np.isfinite(r)
    wet = r[ok & (r > WET_MM)]
    if wet.size < 50:
        out["rain"] = {"wet_p95": None, "wet_p99": None, "wet_fraction": [0.0] * 366}
    else:
        frac = np.zeros(366)
        for i in range(366):
            s = r[(idx == i) & ok]
            frac[i] = float((s > WET_MM).mean()) if s.size else 0.0
        out["rain"] = {"wet_p95": round(float(np.percentile(wet, 95)), 3), "wet_p99": round(float(np.percentile(wet, 99)), 3),
                       "wet_fraction": [round(float(f), 4) for f in _smooth(frac)]}
    return out


def normal_for(normals: Dict[str, Any], variable: str, d: date) -> Dict[str, float]:
    i = min(doy_index(d), 365)
    return {"mean": float(normals[variable]["mean"][i]), "sd": float(normals[variable]["sd"][i])}
