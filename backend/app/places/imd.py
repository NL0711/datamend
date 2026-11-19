"""Indian synoptic stations from NOAA's station inventory (backend/app/places/data/imd_stations.csv, built by scripts/build_imd_station_list.py).

These are stations that have reported to NOAA's Integrated Surface Database; most are operated by IMD. It is NOT IMD's own station list
(IMD's AWS/ARG list is not public). Metadata only: names and coordinates, no observations. `last_data` is when NOAA's archive stops.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.geo import haversine_distance_km

CSV_PATH = Path(__file__).resolve().parent / "data" / "imd_stations.csv"
SOURCE = "NOAA NCEI isd-history.csv (Indian stations, station metadata only)"


@lru_cache(maxsize=1)
def stations() -> List[Dict[str, Any]]:
    try:
        with CSV_PATH.open(encoding="utf8", newline="") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return []
    out = []
    for r in rows:
        out.append({
            "id": r["id"], "name": r["name"], "state": r["state"] or None, "icao": r["icao"] or None,
            "latitude": float(r["latitude"]), "longitude": float(r["longitude"]),
            "elevation_m": float(r["elevation_m"]) if r["elevation_m"] else None,
            "first_data": r["first_data"] or None, "last_data": r["last_data"] or None,
        })
    return out


@lru_cache(maxsize=4096)
def _nearest(lat: float, lon: float) -> Optional[Tuple[str, str, float]]:
    best: Optional[Tuple[str, str, float]] = None
    for s in stations():
        d = haversine_distance_km(lat, lon, s["latitude"], s["longitude"])
        if best is None or d < best[2]:
            best = (s["id"], s["name"], d)
    return best


def nearest(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """The closest listed station to a point and the distance in km, or None when the list is not available. A new dict each call
    (the cache holds an immutable tuple), so a caller cannot change what the next caller gets."""
    b = _nearest(lat, lon)
    return None if b is None else {"id": b[0], "name": b[1], "km": round(b[2], 1)}
