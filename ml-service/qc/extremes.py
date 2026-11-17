"""Protected and ambiguous extremes, defined on uncorrupted data by one rule for every client.

heavy      a cell-day above the cell's own heavy-rain threshold (training-year percentile of wet days)
protected  heavy cell-days forming a connected group (8-neighbour, same day) of at least ``min_cells`` cells.
           Labelled "plausible, unverified": the rule cannot tell real rain from a wide error. Never corrupted.
ambiguous  a heavy cell-day with no heavy neighbour. Neither an error nor protected; reported in its own row.
Heavy groups of 2 to ``min_cells - 1`` cells are neither; they stay ordinary cell-days and are counted in the summary.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import label

from qc.grid import Grid

_SAME_DAY_8 = np.zeros((3, 3, 3), bool)
_SAME_DAY_8[1] = True          # connect within a day only, never across days


@dataclass
class Extremes:
    protected: np.ndarray      # (T, n_land) bool
    ambiguous: np.ndarray      # (T, n_land) bool
    group: np.ndarray          # (T, n_land) int32: id of the heavy group a cell-day belongs to, 0 = not heavy
    n_protected_events: int
    n_small_groups: int        # heavy groups of 2 .. min_cells-1 cells


def find_extremes(series: np.ndarray, heavy_mm: np.ndarray, grid: Grid, min_cells: int = 4) -> Extremes:
    """``series`` is (T, n_land) uncorrupted mm; ``heavy_mm`` is (n_land,)."""
    heavy = np.nan_to_num(series, nan=-1.0) > heavy_mm[None, :]
    field = grid.to_field(heavy, fill=False)
    lab, n = label(field, structure=_SAME_DAY_8)
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    sizes[0] = 0
    group = grid.to_series(lab).astype(np.int32)
    size_of = sizes[group]
    return Extremes(size_of >= min_cells, size_of == 1, group,
                    int((sizes >= min_cells).sum()), int(((sizes >= 2) & (sizes < min_cells)).sum()))
