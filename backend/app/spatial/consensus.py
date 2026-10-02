"""
backend/app/spatial/consensus.py
SkyGuard AI — Spatial Consensus & Neighbor AWS Buddy-Check Diagnostic Layer (Tier 3.5).

Provides spatial quality control and weather-front disambiguation:
1. Calculates Haversine great-circle distances between AWS stations.
2. Identifies neighboring stations within a configurable spatial radius (default: 50.0 km).
3. Computes robust spatial statistics (Median, Median Absolute Deviation, and robust z-scores).
4. Distinguishes regional meteorological events (multi-station coherent movement) from isolated sensor faults.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SpatialConsensusResult(BaseModel):
    """Additive spatial consensus diagnostic result for an AWS observation."""
    status: str = Field(..., description="SUPPORTED, ISOLATED, INSUFFICIENT_DATA, or NO_COORDINATES")
    neighbor_count: int = Field(0, description="Number of active neighboring stations within radius")
    radius_km: float = Field(50.0, description="Spatial search radius in kilometers")
    temperature_deviation: Optional[float] = Field(None, description="Station temperature minus neighbor median (°C)")
    pressure_deviation: Optional[float] = Field(None, description="Station pressure minus neighbor median (hPa)")
    humidity_deviation: Optional[float] = Field(None, description="Station humidity minus neighbor median (%)")
    temperature_robust_z: Optional[float] = Field(None, description="Robust z-score for temperature based on MAD")
    pressure_robust_z: Optional[float] = Field(None, description="Robust z-score for pressure based on MAD")
    humidity_robust_z: Optional[float] = Field(None, description="Robust z-score for humidity based on MAD")
    consensus_score: float = Field(1.0, description="Spatial agreement index [0.0 = completely isolated anomaly, 1.0 = full regional consensus]")
    regional_event_supported: bool = Field(True, description="True if observation is supported by regional neighbor consensus")
    nearest_station_distance_km: Optional[float] = Field(None, description="Distance to closest neighboring station (km)")
    message: str = Field("Spatial consensus check complete.", description="Human-readable spatial diagnostic summary")


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two coordinates on Earth in kilometers using Haversine formula."""
    r_earth = 6371.0  # Earth's mean radius in km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_earth * c


def compute_robust_z(value: float, median_val: float, mad_val: float, eps: float = 1e-4) -> float:
    """Computes robust z-score: (value - median) / (1.4826 * MAD)."""
    scale = 1.4826 * mad_val
    if scale < eps:
        scale = eps
    return (value - median_val) / scale


class SpatialConsensusEngine:
    """
    Tier 3.5 Spatial Consensus Diagnostic Engine.
    Evaluates whether a target AWS station's observations are supported by neighboring stations.
    """

    def __init__(self, default_radius_km: float = 50.0, min_neighbors: int = 2) -> None:
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
        Evaluates spatial consensus of a target station against a list of neighbor station observations.

        Parameters
        ----------
        target_station_id : str
            ID of the target station being evaluated.
        target_lat, target_lon : float, optional
            Geographic coordinates of the target station.
        target_telemetry : dict
            Target station values {'temperature': float, 'pressure': float, 'humidity': float}.
        neighbor_observations : list of dict
            List of neighbor dicts: [{'station_id': str, 'latitude': float, 'longitude': float,
                                      'temperature': float, 'pressure': float, 'humidity': float}, ...]
        radius_km : float, optional
            Spatial search radius (default: 50.0 km).
        """
        radius = radius_km or self.default_radius_km

        if target_lat is None or target_lon is None:
            return SpatialConsensusResult(
                status="NO_COORDINATES",
                neighbor_count=0,
                radius_km=radius,
                consensus_score=1.0,
                regional_event_supported=True,
                message="Target station lacks geographic coordinates; spatial check bypassed.",
            )

        # 1. Filter neighbors within search radius
        valid_neighbors: List[Dict[str, Any]] = []
        distances: List[float] = []

        for n in neighbor_observations:
            n_id = n.get("station_id")
            n_lat = n.get("latitude")
            n_lon = n.get("longitude")

            if n_id == target_station_id or n_lat is None or n_lon is None:
                continue

            dist = haversine_distance_km(target_lat, target_lon, n_lat, n_lon)
            if dist <= radius:
                valid_neighbors.append(n)
                distances.append(dist)

        neighbor_count = len(valid_neighbors)
        nearest_dist = min(distances) if distances else None

        # 2. Check minimum neighbor requirement
        if neighbor_count < self.min_neighbors:
            return SpatialConsensusResult(
                status="INSUFFICIENT_DATA",
                neighbor_count=neighbor_count,
                radius_km=radius,
                nearest_station_distance_km=nearest_dist,
                consensus_score=1.0,
                regional_event_supported=True,
                message=f"Insufficient neighboring stations within {radius:.0f}km (found {neighbor_count}, required {self.min_neighbors}).",
            )

        # 3. Extract channel arrays
        temps = [n["temperature"] for n in valid_neighbors if "temperature" in n and n["temperature"] is not None]
        pressures = [n["pressure"] for n in valid_neighbors if "pressure" in n and n["pressure"] is not None]
        humids = [n["humidity"] for n in valid_neighbors if "humidity" in n and n["humidity"] is not None]

        t_val = target_telemetry.get("temperature")
        p_val = target_telemetry.get("pressure")
        h_val = target_telemetry.get("humidity")

        # Robust statistics
        import numpy as np

        t_dev = None
        t_z = None
        if t_val is not None and len(temps) >= self.min_neighbors:
            t_med = float(np.median(temps))
            t_mad = float(np.median(np.abs(np.array(temps) - t_med)))
            t_dev = round(t_val - t_med, 2)
            t_z = round(compute_robust_z(t_val, t_med, t_mad), 2)

        p_dev = None
        p_z = None
        if p_val is not None and len(pressures) >= self.min_neighbors:
            p_med = float(np.median(pressures))
            p_mad = float(np.median(np.abs(np.array(pressures) - p_med)))
            p_dev = round(p_val - p_med, 2)
            p_z = round(compute_robust_z(p_val, p_med, p_mad), 2)

        h_dev = None
        h_z = None
        if h_val is not None and len(humids) >= self.min_neighbors:
            h_med = float(np.median(humids))
            h_mad = float(np.median(np.abs(np.array(humids) - h_med)))
            h_dev = round(h_val - h_med, 2)
            h_z = round(compute_robust_z(h_val, h_med, h_mad), 2)

        # 4. Consensus scoring & isolated sensor fault vs regional weather front discrimination
        z_scores = [abs(z) for z in [t_z, p_z, h_z] if z is not None]
        max_z = max(z_scores) if z_scores else 0.0

        # Consensus score: 1.0 (perfect agreement) to 0.0 (high spatial deviation)
        # z <= 2.5 is normal, z >= 5.0 is isolated deviation
        consensus_score = max(0.0, min(1.0, 1.0 - (max_z / 5.0)))

        is_isolated = max_z > 3.0
        regional_event_supported = not is_isolated

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
            consensus_score=round(consensus_score, 4),
            regional_event_supported=regional_event_supported,
            nearest_station_distance_km=round(nearest_dist, 2) if nearest_dist else None,
            message=msg,
        )


# Global singleton spatial engine
spatial_consensus_engine = SpatialConsensusEngine()
