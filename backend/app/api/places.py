"""Stateless place lookup: GET /api/places/locate?lat=&lon= (backend/app/places). Reads nothing from the database and writes nothing."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.places import grid
from backend.app.places.lookup import locate

router = APIRouter(prefix="/api/places", tags=["places"])


@router.get("/locate")
async def locate_place(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)) -> Dict[str, Any]:
    try:
        return locate(lat, lon)
    except grid.GridError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
