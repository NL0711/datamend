"""REST endpoints of the live rain-gauge feed (backend/app/rainfall)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status

from backend.app.config import settings
from backend.app.rainfall.service import RainfallService, pick_cluster
from backend.app.rainfall.weather_union import CallBudget, WeatherUnionClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rainfall", tags=["rainfall"])

_service: Optional[RainfallService] = None


def build_service_from_settings() -> Optional[RainfallService]:
    """None (feed off) unless both WEATHER_UNION_API_KEY and WEATHER_UNION_CITY are set."""
    if not settings.WEATHER_UNION_API_KEY or not settings.WEATHER_UNION_CITY:
        return None
    client = WeatherUnionClient(settings.WEATHER_UNION_API_KEY, settings.WEATHER_UNION_BASE_URL,
                                CallBudget(settings.WEATHER_UNION_DAILY_CALL_BUDGET))
    return RainfallService(client, pick_cluster(settings.WEATHER_UNION_CITY, settings.WEATHER_UNION_MAX_STATIONS),
                           settings.WEATHER_UNION_POLL_INTERVAL_SECONDS, settings.WEATHER_UNION_ACCUMULATION_MODE,
                           settings.WEATHER_UNION_RAW_LOG_PATH)


async def start_rainfall_service() -> None:
    global _service
    _service = build_service_from_settings()
    if _service is None:
        logger.info("[RAINFALL] feed disabled (set WEATHER_UNION_API_KEY and WEATHER_UNION_CITY to enable)")
        return
    await _service.start()
    logger.info("[RAINFALL] polling %d stations every %.0fs", len(_service.stations), _service.interval)


async def stop_rainfall_service() -> None:
    global _service
    if _service is not None:
        await _service.stop()
        _service = None


def _require() -> RainfallService:
    if _service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Rainfall feed is not enabled: set WEATHER_UNION_API_KEY and WEATHER_UNION_CITY in the environment")
    return _service


@router.get("/status")
async def rainfall_status() -> Dict[str, Any]:
    return _require().status()


@router.get("/stations")
async def rainfall_stations() -> Dict[str, Any]:
    svc = _require()
    return {"status": svc.status(), "stations": [svc.station_report(sid) for sid in svc.stations]}


@router.get("/stations/{station_id}")
async def rainfall_station(station_id: str) -> Dict[str, Any]:
    svc = _require()
    if station_id not in svc.stations:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"station {station_id} is not being polled")
    return svc.station_report(station_id)
