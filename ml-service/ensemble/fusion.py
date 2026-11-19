"""Label-free score normalization, fusion rules and clean-data threshold calibration.

No supervised stacking meta-model lives here. Every branch is normalized on its own against *clean*
reference data, so scores of different units become comparable without using anomaly labels:

- ``RankNormalizer``: percentile rank of a raw score within the clean reference distribution, in [0, 1].
- ``LikelihoodNormalizer``: temperature-scaled likelihood for the zero-inflated Gamma branch: surprise
  above the clean median, turned into a probability 1 - exp(-surprise / T), with T fit on clean data.

Fusion rules (all operate on normalized scores in [0, 1], one entry per active branch):
``mean_rank`` (mean of ranks), ``max``, ``prob_avg`` (mean of per-branch probabilities, using the
likelihood-normalized probability where a branch has one and its rank otherwise; ranks are only a proxy
for a probability, an [unvalidated] simplification), ``owa`` (ordered weighted average of the sorted scores).
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

log = logging.getLogger(__name__)

RULES: Tuple[str, ...] = ("mean_rank", "max", "prob_avg", "owa")
_MAX_REF = 100_000


class RankNormalizer:
    """Percentile rank against a clean reference sample (kept sorted, subsampled to bound memory)."""

    def __init__(self, ref: Optional[np.ndarray] = None):
        self.ref = ref

    def fit(self, clean: np.ndarray, valid: Optional[np.ndarray] = None, seed: int = 0) -> "RankNormalizer":
        v = np.asarray(clean, float).ravel()
        if valid is not None:
            v = v[np.asarray(valid, bool).ravel()]
        v = v[np.isfinite(v)]
        if v.size == 0:
            raise ValueError("RankNormalizer needs at least one clean score")
        if v.size > _MAX_REF:
            v = np.random.default_rng(seed).choice(v, _MAX_REF, replace=False)
        self.ref = np.sort(v)
        return self

    def transform(self, scores: np.ndarray) -> np.ndarray:
        s = np.asarray(scores, float)
        return np.searchsorted(self.ref, s.ravel(), side="right").reshape(s.shape) / self.ref.size


class LikelihoodNormalizer:
    """p = 1 - exp(-max(nll - median_clean, 0) / T), T = mean clean excess (floored)."""

    def __init__(self, ref: float = 0.0, temperature: float = 1.0):
        self.ref, self.temperature = ref, temperature

    def fit(self, clean_nll: np.ndarray, valid: Optional[np.ndarray] = None) -> "LikelihoodNormalizer":
        v = np.asarray(clean_nll, float).ravel()
        if valid is not None:
            v = v[np.asarray(valid, bool).ravel()]
        v = v[np.isfinite(v)]
        if v.size == 0:
            raise ValueError("LikelihoodNormalizer needs at least one clean score")
        self.ref = float(np.median(v))
        self.temperature = max(float(np.mean(np.maximum(v - self.ref, 0.0))), 1e-3)
        return self

    def transform(self, nll: np.ndarray) -> np.ndarray:
        return 1.0 - np.exp(-np.maximum(np.asarray(nll, float) - self.ref, 0.0) / self.temperature)


def owa_weights(k: int, orness: float = 0.7) -> np.ndarray:
    """Geometric OWA weights over scores sorted descending. orness 0.5 = mean, -> 1 = max, -> 0 = min."""
    a = float(np.clip(orness, 0.01, 0.99))
    r = (1.0 - a) / a
    w = r ** np.arange(k)
    return w / w.sum()


def fuse(ranks: Dict[str, np.ndarray], probs: Optional[Dict[str, np.ndarray]] = None, rule: str = "mean_rank",
         owa_orness: float = 0.7, owa_w: Optional[Sequence[float]] = None) -> np.ndarray:
    """Fuse normalized branch scores (each the same shape). Returns that shape, values in [0, 1]."""
    if rule not in RULES:
        raise ValueError(f"Unknown fusion rule {rule!r}; choose from {RULES}")
    if not ranks:
        raise ValueError("no active branches to fuse")
    names = list(ranks)
    if rule == "prob_avg":
        probs = probs or {}
        return np.mean([probs.get(n, ranks[n]) for n in names], axis=0)
    stack = np.stack([ranks[n] for n in names], axis=0)
    if rule == "mean_rank":
        return stack.mean(0)
    if rule == "max":
        return stack.max(0)
    w = np.asarray(owa_w, float) if owa_w is not None else owa_weights(len(names), owa_orness)
    if len(w) != len(names):
        raise ValueError(f"owa weights ({len(w)}) must match the number of active branches ({len(names)})")
    return (np.sort(stack, axis=0)[::-1] * w.reshape(-1, *[1] * (stack.ndim - 1))).sum(0)


def _events_per_1000(flag: np.ndarray) -> float:
    """Contiguous alarm runs per 1000 steps, counted within each window row."""
    d = np.diff(np.concatenate([np.zeros((flag.shape[0], 1), int), flag.astype(int)], axis=1), axis=1)
    return float((d == 1).sum()) / flag.size * 1000.0


def calibrate_threshold(clean: np.ndarray, valid: Optional[np.ndarray] = None, method: str = "fpr",
                        target_fpr: float = 0.01, max_events_per_1000: float = 5.0) -> Dict[str, float]:
    """Operating threshold from **clean validation** scores (n, W). Never use test data here.

    ``fpr``: the threshold whose point-wise false-positive rate on clean data is ``target_fpr``.
    ``events``: the smallest threshold with at most ``max_events_per_1000`` false alarm runs per 1000 steps.
    Returns the threshold plus the achieved point FPR and event rate on the calibration data.
    """
    s = np.asarray(clean, float)
    ok = np.ones(s.shape, bool) if valid is None else np.asarray(valid, bool)
    vals = s[ok & np.isfinite(s)]
    if vals.size == 0:
        raise ValueError("no clean scores to calibrate on")
    if method == "fpr":
        thr = float(np.quantile(vals, 1.0 - target_fpr))
    elif method == "events":
        cand = np.unique(np.quantile(vals, np.linspace(0.5, 1.0, 400)))
        thr = float(cand[-1])
        for c in cand:
            if _events_per_1000((s >= c) & ok) <= max_events_per_1000:
                thr = float(c)
                break
    else:
        raise ValueError(f"Unknown threshold method {method!r}")
    flag = (s >= thr) & ok
    return {"threshold": thr, "achieved_fpr": float(flag.sum() / max(ok.sum(), 1)),
            "events_per_1000": _events_per_1000(flag), "n_points": int(ok.sum()), "method": method}
