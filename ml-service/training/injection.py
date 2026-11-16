"""Labelled synthetic anomalies for zero-inflated daily rainfall windows (raw mm).

Only the target cell's series is corrupted; the neighbour/climatology context is
left untouched, so each injection is also a spatial or seasonal inconsistency.
Labels mark only timesteps whose value actually changed. Sign errors (negative
rain) are left to the rule engine.

Kinds: spike, stuck (constant run), scale (unit error), phantom_rain (drizzle in
a dry spell), zeroed (real rain replaced by 0 -- the classic missing-as-zero
error), repeat (a block copied from the preceding days).
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

import numpy as np

KINDS: Tuple[str, ...] = ("spike", "stuck", "scale", "phantom_rain", "zeroed", "repeat")

_LENGTHS: Dict[str, Tuple[int, int]] = {
    "spike": (1, 2),
    "stuck": (3, 10),
    "scale": (1, 7),
    "phantom_rain": (7, 20),
    "zeroed": (1, 7),
    "repeat": (3, 10),
}


def _apply(kind: str, seg: np.ndarray, rng: np.random.Generator, prev: Optional[np.ndarray]) -> Optional[np.ndarray]:
    n = seg.size
    if kind == "spike":
        return seg * rng.uniform(5, 15) + rng.uniform(40, 200)
    if kind == "stuck":
        return np.full(n, rng.uniform(1, 30), dtype=seg.dtype)
    if kind == "scale":  # unit error, e.g. cm vs mm
        return seg * (10.0 if rng.random() < 0.5 else 0.1)
    if kind == "phantom_rain":  # drizzle where there should be a dry spell
        return np.full(n, rng.uniform(0.5, 5.0), dtype=seg.dtype)
    if kind == "zeroed":
        return np.zeros(n, dtype=seg.dtype)
    if kind == "repeat":
        return None if prev is None else prev.copy()
    raise ValueError(f"Unknown anomaly kind {kind!r}")


def inject(
    mm: np.ndarray,
    rng: np.random.Generator,
    rate: float = 0.5,
    kinds: Sequence[str] = KINDS,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Corrupt a fraction ``rate`` of windows. ``mm`` is (n, W).

    Returns ``(corrupted_mm, point_labels (n, W) bool, kind_index (n,) int)``;
    ``kind_index`` indexes the global ``KINDS`` and is -1 for clean windows.
    """
    out = mm.astype(np.float32).copy()
    labels = np.zeros(mm.shape, dtype=bool)
    kind_idx = np.full(mm.shape[0], -1, dtype=np.int64)
    w = mm.shape[1]
    for i in np.nonzero(rng.random(mm.shape[0]) < rate)[0]:
        kind = kinds[int(rng.integers(len(kinds)))]
        lo, hi = _LENGTHS[kind]
        n = min(int(rng.integers(lo, hi + 1)), w)
        s = int(rng.integers(0, w - n + 1))
        seg = out[i, s : s + n]
        if kind == "phantom_rain" and (seg > 0).any():
            continue  # only meaningful inside a dry spell
        prev = out[i, s - n : s] if s >= n else None
        new = _apply(kind, seg, rng, prev)
        if new is None:
            continue
        new = new.astype(np.float32)
        changed = np.abs(new - seg) > 1e-3
        if not changed.any():
            continue
        out[i, s : s + n] = new
        labels[i, s : s + n] = changed
        kind_idx[i] = KINDS.index(kind)
    return out, labels, kind_idx
