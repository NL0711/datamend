"""Geographic helpers shared by the rainfall platform. Nothing here depends on the legacy temperature/pressure/humidity code."""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two coordinates in kilometres (Haversine formula)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2.0) ** 2 +
         math.cos(p1) * math.cos(p2) * (math.sin(dlmb / 2.0) ** 2))
    return float(2.0 * EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(1.0 - a)))
