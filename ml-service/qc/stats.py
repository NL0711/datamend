"""Statistics fitted on training years only: per-client normalization, climatology, heavy-rain threshold
and the climatological upper bound. Every array is per land cell (see ``qc.grid``).

Held-out clients also get their own normalization and climatology from their own training-year data.
That uses no labels and no model training, and nothing of it flows back into the trained models.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Sequence

import numpy as np

from ensemble.statbaseline import StatBaseline
from qc.splits import Split, assert_years_allowed
from training.climatology import ClimatologyAccumulator
from training.transform import RainfallTransform


@dataclass
class TrainStats:
    years: List[int]              # the years everything below was fitted on
    climatology: np.ndarray       # (366, n_land) smoothed mean daily rain, mm
    heavy_mm: np.ndarray          # (n_land,) heavy-rain threshold: percentile of the cell's wet days
    bound_mm: np.ndarray          # (366, n_land) climatological upper bound (existing StatBaseline)
    scale: np.ndarray             # (n_land,) normalization scale of the cell's client
    client_scale: Dict[int, float]

    def normalize(self, mm: np.ndarray) -> np.ndarray:
        """log1p(mm) / scale. Rescales only: no clipping of large values (negatives are floored at 0)."""
        return np.log1p(np.clip(mm, 0, None)) / self.scale

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, years=np.array(self.years), climatology=self.climatology, heavy_mm=self.heavy_mm,
                            bound_mm=self.bound_mm, scale=self.scale,
                            client_ids=np.array(sorted(self.client_scale)),
                            client_scales=np.array([self.client_scale[c] for c in sorted(self.client_scale)]))

    @classmethod
    def load(cls, path: Path) -> "TrainStats":
        z = np.load(path)
        return cls([int(y) for y in z["years"]], z["climatology"], z["heavy_mm"], z["bound_mm"], z["scale"],
                   {int(c): float(s) for c, s in zip(z["client_ids"], z["client_scales"])})


def fit_train_stats(series_by_year: Dict[int, np.ndarray], years: Sequence[int], split: Split, cell_client: np.ndarray,
                    wet_mm: float = 0.1, wet_quantile: float = 99.9, heavy_quantile: float = 99.0) -> TrainStats:
    """``series_by_year[y]`` is (days, n_land) mm; ``cell_client`` is (n_land,) client id of each land cell."""
    assert_years_allowed("training statistics", years, split, "train")
    n_land = cell_client.size
    acc = ClimatologyAccumulator((n_land, 1))
    for y in years:
        acc.add(series_by_year[y][:, :, None])
    climatology = acc.result()[:, :, 0]

    allv = np.concatenate([series_by_year[y] for y in years], axis=0)        # (T, n_land)
    wet = np.where(allv > wet_mm, allv, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)                      # cells with no wet day at all
        heavy = np.nanpercentile(wet, heavy_quantile, axis=0).astype(np.float32)
    # A cell with no wet day in the training years has no threshold: it can never be a protected extreme.
    heavy = np.where(np.isfinite(heavy), heavy, np.inf).astype(np.float32)

    client_scale: Dict[int, float] = {}
    scale = np.ones(n_land, np.float32)
    for c in sorted(int(v) for v in np.unique(cell_client)):
        sel = cell_client == c
        client_scale[c] = RainfallTransform.fit(allv[:, sel], wet_quantile).scale
        scale[sel] = client_scale[c]

    cubes = [SimpleNamespace(rain=series_by_year[y][:, :, None]) for y in years]
    bound = StatBaseline.fit(cubes, list(years)).bound[:, :, 0]
    return TrainStats([int(y) for y in years], climatology.astype(np.float32), heavy, bound.astype(np.float32), scale, client_scale)
