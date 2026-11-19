"""Shared rainfall geography, independent of the legacy weather pipeline."""
import math


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    a = min(1.0, max(0.0, a))
    return 2 * 6371.0088 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
