"""Grid UK station values the way RF25 was made: inverse-distance weighting of the nearest 1-4 gauges within a
search radius. Two versions of every day are gridded: the CORRECTED series (current-best values) and the
ORIGINAL series (the values before QC changed them). A cell-day is

  labelled  if a station that fed the ORIGINAL value of the cell was hand-corrected that day and the cell's
            value actually changed (spec section 12: "a cell-day is bad if a hand-corrected station value fed it")
  excluded  if the two versions differ but no hand correction fed the cell (automatic estimates, split
            multi-day totals, other changes): not scored, not clean, counted separately

Design choices that the spec left open (change them in ``configs/uk.yaml``; the build prints them):
grid spacing 0.1 degree, search radius 35 km, at most 4 gauges, weight 1 / distance squared.
Distances use an equirectangular approximation, adequate at this extent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from qc.uk.midas import StationData

KM_PER_DEG = 111.195
CHANGED_MM = 1e-3


@dataclass
class UKGridSpec:
    lat0: float
    lon0: float
    step: float
    n_lat: int
    n_lon: int
    radius_km: float = 35.0
    max_gauges: int = 4
    power: float = 2.0

    @property
    def lat(self) -> np.ndarray:
        return self.lat0 + self.step * np.arange(self.n_lat)

    @property
    def lon(self) -> np.ndarray:
        return self.lon0 + self.step * np.arange(self.n_lon)


def neighbour_table(spec: UKGridSpec, st_lat: np.ndarray, st_lon: np.ndarray, max_keep: int = 24) -> Tuple[np.ndarray, np.ndarray]:
    """For each cell (row-major over the full grid): indices of stations within the radius, nearest first,
    padded with -1, and their distances in km. ``max_keep`` bounds the candidates per cell."""
    la, lo = np.meshgrid(spec.lat, spec.lon, indexing="ij")
    la, lo = la.ravel(), lo.ravel()
    coslat = np.cos(np.deg2rad(la))[:, None]
    dy = (la[:, None] - st_lat[None, :]) * KM_PER_DEG
    dx = (lo[:, None] - st_lon[None, :]) * KM_PER_DEG * coslat
    d = np.hypot(dx, dy)
    order = np.argsort(d, axis=1)[:, :max_keep]
    dist = np.take_along_axis(d, order, axis=1)
    idx = np.where(dist <= spec.radius_km, order, -1)
    return idx.astype(np.int32), np.where(idx >= 0, dist, np.inf).astype(np.float32)


def station_matrices(sd: StationData, year: int) -> Dict[str, np.ndarray]:
    """Dense (T, n_station) arrays for one year: corrected, original (mm, NaN = none), manual and excluded (bool)."""
    days = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    n, T = len(sd.ids), len(days)
    col = {s: i for i, s in enumerate(sd.ids)}

    def put(df: pd.DataFrame, value_cols, fill, dtype):
        out = [np.full((T, n), fill, dtype) for _ in value_cols]
        d = df[df["date"].dt.year == year]
        t = (d["date"] - days[0]).dt.days.to_numpy()
        s = d["station"].map(col).to_numpy()
        ok = ~np.isnan(s.astype(float)) & (t >= 0) & (t < T)
        for o, c in zip(out, value_cols):
            o[t[ok], s[ok].astype(int)] = d[c].to_numpy()[ok] if c else True
        return out

    corrected, original = put(sd.daily, ["corrected", "original"], np.nan, np.float32)
    (manual,) = put(sd.manual, [None], False, bool)
    (excluded,) = put(sd.excluded, [None], False, bool)
    return {"corrected": corrected, "original": original, "manual": manual, "excluded": excluded}


def _idw(values: np.ndarray, idx: np.ndarray, dist: np.ndarray, spec: UKGridSpec):
    """(T, n_station) -> gridded (T, n_cell) and the selection mask (T, n_cell, M) of gauges that fed each value."""
    pad = np.concatenate([values, np.full((values.shape[0], 1), np.nan, values.dtype)], axis=1)
    v = pad[:, idx]                                              # (T, C, M); index -1 picks the NaN column
    fin = np.isfinite(v)
    sel = fin & (np.cumsum(fin, axis=2) <= spec.max_gauges)
    w = np.where(sel, 1.0 / np.maximum(dist[None], 1.0) ** spec.power, 0.0)
    num = np.where(sel, v, 0.0) * w
    tot = w.sum(axis=2)
    with np.errstate(invalid="ignore", divide="ignore"):
        g = np.where(tot > 0, num.sum(axis=2) / tot, np.nan)
    return g.astype(np.float32), sel


def grid_year(m: Dict[str, np.ndarray], idx: np.ndarray, dist: np.ndarray, spec: UKGridSpec) -> Dict[str, np.ndarray]:
    """Gridded corrected and original series, and the labelled and excluded cell-day masks, all (T, n_cell)."""
    corr, _ = _idw(m["corrected"], idx, dist, spec)
    orig, sel = _idw(m["original"], idx, dist, spec)
    manual_pad = np.concatenate([m["manual"], np.zeros((m["manual"].shape[0], 1), bool)], axis=1)
    fed_by_manual = (sel & manual_pad[:, idx]).any(axis=2)
    both = np.isfinite(corr) & np.isfinite(orig)
    changed = both & (np.abs(orig - corr) > CHANGED_MM)
    changed |= np.isfinite(corr) != np.isfinite(orig)           # a value on one side only: also a difference
    labelled = fed_by_manual & both & changed
    excluded = changed & ~labelled
    return {"corrected": corr, "original": orig, "labelled": labelled, "excluded": excluded}
