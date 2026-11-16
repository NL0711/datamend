"""Statistical baseline branch: per-cell, per-calendar-day climatological upper bound (training years only)."""

from __future__ import annotations

import warnings
from typing import Optional, Sequence

import numpy as np

from training.sampler import Batch, YearCube


class StatBaseline:
    """bound[d, r, c] = ``q``-quantile of daily rainfall in a +-``half_window`` day window around day d,
    pooled over the *given* years at cell (r, c). The caller must pass only training-year cubes; the
    fitted ``years`` are stored so tests and artifacts can verify that."""

    def __init__(self, bound: np.ndarray, years: Sequence[int], floor_mm: float = 1.0):
        self.bound, self.years, self.floor_mm = bound, list(years), floor_mm

    @classmethod
    def fit(cls, cubes: Sequence[YearCube], years: Sequence[int], q: float = 0.995,
            half_window: int = 7, stride: int = 3) -> "StatBaseline":
        if len(cubes) != len(years) or not cubes:
            raise ValueError("need one cube per year (non-empty)")
        h, w = cubes[0].rain.shape[1:]
        anchors = sorted(set(range(0, 366, stride)) | {365})
        vals = np.empty((len(anchors), h, w), np.float32)
        for i, d in enumerate(anchors):
            lo, hi = max(d - half_window, 0), d + half_window + 1
            parts = [c.rain[lo:min(hi, c.rain.shape[0])].astype(np.float32) for c in cubes if c.rain.shape[0] > lo]
            if not parts:        # no training year covers this day (only possible for partial years)
                vals[i] = np.nan
                continue
            pool = np.concatenate(parts, axis=0)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                vals[i] = np.nanquantile(pool, q, axis=0)
        days = np.arange(366)
        anchor_arr = np.array(anchors)
        hi_idx = np.clip(np.searchsorted(anchor_arr, days), 0, len(anchors) - 1)
        lo_idx = np.clip(hi_idx - 1, 0, len(anchors) - 1)
        a_lo, a_hi = anchor_arr[lo_idx], anchor_arr[hi_idx]
        t = np.where(a_hi > a_lo, (days - a_lo) / np.maximum(a_hi - a_lo, 1), 0.0)[:, None, None]
        bound = (1 - t) * vals[lo_idx] + t * vals[hi_idx]
        return cls(np.nan_to_num(bound, nan=0.0).astype(np.float32), years)

    def raw(self, b: Batch) -> Optional[np.ndarray]:
        """(n, W) ratio of the observed value to the climatological bound; None if cell/doy are unknown."""
        if b.cell is None or b.doy is None:
            return None
        rows, cols = b.cell[:, 0][:, None], b.cell[:, 1][:, None]
        bound = self.bound[np.minimum(b.doy, 365), rows, cols]
        return b.x_mm[..., 0] / (bound + self.floor_mm)
