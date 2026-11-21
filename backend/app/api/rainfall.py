"""REST endpoints of the live rain-gauge feed (backend/app/rainfall)."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.config import settings
from backend.app.rainfall.gauges import gauge_file
from backend.app.rainfall.history import build_feed_history
from backend.app.rainfall.providers import OpenMeteoProvider, RainProvider, WeatherUnionProvider
from backend.app.rainfall.service import RainfallService, pick_cluster
from backend.app.rainfall.weather_union import CallBudget, WeatherUnionClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rainfall", tags=["rainfall"])

_service: Optional[RainfallService] = None


def build_provider(eff) -> Optional[RainProvider]:
    """The weather provider chosen in the effective settings, or None when the feed cannot run: it needs a city, and a key when the provider
    needs one (Open-Meteo works without; a key there selects its commercial endpoint)."""
    from backend.app.runtime_settings import feed_enabled
    if not feed_enabled(eff):
        return None
    if eff.weather_provider == "open_meteo":
        return OpenMeteoProvider(eff.weather_union_api_key, settings.OPEN_METEO_BASE_URL, settings.OPEN_METEO_CUSTOMER_BASE_URL,
                                 CallBudget(settings.OPEN_METEO_DAILY_CALL_BUDGET))
    return WeatherUnionProvider(WeatherUnionClient(eff.weather_union_api_key, settings.WEATHER_UNION_BASE_URL,
                                                   CallBudget(settings.WEATHER_UNION_DAILY_CALL_BUDGET)))


def build_service_from_settings() -> Optional[RainfallService]:
    """None (feed off) unless the chosen provider is fully configured, in the environment or saved from the dashboard."""
    from backend.app.runtime_settings import effective
    eff = effective()
    provider = build_provider(eff)
    if provider is None:
        return None
    return RainfallService(provider, pick_cluster(eff.weather_union_city, settings.WEATHER_UNION_MAX_STATIONS),
                           eff.weather_union_poll_interval_seconds, eff.weather_union_accumulation_mode,
                           settings.WEATHER_UNION_RAW_LOG_PATH,
                           store=build_feed_history(settings.FEED_HISTORY_URL, settings.FEED_HISTORY_RETENTION_DAYS, settings.FEED_HISTORY_PATH))


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
        await refresh_live_run(session, readings, day, svc.reading_minutes, svc.mode, provider=svc.provider.name)


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
                            "Rainfall feed is not enabled: choose a weather provider and a city in Settings (Weather Union also needs a key; or set "
                            "WEATHER_UNION_API_KEY and WEATHER_UNION_CITY in .env)")
    return _service


@router.get("/status")
async def rainfall_status() -> Dict[str, Any]:
    return _require().status()


@router.get("/stations")
async def rainfall_stations() -> Dict[str, Any]:
    svc = _require()
    return {"status": svc.status(), "stations": [svc.station_report(sid) for sid in svc.stations]}


@router.get("/gauges")
async def rainfall_gauges(days: int = Query(90, ge=1, le=365)) -> Dict[str, Any]:
    """Weather Union daily totals with coordinates, the input of the ml-service ``score-gauges`` command (complete rain days only)."""
    try:
        return await gauge_file(_require(), days)
    except ValueError as e:                                  # a model provider (Open-Meteo) has no gauges to export
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))


@router.get("/stations/{station_id}")
async def rainfall_station(station_id: str) -> Dict[str, Any]:
    svc = _require()
    if station_id not in svc.stations:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"station {station_id} is not being polled")
    return svc.station_report(station_id)
