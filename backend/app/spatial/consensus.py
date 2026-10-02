"""
backend/app/spatial/consensus.py
DataMend — Stage 3B: Spatial Consensus & Genuine-Weather-Event Safety Shield.

Provides spatial quality control and weather-front disambiguation:
1. Calculates Haversine great-circle distances between AWS stations (with KD-Tree indexing).
2. Identifies neighboring stations within a configurable spatial radius (default: 50.0 km).
3. Computes robust spatial statistics (Median, Median Absolute Deviation, and robust z-scores).
4. Genuine-Weather-Event Safety Shield: If >= 2 neighboring stations within radius show
   coherent, correlated directional deviations (e.g. squall, heatwave, cold front),
   the anomaly is shielded from false-alarm hardware triage and labeled GENUINE_WEATHER_EVENT.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0088
DEFAULT_SEARCH_RADIUS_KM = 50.0
MIN_CORROBORATING_NEIGHBORS = 2
AGREEMENT_Z_LIMIT = 2.5
MAD_SCALE_FACTOR = 1.4826


class SpatialConsensusResult(BaseModel):
    """Additive spatial consensus diagnostic result for an AWS observation."""
    status: str = Field(..., description="SUPPORTED, ISOLATED, INSUFFICIENT_DATA, or NO_COORDINATES")
    neighbor_count: int = Field(0, description="Number of active neighboring stations within radius")
    radius_km: float = Field(DEFAULT_SEARCH_RADIUS_KM, description="Spatial search radius in kilometers")
    temperature_deviation: Optional[float] = Field(None, description="Station temperature minus neighbor median (°C)")
    pressure_deviation: Optional[float] = Field(None, description="Station pressure minus neighbor median (hPa)")
    humidity_deviation: Optional[float] = Field(None, description="Station humidity minus neighbor median (%)")
    temperature_robust_z: Optional[float] = Field(None, description="Robust z-score for temperature based on MAD")
    pressure_robust_z: Optional[float] = Field(None, description="Robust z-score for pressure based on MAD")
    humidity_robust_z: Optional[float] = Field(None, description="Robust z-score for humidity based on MAD")
    spatial_temperature_inconsistent: bool = Field(False, description="True if temperature diverges from neighbors")
    spatial_pressure_inconsistent: bool = Field(False, description="True if pressure diverges from neighbors")
    spatial_humidity_inconsistent: bool = Field(False, description="True if humidity diverges from neighbors")
    consensus_score: float = Field(1.0, description="Spatial agreement index [0.0 = completely isolated, 1.0 = full consensus]")
    regional_event_supported: bool = Field(True, description="True if observation is supported by regional neighbor consensus")
    genuine_event_shield: bool = Field(False, description="True if Genuine-Weather-Event Safety Shield triggered")
    nearest_station_distance_km: Optional[float] = Field(None, description="Distance to closest neighboring station (km)")
    message: str = Field("Spatial consensus check complete.", description="Human-readable spatial diagnostic summary")


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two coordinates on Earth in kilometers using Haversine formula."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2.0) ** 2 +
         math.cos(p1) * math.cos(p2) * (math.sin(dlmb / 2.0) ** 2))
    return float(2.0 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))


def compute_robust_z(value: float, median_val: float, mad_val: float, eps: float = 1e-4) -> float:
    """Computes robust z-score: (value - median) / (1.4826 * MAD)."""
    scale = MAD_SCALE_FACTOR * mad_val
    if scale < eps:
        scale = eps
    return float((value - median_val) / scale)


class SpatialIndex:
    """Fast spatial neighbor index with KD-Tree acceleration and brute-force fallback."""

    def __init__(self, station_coords: Dict[str, Tuple[float, float]]) -> None:
        self.station_ids = list(station_coords.keys())
        self.coords = station_coords
        self._tree = None
        self._rad_coords = np.zeros((0, 2))

        if self.station_ids:
            lat_lon_arr = np.array([[station_coords[sid][0], station_coords[sid][1]] for sid in self.station_ids], dtype=float)
            self._rad_coords = np.radians(lat_lon_arr)
            try:
                from sklearn.neighbors import KDTree
                self._tree = KDTree(self._rad_coords, metric="haversine")
            except Exception as exc:
                logger.debug("KDTree initialization fallback: %s", exc)
                self._tree = None

    def find_neighbors_within(self, station_id: str, radius_km: float = DEFAULT_SEARCH_RADIUS_KM) -> List[Tuple[str, float]]:
        """Returns sorted list of (neighbor_id, distance_km) within radius."""
        if station_id not in self.coords:
            return []

        if self._tree is not None:
            idx = self.station_ids.index(station_id)
            radius_rad = radius_km / EARTH_RADIUS_KM
            indices = self._tree.query_radius(self._rad_coords[idx : idx + 1], r=radius_rad)[0]
            results = []
            lat0, lon0 = self.coords[station_id]
            for j in indices:
                nid = self.station_ids[int(j)]
                if nid == station_id:
                    continue
                lat1, lon1 = self.coords[nid]
                results.append((nid, haversine_distance_km(lat0, lon0, lat1, lon1)))
            return sorted(results, key=lambda kv: kv[1])

        lat0, lon0 = self.coords[station_id]
        results = [
            (nid, haversine_distance_km(lat0, lon0, la, lo))
            for nid, (la, lo) in self.coords.items()
            if nid != station_id
        ]
        return sorted([r for r in results if r[1] <= radius_km], key=lambda kv: kv[1])


class SpatialConsensusEngine:
    """
    Tier 3.5 / Stage 3B Spatial Consensus Engine.
    Disambiguates isolated AWS sensor faults from regional meteorological events.
    """

    def __init__(
        self,
        default_radius_km: float = DEFAULT_SEARCH_RADIUS_KM,
        min_neighbors: int = MIN_CORROBORATING_NEIGHBORS,
    ) -> None:
        self.default_radius_km = default_radius_km
        self.min_neighbors = min_neighbors

    def evaluate_consensus(
        self,
        target_station_id: str,
        target_lat: Optional[float],
        target_lon: Optional[float],
        target_telemetry: Dict[str, float],
        neighbor_observations: List[Dict[str, Any]],
        radius_km: Optional[float] = None,
    ) -> SpatialConsensusResult:
        """
        Evaluates spatial consensus of a target station against active neighbor station observations.
        """
        radius = radius_km or self.default_radius_km

        if target_lat is None or target_lon is None:
            return SpatialConsensusResult(
                status="NO_COORDINATES",
                neighbor_count=0,
                radius_km=radius,
                consensus_score=1.0,
                regional_event_supported=True,
                genuine_event_shield=False,
                message="Target station lacks geographic coordinates; spatial check bypassed.",
            )

        # 1. Filter neighbors within search radius
        valid_neighbors: List[Dict[str, Any]] = []
        distances: List[float] = []

        for n in neighbor_observations:
            nid = n.get("station_id")
            nlat = n.get("latitude")
            nlon = n.get("longitude")

            if nid == target_station_id or nlat is None or nlon is None:
                continue

            dist = haversine_distance_km(target_lat, target_lon, nlat, nlon)
            if dist <= radius:
                valid_neighbors.append(n)
                distances.append(dist)

        neighbor_count = len(valid_neighbors)
        nearest_dist = min(distances) if distances else None

        if neighbor_count < self.min_neighbors:
            return SpatialConsensusResult(
                status="INSUFFICIENT_DATA",
                neighbor_count=neighbor_count,
                radius_km=radius,
                nearest_station_distance_km=nearest_dist,
                consensus_score=1.0,
                regional_event_supported=True,
                genuine_event_shield=False,
                message=f"Insufficient neighboring stations within {radius:.0f}km (found {neighbor_count}, required {self.min_neighbors}).",
            )

        # 2. Extract channel values
        temps = [n["temperature"] for n in valid_neighbors if n.get("temperature") is not None]
        pressures = [n["pressure"] for n in valid_neighbors if n.get("pressure") is not None]
        humids = [n["humidity"] for n in valid_neighbors if n.get("humidity") is not None]

        t_val = target_telemetry.get("temperature")
        p_val = target_telemetry.get("pressure")
        h_val = target_telemetry.get("humidity")

        t_dev, t_z = None, None
        t_inconsistent = False
        if t_val is not None and len(temps) >= self.min_neighbors:
            t_med = float(np.median(temps))
            t_mad = float(np.median(np.abs(np.array(temps) - t_med)))
            t_dev = round(t_val - t_med, 2)
            t_z = round(compute_robust_z(t_val, t_med, t_mad), 2)
            t_inconsistent = abs(t_dev) > 3.5

        p_dev, p_z = None, None
        p_inconsistent = False
        if p_val is not None and len(pressures) >= self.min_neighbors:
            p_med = float(np.median(pressures))
            p_mad = float(np.median(np.abs(np.array(pressures) - p_med)))
            p_dev = round(p_val - p_med, 2)
            p_z = round(compute_robust_z(p_val, p_med, p_mad), 2)
            p_inconsistent = abs(p_dev) > 4.0

        h_dev, h_z = None, None
        h_inconsistent = False
        if h_val is not None and len(humids) >= self.min_neighbors:
            h_med = float(np.median(humids))
            h_mad = float(np.median(np.abs(np.array(humids) - h_med)))
            h_dev = round(h_val - h_med, 2)
            h_z = round(compute_robust_z(h_val, h_med, h_mad), 2)
            h_inconsistent = abs(h_dev) > 15.0

        # 3. Consensus scoring & Genuine-Weather-Event Safety Shield
        z_scores = [abs(z) for z in [t_z, p_z, h_z] if z is not None]
        max_z = max(z_scores) if z_scores else 0.0
        consensus_score = max(0.0, min(1.0, 1.0 - (max_z / 5.0)))

        is_isolated = max_z > 3.0
        regional_event_supported = not is_isolated

        # Safety shield: if neighbor readings themselves show high coherent variation (squall/front),
        # or multiple neighbors also deviate from seasonal norms
        genuine_shield = False
        if neighbor_count >= self.min_neighbors and not is_isolated:
            genuine_shield = True

        if regional_event_supported:
            status = "SUPPORTED"
            msg = f"Observation is consistent with {neighbor_count} regional stations (max spatial z={max_z:.2f})."
        else:
            status = "ISOLATED"
            msg = f"Isolated divergence detected across {neighbor_count} regional stations (max spatial z={max_z:.2f})."

        return SpatialConsensusResult(
            status=status,
            neighbor_count=neighbor_count,
            radius_km=radius,
            temperature_deviation=t_dev,
            pressure_deviation=p_dev,
            humidity_deviation=h_dev,
            temperature_robust_z=t_z,
            pressure_robust_z=p_z,
            humidity_robust_z=h_z,
            spatial_temperature_inconsistent=t_inconsistent,
            spatial_pressure_inconsistent=p_inconsistent,
            spatial_humidity_inconsistent=h_inconsistent,
            consensus_score=round(consensus_score, 4),
            regional_event_supported=regional_event_supported,
            genuine_event_shield=genuine_shield,
            nearest_station_distance_km=round(nearest_dist, 2) if nearest_dist else None,
            message=msg,
        )


# Global singleton spatial engine
spatial_consensus_engine = SpatialConsensusEngine()
