"""REST endpoints of the Locations feature (see docs/LOCATIONS_DESIGN.md)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db.database import get_db
from backend.app.locations.grid import GridError
from backend.app.locations.models import Location
from backend.app.locations.openmeteo import OpenMeteoClient, OpenMeteoError
from backend.app.locations.scores import FileScoreProvider
from backend.app.locations.service import DEFAULT_RADIUS_KM, LocationNotFound, LocationService

router = APIRouter(prefix="/api/locations", tags=["locations"])

_client = OpenMeteoClient()
_scores = FileScoreProvider()


class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255, description="A place name; used to look up coordinates when none are given")
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    radius_km: float = Field(default=DEFAULT_RADIUS_KM, ge=0, le=100)

    @model_validator(mode="after")
    def both_or_neither(self) -> "LocationCreate":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("give both latitude and longitude, or neither")
        return self


def get_service(db: AsyncSession = Depends(get_db)) -> LocationService:
    return LocationService(db, om=_client, scores=_scores)


def _out(loc: Location) -> Dict[str, Any]:
    return {"id": loc.id, "name": loc.name, "latitude": loc.latitude, "longitude": loc.longitude, "radius_km": loc.radius_km,
            "preset": loc.preset, "created_at": loc.created_at.isoformat(),
            "cells": [{"row": c.cell_row, "col": c.cell_col, "lat": c.lat, "lon": c.lon, "is_land": c.is_land, "client": c.client,
                       "held_out": c.held_out} for c in loc.cells]}


def _raise(e: Exception) -> None:
    if isinstance(e, LocationNotFound):
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    if isinstance(e, GridError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    if isinstance(e, OpenMeteoError):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"The weather data service is not reachable right now ({e}). Try again shortly.")
    raise e


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a location by name or coordinates")
async def create_location(body: LocationCreate, svc: LocationService = Depends(get_service)) -> Dict[str, Any]:
    try:
        if body.latitude is None:
            loc = await svc.create_from_name(body.name, body.radius_km)
        else:
            loc = await svc.create(body.name, body.latitude, body.longitude, body.radius_km)
    except (LocationNotFound, GridError, OpenMeteoError) as e:
        _raise(e)
    return _out(loc)


@router.get("", summary="List locations")
async def list_locations(svc: LocationService = Depends(get_service)) -> Dict[str, Any]:
    items = [_out(x) for x in await svc.list()]
    return {"items": items, "total": len(items)}


@router.get("/{location_id}", summary="One location with its grid cells")
async def get_location(location_id: int, svc: LocationService = Depends(get_service)) -> Dict[str, Any]:
    try:
        return _out(await svc.get(location_id))
    except LocationNotFound as e:
        _raise(e)


@router.delete("/{location_id}", summary="Remove a location")
async def delete_location(location_id: int, svc: LocationService = Depends(get_service)) -> Dict[str, Any]:
    try:
        await svc.delete(location_id)
    except LocationNotFound as e:
        _raise(e)
    return {"deleted": location_id}


@router.get("/{location_id}/status", summary="Current weather, weather anomaly and data-QC flag per cell")
async def location_status(location_id: int, svc: LocationService = Depends(get_service)) -> Dict[str, Any]:
    try:
        return await svc.status(location_id)
    except (LocationNotFound, OpenMeteoError) as e:
        _raise(e)


@router.get("/{location_id}/series", summary="Hourly series per cell")
async def location_series(location_id: int, days: int = Query(7, ge=1, le=7), svc: LocationService = Depends(get_service)) -> Dict[str, Any]:
    try:
        return await svc.series(location_id, days)
    except (LocationNotFound, OpenMeteoError) as e:
        _raise(e)
