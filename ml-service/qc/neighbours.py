"""Neighbour lookup on the land grid: for every land cell, the land cells in a ring around it.

``ring_index(grid, r_in, r_out)`` returns (n_land, K) land-cell indices of the cells whose distance d from the
target satisfies ``r_in < d <= r_out`` (Euclidean, in cells); -1 where the neighbour is off land, off the
grid, or not allowed. With ``r_in = hidden radius`` the target and its hidden disc are never included.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from qc.grid import Grid


def ring_offsets(r_in: float, r_out: float) -> np.ndarray:
    k = int(np.floor(r_out))
    dr, dc = np.mgrid[-k:k + 1, -k:k + 1]
    d = np.hypot(dr, dc)
    sel = (d > r_in) & (d <= r_out)
    return np.stack([dr[sel], dc[sel]], axis=1)


def ring_index(grid: Grid, r_in: float, r_out: float, allowed: Optional[np.ndarray] = None) -> np.ndarray:
    """``allowed`` is an (H, W) bool mask of cells that may be read (e.g. one client's cells); default all land."""
    h, w = grid.shape
    index = np.full((h, w), -1, np.int32)
    index[grid.rows, grid.cols] = np.arange(grid.n_land)
    if allowed is not None:
        index[~allowed] = -1
    off = ring_offsets(r_in, r_out)
    rr = grid.rows[:, None] + off[None, :, 0]
    cc = grid.cols[:, None] + off[None, :, 1]
    ok = (rr >= 0) & (rr < h) & (cc >= 0) & (cc < w)
    out = np.full(rr.shape, -1, np.int32)
    out[ok] = index[rr[ok], cc[ok]]
    return out


def gather(series: np.ndarray, idx: np.ndarray) -> np.ndarray:
    """(T, n_land) and (n_land, K) -> (T, n_land, K), NaN where the neighbour index is -1."""
    padded = np.concatenate([series, np.full((series.shape[0], 1), np.nan, series.dtype)], axis=1)
    return padded[:, idx]            # index -1 picks the NaN column
