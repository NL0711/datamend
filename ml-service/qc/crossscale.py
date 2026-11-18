"""Cross-scale fusion: put daily, monthly, seasonal and yearly scores on one scale and combine them.

STATUS: new, unit-tested on generated arrays only; no real run. Spec: docs/qc-multires-pipeline-spec.md section 6.

Each scale's score is standardised by a reference taken from CLEAN threshold-year data (``reference``: its 99.9th percentile), so
1.0 means "as extreme as the clean 99.9th percentile of that scale". A period score is aligned to days (``align_to_days``): every
day of a month carries that month's score. Combination is fixed and label-free (no fitting on synthetic faults):

  ``max``       the largest ratio; the scale that gave it is the DRIVER.
  ``noisy_or``  with the probability of a scale taken as 1 - 2**(-ratio), 1 - prod(1 - p) = 1 - 2**(-sum of ratios), so the fused
                score is the SUM of the ratios. The driver is still the scale with the largest ratio.

The coherent-extreme rule multiplies the fused score of cell-periods inside a protected genuine extreme (a spatially coherent heavy
group, ``qc.extremes``) by a factor below 1, so a real widespread event is less likely to be flagged. A learned fusion would be a
challenger that must beat this on 2016-2017; it is NOT IMPLEMENTED here.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from qc.resolution import SEASON_MONTHS, days_in_year, period_ids

MODES = ("max", "noisy_or")


def reference(clean_scores: np.ndarray, q: float = 99.9, min_count: int = 100) -> float:
    v = np.asarray(clean_scores, float)
    v = v[np.isfinite(v)]
    if v.size < min_count:
        raise ValueError(f"only {v.size} clean scores; need at least {min_count} to set a reference")
    ref = float(np.percentile(v, q))
    if not ref > 0:
        raise ValueError("the clean reference is not positive; the scores cannot be standardised")
    return ref


def align_to_days(period_scores: np.ndarray, year: int, scale: str, n_days: Optional[int] = None,
                  season: Sequence[int] = SEASON_MONTHS) -> np.ndarray:
    """(P, n) -> (T, n): each day takes the score of its period; days outside every period are NaN."""
    T = n_days if n_days is not None else days_in_year(year)
    ids = period_ids(year, T, scale, season)
    out = np.full((T, period_scores.shape[1]), np.nan, np.float32)
    ok = ids >= 0
    out[ok] = period_scores[ids[ok]]
    return out


@dataclass
class FusedScores:
    score: np.ndarray        # (T, n) float32, NaN where no scale scored the cell-day
    driver: np.ndarray       # (T, n) int8: index into ``names`` of the scale with the largest ratio, -1 none
    names: List[str]


def fuse_scales(parts: Dict[str, np.ndarray], refs: Dict[str, float], mode: str = "max",
                protected: Optional[np.ndarray] = None, protected_factor: float = 0.5) -> FusedScores:
    """``parts[name]`` are (T, n) scores already aligned to days. ``refs`` come from ``reference`` on clean threshold years."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if not parts or set(parts) != set(refs):
        raise ValueError("parts and refs must name the same, non-empty set of scales")
    if not 0.0 <= protected_factor <= 1.0:
        raise ValueError("protected_factor must be in [0, 1]")
    names = list(parts)
    shapes = {parts[k].shape for k in names}
    if len(shapes) != 1:
        raise ValueError(f"all scales must have the same (T, n) shape, got {sorted(shapes)}")
    ratios = np.stack([parts[k] / float(refs[k]) for k in names], axis=0).astype(np.float32)       # (S, T, n)
    anyv = np.isfinite(ratios).any(axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        score = np.nanmax(ratios, axis=0) if mode == "max" else np.nansum(ratios, axis=0)
        drv = np.argmax(np.where(np.isfinite(ratios), ratios, -np.inf), axis=0).astype(np.int8)
    score = np.where(anyv, score, np.nan).astype(np.float32)
    drv = np.where(anyv, drv, -1).astype(np.int8)
    if protected is not None:
        if protected.shape != score.shape:
            raise ValueError("protected must have the shape of the fused score")
        score = np.where(protected & anyv, score * protected_factor, score).astype(np.float32)
    return FusedScores(score, drv, names)
