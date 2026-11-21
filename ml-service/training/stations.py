"""Optional station branch (feature flag ``use_stations``): station-wise affine calibration of the grid with
inverse-distance-squared blending over the nearest stations.

Grid model first; this layer only *calibrates the grid value at a location* using nearby stations:
for each of the k nearest stations i, ``a_i * grid + b_i`` is the grid rescaled to match station i
(least squares on the fit period), and the results are blended with weights proportional to 1 / d_i^2.

No station data ships with the repo. ``load_stations(None)`` logs a warning and returns an empty list, and
the sampler uses ``NullStationProvider`` (stations unavailable). Affine parameters must be fit on
**training-year** data only; ``StationCalibrator`` fits on exactly the arrays it is given.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class Station:
    name: str
    lat: float
    lon: float
    obs: np.ndarray    # (T,) station daily rainfall, mm (fit period)
    grid: np.ndarray   # (T,) grid value at the station, mm, aligned with ``obs``


def haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(np.asarray(lon2) - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def fit_affine(grid: np.ndarray, obs: np.ndarray, min_pairs: int = 10) -> Tuple[float, float]:
    """Least-squares (a, b) with obs ~ a * grid + b on finite pairs; (1, 0) when there is too little data
    or the grid has no variance. ``a`` is clipped to [0.2, 5] to avoid wild rescaling."""
    g, o = np.asarray(grid, float), np.asarray(obs, float)
    ok = np.isfinite(g) & np.isfinite(o)
    if ok.sum() < min_pairs or np.ptp(g[ok]) < 1e-6:
        return 1.0, 0.0
    a, b = np.polyfit(g[ok], o[ok], 1)
    return float(np.clip(a, 0.2, 5.0)), float(b)


def idw_weights(dist_km: np.ndarray, power: float = 2.0, eps_km: float = 0.1) -> np.ndarray:
    w = 1.0 / np.maximum(np.asarray(dist_km, float), eps_km) ** power
    return w / w.sum()


class StationCalibrator:
    def __init__(self, stations: Sequence[Station], k: int = 3, power: float = 2.0):
        if not stations:
            raise ValueError("StationCalibrator needs at least one station")
        self.stations, self.k, self.power = list(stations), k, power
        self.affine = [fit_affine(s.grid, s.obs) for s in self.stations]

    def calibrate(self, grid_series: np.ndarray, lat: float, lon: float) -> np.ndarray:
        """Station-calibrated version of a grid series at (lat, lon); never negative."""
        d = haversine_km(lat, lon, [s.lat for s in self.stations], [s.lon for s in self.stations])
        near = np.argsort(d)[: self.k]
        w = idw_weights(d[near], self.power)
        g = np.asarray(grid_series, float)
        out = sum(wi * (self.affine[i][0] * g + self.affine[i][1]) for wi, i in zip(w, near))
        return np.clip(out, 0.0, None)


def load_stations(path: Optional[str]) -> List[Station]:
    """Stub: no station file format is defined yet. Logs a warning and returns no stations."""
    if path:
        log.warning("load_stations(%r): station loading is not implemented yet (interface only); "
                    "continuing without stations", path)
    else:
        log.warning("no station data configured: the station branch will be marked unavailable")
    return []
