"""Stateless place lookup: GET /api/places/locate?lat=&lon= (backend/app/places). Reads nothing from the database and writes nothing."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.places import grid
from backend.app.places.lookup import locate

router = APIRouter(prefix="/api/places", tags=["places"])


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
