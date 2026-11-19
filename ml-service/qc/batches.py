"""Turn a block of daily fields into network inputs, for training and for scoring.

A *view* wraps one block (history days + the days to score) as a dense (days, H, W) array so that patches
can be cut out by indexing. Inputs are normalised with the target cell's own client scale. Targets are
raw mm. Nothing here reads a cell outside the array it is given: to train on one client only, pass a view
whose unreadable cells are NaN (``mask_unreadable``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import torch

from qc.grid import Grid
from qc.stats import TrainStats


def mask_unreadable(obs: np.ndarray, readable: np.ndarray, grid: Grid) -> np.ndarray:
    """Set cells that may not be read to NaN. ``readable`` is an (H, W) bool mask."""
    out = obs.copy()
    out[:, ~grid.to_series(readable)] = np.nan
    return out


@dataclass
class View:
    """One block ready for batching. ``obs`` is (pad + T, n_land) mm, ``doy`` is (pad + T,)."""
    grid: Grid
    stats: TrainStats
    obs: np.ndarray
    doy: np.ndarray
    pad: int
    radius: int
    dense: Optional[np.ndarray] = None            # (pad + T, H + 2R, W + 2R), built only for the spatial component

    @classmethod
    def build(cls, grid: Grid, stats: TrainStats, obs: np.ndarray, doy: np.ndarray, pad: int, radius: int = 0) -> "View":
        v = cls(grid, stats, obs, doy, pad, radius)
        if radius > 0:
            h, w = grid.shape
            v.dense = np.full((obs.shape[0], h + 2 * radius, w + 2 * radius), np.nan, np.float32)
            v.dense[:, radius:radius + h, radius:radius + w][:, grid.rows, grid.cols] = obs
        return v

    @property
    def days(self) -> int:
        return self.obs.shape[0] - self.pad

    # ------------------------------------------------------------------ shared pieces

    def _static(self, t: np.ndarray, cell: np.ndarray) -> np.ndarray:
        """(B, 4): sin, cos of the day of year; log1p(climatology)/scale; log1p(heavy threshold)/scale."""
        d = np.minimum(self.doy[self.pad + t], 365)
        ang = 2 * np.pi * d / 365.25
        sc = self.stats.scale[cell]
        heavy = np.where(np.isfinite(self.stats.heavy_mm[cell]), self.stats.heavy_mm[cell], 0.0)
        return np.stack([np.sin(ang), np.cos(ang), np.log1p(self.stats.climatology[d, cell]) / sc, np.log1p(heavy) / sc],
                        axis=1).astype(np.float32)

    def _norm(self, mm: np.ndarray, cell: np.ndarray) -> np.ndarray:
        sc = self.stats.scale[cell].reshape((-1,) + (1,) * (mm.ndim - 1))
        return np.log1p(np.clip(mm, 0, None)) / sc

    def target(self, t: np.ndarray, cell: np.ndarray, clean: Optional[np.ndarray] = None) -> np.ndarray:
        """Observed mm of the scored day (or ``clean`` if given: the block's uncorrupted values, same layout as obs)."""
        src = self.obs if clean is None else clean
        return src[self.pad + t, cell]

    def unit(self, cell: np.ndarray) -> np.ndarray:
        """mm per rainfall unit: the cell's client scale turned back into mm."""
        return np.expm1(self.stats.scale[cell]).astype(np.float32)

    # ------------------------------------------------------------------ spatial

    def spatial(self, t: np.ndarray, cell: np.ndarray) -> Dict[str, np.ndarray]:
        """Same-day patches (2R+1)^2 around each target. The model, not this function, hides the target and its disc."""
        R = self.radius
        k = np.arange(-R, R + 1)
        r = self.grid.rows[cell] + R
        c = self.grid.cols[cell] + R
        raw = self.dense[(self.pad + t)[:, None, None], (r[:, None, None] + k[None, :, None]), (c[:, None, None] + k[None, None, :])]
        valid = np.isfinite(raw)
        patch = np.where(valid, self._norm(np.nan_to_num(raw, nan=0.0), cell), 0.0).astype(np.float32)
        return {"patch": patch, "valid": valid.astype(np.float32), "static": self._static(t, cell)}

    # ------------------------------------------------------------------ temporal

    def history(self, t: np.ndarray, cell: np.ndarray, length: int) -> Dict[str, np.ndarray]:
        """The cell's own days t-length .. t-1 (oldest first). The scored day itself is never included."""
        rows = (self.pad + t)[:, None] - length + np.arange(length)[None, :]
        raw = self.obs[rows, cell[:, None]]
        valid = np.isfinite(raw)
        hist = np.where(valid, self._norm(np.nan_to_num(raw, nan=0.0), cell), 0.0).astype(np.float32)
        return {"hist": hist, "valid": valid.astype(np.float32), "static": self._static(t, cell)}


def to_torch(batch: Dict[str, np.ndarray], device) -> Dict[str, torch.Tensor]:
    return {k: torch.from_numpy(np.ascontiguousarray(v)).to(device, non_blocking=True) for k, v in batch.items()}
