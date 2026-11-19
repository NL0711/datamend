"""`locate(lat, lon)`: the RF25 cell, its land or sea status and its client region. Stateless; nothing is stored.

The client region comes from the committed ml-service/qc/assets/client_map.json (0 = not land, 1..8 = region). The IMD sub-division
lookup is NOT IMPLEMENTED in the platform (its boundary file is fetched by script, not committed, licence unstated), so it always
answers "not available".
"""
from __future__ import annotations

from typing import Any, Dict

from backend.app.places import grid


def locate(lat: float, lon: float) -> Dict[str, Any]:
    """Raises grid.GridError for a point outside the RF25 domain or a non-finite coordinate."""
    if not (isinstance(lat, (int, float)) and isinstance(lon, (int, float))) or lat != lat or lon != lon:
        raise grid.GridError("latitude and longitude must be numbers")
    row, col = grid.cell_of(lat, lon)
    cell = grid.describe_cell(row, col)
    return {
        "latitude": lat, "longitude": lon,
        "cell": {"row": row, "col": col, "lat": cell["lat"], "lon": cell["lon"], "grid": "RF25 0.25 degree"},
        "is_land": cell["is_land"],       # None when the client map asset is missing
        "client_region": cell["client"],
        "imd_subdivision": {"status": "not_available", "reason": "NOT IMPLEMENTED in the platform: the IMD boundary file is local-only and not loaded"},
    }
