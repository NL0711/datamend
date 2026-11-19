"""The 0.25-degree RF25 grid used by ml-service/qc, and the mapping from a place to its cells.

Grid (same as ml-service/qc/configs/base.yaml): latitude 6.5 + 0.25 * row for row 0..128 (row 0 is the SOUTHERNMOST row),
longitude 66.5 + 0.25 * col for col 0..134. A cell is the 0.25 x 0.25 degree square centred on that point.
Land mask and client region come from ml-service/qc/assets/client_map.json (0 = not land; 1..8 = client region).
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

LAT0, LON0, STEP = 6.5, 66.5, 0.25
N_LAT, N_LON = 129, 135
HELD_OUT_CLIENTS = (3, 6)                       # unseen clients in the rainfall experiments (qc config clients.heldout)
KM_PER_DEG = 111.195
MAX_CELLS = 40
CLIENT_MAP_PATH = Path(__file__).resolve().parents[3] / "ml-service" / "qc" / "assets" / "client_map.json"


class GridError(ValueError):
    """The point or area cannot be mapped to the grid."""


def lat_of(row: int) -> float:
    return LAT0 + STEP * row


def lon_of(col: int) -> float:
    return LON0 + STEP * col


def in_domain(lat: float, lon: float) -> bool:
    return (LAT0 - STEP / 2 <= lat <= lat_of(N_LAT - 1) + STEP / 2) and (LON0 - STEP / 2 <= lon <= lon_of(N_LON - 1) + STEP / 2)


def cell_of(lat: float, lon: float) -> Tuple[int, int]:
    """(row, col) of the cell whose square contains the point."""
    if not in_domain(lat, lon):
        raise GridError(f"({lat}, {lon}) is outside the grid ({LAT0}-{lat_of(N_LAT - 1)} N, {LON0}-{lon_of(N_LON - 1)} E)")
    return int(round((lat - LAT0) / STEP)), int(round((lon - LON0) / STEP))


def bbox_from_radius(lat: float, lon: float, radius_km: float) -> Tuple[float, float, float, float]:
    dlat = radius_km / KM_PER_DEG
    dlon = radius_km / (KM_PER_DEG * max(math.cos(math.radians(lat)), 0.1))
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def cells_in_bbox(lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> List[Tuple[int, int]]:
    """Cells whose square overlaps the box with positive area, south to north, west to east."""
    half = STEP / 2
    rows = [r for r in range(N_LAT) if lat_of(r) + half > lat_min and lat_of(r) - half < lat_max]
    cols = [c for c in range(N_LON) if lon_of(c) + half > lon_min and lon_of(c) - half < lon_max]
    return [(r, c) for r in rows for c in cols]


def cells_for(lat: float, lon: float, radius_km: float) -> List[Tuple[int, int]]:
    """The cells a place covers: those overlapping the box of ``radius_km`` around it, always including the cell of the point."""
    if radius_km < 0:
        raise GridError("radius_km must be 0 or more")
    home = cell_of(lat, lon)
    found = [rc for rc in cells_in_bbox(*bbox_from_radius(lat, lon, radius_km)) if 0 <= rc[0] < N_LAT and 0 <= rc[1] < N_LON]
    if home not in found:
        found.append(home)
    if len(found) > MAX_CELLS:
        raise GridError(f"that area covers {len(found)} cells; at most {MAX_CELLS} are allowed (use a smaller radius)")
    return sorted(found)


@lru_cache(maxsize=1)
def client_map() -> Optional[List[List[int]]]:
    """Client id per cell, [row][col]; None if the asset is not available."""
    try:
        doc = json.loads(CLIENT_MAP_PATH.read_text(encoding="utf-8"))
        return [[int(ch) for ch in row] for row in doc["rows"]]
    except (OSError, ValueError, KeyError):
        return None


def describe_cell(row: int, col: int) -> Dict:
    cm = client_map()
    if cm is None:
        return {"row": row, "col": col, "lat": lat_of(row), "lon": lon_of(col), "is_land": None, "client": None, "held_out": False}
    client = cm[row][col]
    return {"row": row, "col": col, "lat": lat_of(row), "lon": lon_of(col), "is_land": client > 0,
            "client": client or None, "held_out": client in HELD_OUT_CLIENTS}
