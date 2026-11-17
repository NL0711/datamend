"""Per-cell day-of-year rainfall climatology, fit on training years only."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import uniform_filter1d


class ClimatologyAccumulator:
    """Stream cubes in one at a time; ``result()`` gives a smoothed (366, H, W) mean in mm."""

    def __init__(self, shape_hw):
        h, w = shape_hw
        self.total = np.zeros((366, h, w), dtype=np.float64)
        self.count = np.zeros((366, h, w), dtype=np.float64)

    def add(self, cube: np.ndarray) -> None:
        t = cube.shape[0]
        ok = ~np.isnan(cube)
        self.total[:t] += np.where(ok, cube, 0.0)
        self.count[:t] += ok

    def result(self, smooth_days: int = 15) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            clim = self.total / self.count
        land = ~np.isnan(clim[:365]).all(axis=0)
        clim[365] = np.where(np.isnan(clim[365]), clim[364], clim[365])  # day 366 (leap years only)
        filled = np.nan_to_num(clim, nan=0.0)
        smooth = uniform_filter1d(filled, size=smooth_days, axis=0, mode="wrap")
        smooth[:, ~land] = np.nan
        return smooth.astype(np.float32)
