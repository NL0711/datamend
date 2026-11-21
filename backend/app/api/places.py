"""Stateless place lookup: GET /api/places/locate?lat=&lon= (backend/app/places). Reads nothing from the database and writes nothing."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.places import grid
from backend.app.places.lookup import locate

router = APIRouter(prefix="/api/places", tags=["places"])


@router.get("/map")
async def map_layers() -> Dict[str, Any]:
    """The RF25 land mask and client regions for drawing a map: one string per row (row 0 is the SOUTHERNMOST), one digit per cell
    (0 = not land, 1 to 8 = client region). 129 x 135 cells at 0.25 degree."""
    cm = grid.client_map()
    if cm is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "the RF25 land mask asset is not available on this server")
    return {"grid": {"lat0": grid.LAT0, "lon0": grid.LON0, "step": grid.STEP, "n_lat": grid.N_LAT, "n_lon": grid.N_LON, "row0": "south"},
            "rows": ["".join(str(v) for v in row) for row in cm], "regions": sorted({v for row in cm for v in row if v}),
            "held_out_regions": list(grid.HELD_OUT_CLIENTS),
            "note": "RF25 client regions (groups of whole IMD sub-divisions used in the rainfall experiments), not IMD's own region boundaries"}


@router.get("/stations")
async def list_stations(city: Optional[str] = Query(None, max_length=80), limit: int = Query(200, ge=1, le=600)) -> Dict[str, Any]:
    """The Weather Union gauge catalogue (published station list), optionally for one city, each with its RF25 cell. A static list: no
    reading, no call to Weather Union."""
    from backend.app.rainfall.catalog import load_catalog
    cat = [s for s in load_catalog().values() if city is None or s.city.lower() == city.lower()]
    cities = sorted({s.city for s in load_catalog().values()})
    out = []
    for s in sorted(cat, key=lambda s: (s.city, s.place))[:limit]:
        try:
            p = locate(s.latitude, s.longitude)
            cell, land = p["cell"], p["is_land"]
        except grid.GridError:
            cell, land = None, None
        out.append({"station_id": s.locality_id, "city": s.city, "place": s.place, "latitude": s.latitude, "longitude": s.longitude,
                    "device": s.device_label, "cell": cell, "is_land": land})
    return {"cities": cities, "count": len(cat), "shown": len(out), "stations": out}


@router.get("/locate")
async def locate_place(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)) -> Dict[str, Any]:
    try:
        return locate(lat, lon)
    except grid.GridError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
