"""Weather Union station catalogue (built by scripts/build_weather_union_catalog.py from Zomato's published list)."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from backend.app.spatial.consensus import haversine_distance_km

CATALOG_PATH = Path(__file__).resolve().parents[1] / "sources" / "data" / "weather_union_stations.csv"

AWS = 1          # automated weather system: temperature, humidity, wind, rain
RAIN_GAUGE = 2   # rain gauge system: rainfall only (other fields come back null)


@dataclass(frozen=True)
class Station:
    locality_id: str
    city: str
    place: str
    latitude: float
    longitude: float
    device_type: int

    @property
    def device_label(self) -> str:
        return "rain gauge" if self.device_type == RAIN_GAUGE else "automated weather system"


@lru_cache(maxsize=1)
def load_catalog(path: Optional[str] = None) -> Dict[str, Station]:
    p = Path(path) if path else CATALOG_PATH
    with p.open(encoding="utf8", newline="") as f:
        return {
            r["locality_id"]: Station(r["locality_id"], r["city"], r["place"], float(r["latitude"]), float(r["longitude"]),
                                      int(r["device_type"]))
            for r in csv.DictReader(f)
        }


def neighbours(station: Station, radius_km: float = 10.0, catalog: Optional[Dict[str, Station]] = None) -> List[Station]:
    """Other stations within ``radius_km`` of ``station``, nearest first."""
    cat = catalog if catalog is not None else load_catalog()
    found = []
    for s in cat.values():
        if s.locality_id == station.locality_id:
            continue
        d = haversine_distance_km(station.latitude, station.longitude, s.latitude, s.longitude)
        if d <= radius_km:
            found.append((d, s))
    return [s for _, s in sorted(found, key=lambda t: t[0])]
