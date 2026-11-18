"""Decadal scale: change-point tests on a cell's yearly series against its neighbours. Tests, not trained models.

STATUS: new, unit-tested on generated series only; nothing has run on real RF25. Spec: docs/qc-multires-pipeline-spec.md section 4.

The series tested is the cell's yearly anomaly minus the median of its neighbours' anomalies (a ratio test in log space, so a step in
the cell that its neighbours do not share shows up). Two classical tests of a single shift at an unknown year are given:

  ``snht``     the standard normal homogeneity statistic T = max_k [ k * mean(z[:k])**2 + (n-k) * mean(z[k:])**2 ] on the standardised series;
  ``pettitt``  the Pettitt rank statistic K = max_k |U_k|.

Both take the maximum over every possible break year, so their critical values must be the "maximal" ones. They are set here by
SIMULATION on break-free series of the same length (``simulated_critical``), as the research note says published documents give no
ready threshold for interpolated gridded rainfall. RF25 is interpolated from shared gauges and changing station density, so a detected
break means "network or sensor change, not distinguishable": it is never attributed to a cause here.
"""

from __future__ import annotations

import warnings
from typing import Callable, Dict, Optional, Sequence

import numpy as np

MIN_YEARS = 15
TESTS = ("snht", "pettitt")


def snht(z: np.ndarray):
    """(statistic, break index k) for one series; the break is between index k-1 and k. NaN-free input."""
    z = np.asarray(z, float)
    n = z.size
    sd = z.std(ddof=1)
    if n < 4 or sd == 0:
        return 0.0, None
    y = (z - z.mean()) / sd
    cs = np.cumsum(y)
    k = np.arange(1, n)
    m1 = cs[:-1] / k
    m2 = (cs[-1] - cs[:-1]) / (n - k)
    t = k * m1 ** 2 + (n - k) * m2 ** 2
    i = int(np.argmax(t))
    return float(t[i]), int(k[i])


def pettitt(z: np.ndarray):
    """(statistic K, break index k) for one series."""
    z = np.asarray(z, float)
    n = z.size
    if n < 4:
        return 0.0, None
    ranks = np.argsort(np.argsort(z)) + 1.0
    u = 2.0 * np.cumsum(ranks)[:-1] - (np.arange(1, n)) * (n + 1.0)
    i = int(np.argmax(np.abs(u)))
    return float(np.abs(u[i])), int(i + 1)


_STAT: Dict[str, Callable] = {"snht": snht, "pettitt": pettitt}


def simulated_critical(test: str, n_years: int, alpha: float = 0.01, n_sim: int = 4000, rng: Optional[np.random.Generator] = None) -> float:
    """The (1 - alpha) quantile of the statistic on break-free standard normal series of ``n_years`` values."""
    if test not in _STAT:
        raise ValueError(f"test must be one of {TESTS}")
    if n_years < MIN_YEARS:
        raise ValueError(f"need at least {MIN_YEARS} years for a break test, got {n_years}")
    if not 0 < alpha < 0.5:
        raise ValueError("alpha must be in (0, 0.5)")
    rng = rng or np.random.default_rng(0)
    f = _STAT[test]
    stats = np.array([f(rng.normal(size=n_years))[0] for _ in range(n_sim)])
    return float(np.quantile(stats, 1.0 - alpha))


def neighbour_difference(yearly_anomaly: np.ndarray, neighbour_idx: np.ndarray) -> np.ndarray:
    """(Y, n) yearly anomalies (for example log1p total minus log1p climatology) -> (Y, n) cell minus the median of its neighbours.
    ``neighbour_idx`` is (n, K) with -1 for no neighbour. NaN where fewer than 3 neighbours have a value."""
    padded = np.concatenate([yearly_anomaly, np.full((yearly_anomaly.shape[0], 1), np.nan, yearly_anomaly.dtype)], axis=1)
    nb = padded[:, neighbour_idx]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(nb, axis=2)
    ok = np.isfinite(nb).sum(axis=2) >= 3
    return np.where(ok, yearly_anomaly - med, np.nan)


def detect_breaks(diff: np.ndarray, years: Sequence[int], test: str = "snht", alpha: float = 0.01,
                  critical: Optional[float] = None, rng: Optional[np.random.Generator] = None) -> Dict:
    """Run ``test`` on every cell's series ``diff[:, i]`` (Y, n). Cells with missing years are skipped, not filled."""
    if test not in _STAT:
        raise ValueError(f"test must be one of {TESTS}")
    Y, n = diff.shape
    if len(years) != Y:
        raise ValueError("years must have one entry per row of diff")
    crit = simulated_critical(test, Y, alpha, rng=rng) if critical is None else float(critical)
    f = _STAT[test]
    stat = np.full(n, np.nan)
    brk = np.full(n, -1, int)
    shift = np.full(n, np.nan)
    for i in range(n):
        z = diff[:, i]
        if not np.isfinite(z).all():
            continue
        s, k = f(z)
        stat[i] = s
        if k is not None:
            brk[i] = int(years[k])
            shift[i] = float(z[k:].mean() - z[:k].mean())
    flagged = np.isfinite(stat) & (stat > crit)
    return {"test": test, "alpha": alpha, "critical": crit, "statistic": stat, "break_year": np.where(flagged, brk, -1),
            "shift": np.where(flagged, shift, np.nan), "flagged": flagged, "tested": np.isfinite(stat),
            "meaning": "network or sensor change, not distinguishable; RF25 is interpolated from gauges whose number changed over time"}


def step_power(n_years: int, steps_in_sd: Sequence[float], test: str = "snht", alpha: float = 0.01, n_sim: int = 500,
               rng: Optional[np.random.Generator] = None) -> Dict[float, float]:
    """Share of simulated series with a step of the given size (in standard deviations) at a random year that the test flags, with the
    critical value set on break-free series. The step is injected, so this is a SYNTHETIC power estimate."""
    rng = rng or np.random.default_rng(0)
    crit = simulated_critical(test, n_years, alpha, rng=rng)
    f = _STAT[test]
    out = {}
    for s in steps_in_sd:
        hit = 0
        for _ in range(n_sim):
            z = rng.normal(size=n_years)
            k = int(rng.integers(n_years // 4, n_years - n_years // 4))
            z[k:] += s
            hit += f(z)[0] > crit
        out[float(s)] = hit / n_sim
    return out
