"""Dashboard settings: the Weather Union feed (key, city, interval, accumulation mode) and the AI narrator (URL, token).

Reading is open and never returns a secret. WRITING requires the admin sign-in (api/auth.py; its session token is sent as X-Admin-Token) or
the ADMIN_TOKEN itself; with neither ADMIN_PASSWORD nor ADMIN_TOKEN set, editing is disabled (403). Saved values override .env and apply at once: the live
feed is restarted with the new settings.
"""
from __future__ import annotations

import hmac
import logging
import time
from collections import deque
from typing import Any, Deque, Dict, List, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.app import runtime_settings as rs
from backend.app.api import auth as auth_api
from backend.app.api import rainfall as rainfall_api
from backend.app.config import settings
from backend.app.rainfall.providers import OpenMeteoError, OpenMeteoProvider
from backend.app.rainfall.service import pick_cluster
from backend.app.rainfall.weather_union import BudgetExhausted, CallBudget, WeatherUnionClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

_failures = auth_api._token_failures             # the SAME limiter the login middleware uses for wrong tokens, per client address
MAX_FAILURES, WINDOW_S = auth_api.TOKEN_MAX_FAILURES, auth_api.WINDOW_S
_TEST_TRANSPORT: Optional[httpx.AsyncBaseTransport] = None      # tests inject a mocked transport; never set in production


def editing_enabled() -> bool:
    return bool(settings.ADMIN_TOKEN) or auth_api.login_enabled()


async def require_admin(request: Request, x_admin_token: Optional[str] = Header(None)) -> None:
    """A write needs a signed-in admin session (api/auth.py) or, for scripts, the ADMIN_TOKEN itself. Wrong tokens are limited per client address."""
    if not editing_enabled():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "editing is disabled: set ADMIN_PASSWORD (or ADMIN_TOKEN) on the server and restart")
    if await auth_api.session_valid_async(x_admin_token):
        return
    client = auth_api.client_key(request)
    if auth_api.too_many(_failures, client, MAX_FAILURES):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many wrong tokens; wait a few minutes")
    if settings.ADMIN_TOKEN and x_admin_token and hmac.compare_digest(x_admin_token.encode(), settings.ADMIN_TOKEN.encode()):
        return
    auth_api.record_failure(_failures, client)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in as admin first (the session is missing or has expired)")


def _state() -> Dict[str, Any]:
    svc = rainfall_api.rainfall_service()
    view = rs.public_view()
    view["editing_enabled"] = editing_enabled()
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
    weather_provider: Optional[Literal["weather_union", "open_meteo"]] = None
    weather_union_api_key: Optional[str] = Field(None, max_length=400)       # the weather API key, whichever provider is chosen
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


async def _test_open_meteo(eff: rs.Effective, station) -> Dict[str, Any]:
    provider = OpenMeteoProvider(eff.weather_union_api_key, settings.OPEN_METEO_BASE_URL, settings.OPEN_METEO_CUSTOMER_BASE_URL, CallBudget(5),
                                 transport=_TEST_TRANSPORT)
    base = {"station_id": station.locality_id, "place": station.place}
    try:
        obs = await provider.fetch(station)
    except OpenMeteoError as e:
        return {"ok": False, "message": f"the key was rejected ({e.reason or 'HTTP %d' % e.status})" if e.key_problem else str(e), **base}
    except (httpx.HTTPError, BudgetExhausted, ValueError) as e:
        return {"ok": False, "message": f"could not read Open-Meteo ({type(e).__name__})", **base}
    finally:
        await provider.aclose()
    latest = next((o for o in reversed(obs) if o.rain_accumulation is not None), None)
    return {"ok": True, "message": "Open-Meteo answered" + ("" if latest else " (no precipitation value for the last hours)"), "status": "OK" if latest else "NO_RAIN_FIELDS",
            "rain_intensity": latest.rain_intensity if latest else None, "rain_accumulation": latest.rain_accumulation if latest else None, **base}


@router.post("/feed/test", dependencies=[Depends(require_admin)])
async def test_feed() -> Dict[str, Any]:
    """Make ONE call to the chosen weather provider with the effective settings (one of the day's call budget) to check that it works."""
    eff = rs.effective()
    if not rs.feed_enabled(eff):
        raise HTTPException(status.HTTP_409_CONFLICT, "choose a city first" if eff.weather_provider == "open_meteo" else "set a Weather Union key and a city first")
    station = pick_cluster(eff.weather_union_city, 1)[0]
    if eff.weather_provider == "open_meteo":
        return await _test_open_meteo(eff, station)
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
