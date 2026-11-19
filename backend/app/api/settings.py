"""Dashboard settings: the Weather Union feed (key, city, interval, accumulation mode) and the AI narrator (URL, token).

Reading is open and never returns a secret. WRITING requires ADMIN_TOKEN (set in the server's .env) sent as the X-Admin-Token header; with
no ADMIN_TOKEN configured, editing is disabled (403). There are no user accounts. Saved values override .env and apply at once: the live
feed is restarted with the new settings.
"""
from __future__ import annotations

import hmac
import logging
import time
from collections import deque
from typing import Any, Deque, Dict, List, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from backend.app import runtime_settings as rs
from backend.app.api import rainfall as rainfall_api
from backend.app.config import settings
from backend.app.rainfall.service import pick_cluster
from backend.app.rainfall.weather_union import BudgetExhausted, CallBudget, WeatherUnionClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

_failures: Deque[float] = deque()
MAX_FAILURES, WINDOW_S = 10, 300.0
_TEST_TRANSPORT: Optional[httpx.AsyncBaseTransport] = None      # tests inject a mocked transport; never set in production


def require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    if not settings.ADMIN_TOKEN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "editing settings is disabled: set ADMIN_TOKEN in the server's .env and restart")
    now = time.monotonic()
    while _failures and now - _failures[0] > WINDOW_S:
        _failures.popleft()
    if len(_failures) >= MAX_FAILURES:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many wrong tokens; wait a few minutes")
    if not x_admin_token or not hmac.compare_digest(x_admin_token.encode(), settings.ADMIN_TOKEN.encode()):
        _failures.append(now)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "the admin token is missing or wrong")


def _state() -> Dict[str, Any]:
    svc = rainfall_api.rainfall_service()
    view = rs.public_view()
    view["editing_enabled"] = bool(settings.ADMIN_TOKEN)
    view["cities"] = rs.cities()
    view["accumulation_modes"] = list(rs.ACCUMULATION_MODES)
    view["interval_limits_seconds"] = [rs.MIN_INTERVAL_S, rs.MAX_INTERVAL_S]
    view["feed_running"] = svc is not None
    if svc is not None:
        st = svc.status()
        view["feed"] = {"stations": st["stations"], "poll_interval_seconds": st["poll_interval_seconds"], "calls_used_today": st["calls_used_today"],
                        "calls_remaining_today": st["calls_remaining_today"], "last_poll_at": st["last_poll_at"], "last_error": st["last_error"]}
    return view


@router.get("")
async def get_settings() -> Dict[str, Any]:
    return _state()


class SettingsUpdate(BaseModel):
    weather_union_api_key: Optional[str] = Field(None, max_length=400)
    weather_union_city: Optional[str] = Field(None, max_length=80)
    weather_union_poll_interval_seconds: Optional[float] = None
    weather_union_accumulation_mode: Optional[Literal["cumulative", "per_reading"]] = None
    narrator_url: Optional[str] = Field(None, max_length=500)
    narrator_token: Optional[str] = Field(None, max_length=400)
    clear: List[str] = Field(default_factory=list, max_length=10)       # remove a saved override (the .env value applies again)


@router.put("", dependencies=[Depends(require_admin)])
async def update_settings(body: SettingsUpdate) -> Dict[str, Any]:
    raw = body.model_dump(exclude={"clear"})
    try:
        changes = rs.validate_update(raw, body.clear)
    except rs.SettingsError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    if not changes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "nothing to change")
    rs.save_update(changes)
    logger.info("[SETTINGS] changed: %s", ", ".join(sorted(changes)))          # names only, never values
    feed_error: Optional[str] = None
    if any(k.startswith("weather_union") for k in changes):
        try:
            await rainfall_api.restart_rainfall_service()
        except Exception as e:                                                   # bad city/key combination: report, do not crash
            feed_error = f"the feed could not be restarted: {type(e).__name__}"
            logger.warning("[SETTINGS] %s", feed_error)
    state = _state()
    state["saved"] = sorted(changes)
    if feed_error:
        state["feed_error"] = feed_error
    return state


@router.post("/feed/test", dependencies=[Depends(require_admin)])
async def test_feed() -> Dict[str, Any]:
    """Make ONE call to Weather Union with the effective key (one of the day's call budget) to check that the key works."""
    eff = rs.effective()
    if not eff.weather_union_api_key or not eff.weather_union_city:
        raise HTTPException(status.HTTP_409_CONFLICT, "set a Weather Union key and a city first")
    station = pick_cluster(eff.weather_union_city, 1)[0]
    client = WeatherUnionClient(eff.weather_union_api_key, settings.WEATHER_UNION_BASE_URL, CallBudget(5), transport=_TEST_TRANSPORT)
    try:
        obs = await client.fetch_locality(station.locality_id)
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        msg = "the key was rejected (HTTP %d)" % code if code in (401, 403) else f"Weather Union answered HTTP {code}"
        return {"ok": False, "message": msg, "station_id": station.locality_id}
    except (httpx.HTTPError, BudgetExhausted, ValueError) as e:
        return {"ok": False, "message": f"could not reach Weather Union ({type(e).__name__})", "station_id": station.locality_id}
    finally:
        await client.aclose()
    if obs.status == "API_ERROR":
        return {"ok": False, "message": "Weather Union answered but reported an error for this station", "station_id": station.locality_id}
    return {"ok": True, "station_id": station.locality_id, "place": station.place, "status": obs.status,
            "message": "the key works" + ("" if obs.has_rain_fields else " (this station returned no rain fields right now)"),
            "rain_intensity": obs.rain_intensity, "rain_accumulation": obs.rain_accumulation}
