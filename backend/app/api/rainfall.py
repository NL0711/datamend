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
    """None (feed off) unless both a Weather Union key and a city are set, in the environment or saved from the dashboard."""
    from backend.app.runtime_settings import effective
    eff = effective()
    if not eff.weather_union_api_key or not eff.weather_union_city:
        return None
    client = WeatherUnionClient(eff.weather_union_api_key, settings.WEATHER_UNION_BASE_URL,
                                CallBudget(settings.WEATHER_UNION_DAILY_CALL_BUDGET))
    return RainfallService(client, pick_cluster(eff.weather_union_city, settings.WEATHER_UNION_MAX_STATIONS),
                           eff.weather_union_poll_interval_seconds, eff.weather_union_accumulation_mode,
                           settings.WEATHER_UNION_RAW_LOG_PATH)


async def refresh_live_run_from_service(svc: RainfallService) -> None:
    """After each poll: re-score the current rain day and store it as the one open live run (spec section 5)."""
    from datetime import datetime, timezone

    from backend.app.db.database import get_db_context
    from backend.app.rainfall.daily import rain_day
    from backend.app.validation.runs import refresh_live_run

    day = rain_day(datetime.now(timezone.utc))
    readings = svc.readings(day)
    if not readings:
        return
    async with get_db_context() as session:
        await refresh_live_run(session, readings, day, svc.interval / 60.0, svc.mode)


async def start_rainfall_service() -> None:
    global _service
    _service = build_service_from_settings()
    if _service is None:
        logger.info("[RAINFALL] feed disabled (set WEATHER_UNION_API_KEY and WEATHER_UNION_CITY to enable)")
        return
    _service.on_poll = refresh_live_run_from_service
    await _service.start()
    logger.info("[RAINFALL] polling %d stations every %.0fs", len(_service.stations), _service.interval)


async def restart_rainfall_service() -> bool:
    """Apply changed settings: stop the feed and start it again from the effective settings. Returns whether it is now running.
    The call budget restarts too, so the dashboard's polling interval is still raised if the budget would be exceeded."""
    await stop_rainfall_service()
    await start_rainfall_service()
    return _service is not None


def rainfall_service() -> Optional[RainfallService]:
    return _service


async def stop_rainfall_service() -> None:
    global _service
    if _service is not None:
        await _service.stop()
        _service = None


def _require() -> RainfallService:
    if _service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Rainfall feed is not enabled: add a Weather Union key and a city in Settings (or WEATHER_UNION_API_KEY and WEATHER_UNION_CITY in .env)")
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
