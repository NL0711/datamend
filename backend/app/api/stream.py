"""REST endpoints and the WebSocket of the telemetry stream, in the shapes the dashboard's service layer (frontend/src/services) expects.

Routes only parse and delegate to services (stream/service.py). Reads need the sign-in like every /api route (the middleware in api/auth.py);
changing the stream (select a source, start or stop the simulator, inject a fault) also needs the admin check (api/settings.py, require_admin).

WebSocket /ws/live (outside /api, so the HTTP middleware does not see it): with REQUIRE_LOGIN on, the connection must present a valid session,
either the X-Admin-Token header (scripts, test clients) or the ``datamend_session`` cookie that the sign-in sets (browsers cannot set headers on a
WebSocket). The cookie is read here only, never on an HTTP route, and a cookie connection must come from an allowed origin. A refused
connection is closed with code 1008 before it is accepted.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api import auth as auth_api
from backend.app.api.settings import require_admin
from backend.app.config import settings
from backend.app.db.database import get_db
from backend.app.stream import frames, runtime, service
from backend.app.stream.types import (BadSimulatorConfig, SimulatorBusy, SimulatorNotRunning, SourceStartFailed, StreamError, UnknownSource, UnknownStation,
                                      utcnow)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["stream"])
ws_router = APIRouter(tags=["stream"])
SESSION_COOKIE = auth_api.SESSION_COOKIE


def _http(e: StreamError) -> HTTPException:
    """The one place a stream error becomes an HTTP answer."""
    code = (status.HTTP_404_NOT_FOUND if isinstance(e, UnknownStation) else
            status.HTTP_409_CONFLICT if isinstance(e, (SimulatorNotRunning, SimulatorBusy)) else
            status.HTTP_422_UNPROCESSABLE_ENTITY if isinstance(e, BadSimulatorConfig) else
            status.HTTP_502_BAD_GATEWAY if isinstance(e, SourceStartFailed) else
            status.HTTP_404_NOT_FOUND if isinstance(e, UnknownSource) else status.HTTP_400_BAD_REQUEST)
    return HTTPException(code, str(e))


# ------------------------------------------------------------------------------------------------ stations and observations
@router.get("/stations")
async def list_stations(status_filter: Optional[str] = Query(None, alias="status"), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await service.list_stations(session, runtime.get_manager(), status_filter)


@router.get("/stations/{station_id}")
async def get_station(station_id: str, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    found = await service.get_station(session, runtime.get_manager(), station_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"station {station_id} not found")
    return found


@router.get("/observations")
async def list_observations(station_id: Optional[str] = None, limit: int = Query(50, ge=1, le=service.MAX_PAGE), page: int = Query(1, ge=1),
                            session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Stored stream readings, newest first. Temperature, pressure and humidity carry validation_status NO_CHECKS until their checks exist (S4)."""
    return await service.list_observations(session, station_id, limit, page)


# ------------------------------------------------------------------------------------------------ detections
# Only detections the checks really raised on stored readings. The stream has checks for rainfall only, so temperature, pressure and humidity
# readings never produce one (S4). `fleet_balanced` is accepted for the dashboard's sake and has no effect.
@router.get("/anomalies")
async def list_anomalies(station_id: Optional[str] = None, severity: Optional[str] = None, classification: Optional[str] = None,
                         limit: Optional[int] = Query(None, ge=1, le=service.MAX_PAGE), page: int = Query(1, ge=1),
                         page_size: Optional[int] = Query(None, ge=1, le=service.MAX_PAGE), offset: Optional[int] = Query(None, ge=0),
                         fleet_balanced: Optional[bool] = None, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    size = page_size or limit or 50
    res = await service.list_anomalies(session, station_id, severity, classification, size, offset if offset is not None else (page - 1) * size)
    return {**res, "page": page, "page_size": size}


@router.get("/anomalies/stats")
async def anomaly_stats(hours: int = Query(24, ge=1, le=24 * 365), session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    return await service.anomaly_stats(session, hours)


@router.get("/anomalies/alerts/active")
async def active_alerts(limit: int = Query(50, ge=1, le=service.MAX_PAGE), session: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """Medium and high detections of the last 24 hours. There is no alert store (acknowledge is NOT IMPLEMENTED): this is a filtered read of detections."""
    res = await service.list_anomalies(session, limit=limit, since=utcnow() - timedelta(hours=24), severities=("medium", "high"))
    return res["items"]


@router.get("/alerts", include_in_schema=False)
async def alerts_alias(limit: int = Query(50, ge=1, le=service.MAX_PAGE), session: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    return await active_alerts(limit, session)


@router.get("/anomalies/{anomaly_id}")
async def anomaly_detail(anomaly_id: int, session: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    found = await service.anomaly_detail(session, runtime.get_manager(), anomaly_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"anomaly {anomaly_id} not found")
    return found


# ------------------------------------------------------------------------------------------------ data sources
class SelectSource(BaseModel):
    source_type: Literal["SIMULATED", "EXTERNAL_API", "WEATHER_UNION", "PHYSICAL_AWS"]


@router.get("/data-sources")
async def list_data_sources() -> Dict[str, Any]:
    return service.source_list(runtime.get_manager())


@router.get("/data-sources/status")
async def active_data_source_status() -> Dict[str, Any]:
    found = service.active_source_status(runtime.get_manager())
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no data source is selected")
    return found


@router.post("/data-sources/select", dependencies=[Depends(require_admin)])
async def select_data_source(body: SelectSource) -> Dict[str, Any]:
    try:
        return await service.select_source(runtime.get_manager(), body.source_type)
    except UnknownSource as e:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(e))
    except StreamError as e:
        raise _http(e)


# ------------------------------------------------------------------------------------------------ simulator
class SimulationStart(BaseModel):
    station_ids: Optional[List[str]] = None
    interval_seconds: Optional[float] = Field(None, ge=0.05, le=60.0)
    noise_level: Optional[float] = Field(None, ge=0.0, le=10.0, description="multiplier of the nominal noise (1 = nominal)")
    scenario: Optional[str] = None


class Injection(BaseModel):
    anomaly_type: str
    station_id: Optional[str] = None
    parameter: str = "temperature"
    magnitude: Optional[float] = None
    duration_steps: int = Field(1, ge=1, le=200)
    decay: bool = False


@router.get("/simulation/status")
@router.get("/simulate/status", include_in_schema=False)
async def simulation_status() -> Dict[str, Any]:
    return service.simulation_status(runtime.get_manager())


@router.post("/simulation/start", dependencies=[Depends(require_admin)])
@router.post("/simulate/start", include_in_schema=False, dependencies=[Depends(require_admin)])
async def simulation_start(body: SimulationStart = SimulationStart()) -> Dict[str, Any]:
    try:
        return await service.start_simulation(runtime.get_manager(), body.station_ids, body.interval_seconds, body.noise_level, body.scenario)
    except StreamError as e:
        raise _http(e)


@router.post("/simulation/stop", dependencies=[Depends(require_admin)])
@router.post("/simulate/stop", include_in_schema=False, dependencies=[Depends(require_admin)])
async def simulation_stop() -> Dict[str, Any]:
    return await service.stop_simulation(runtime.get_manager())


@router.post("/simulate/inject", dependencies=[Depends(require_admin)])
@router.post("/simulation/inject", include_in_schema=False, dependencies=[Depends(require_admin)])
async def inject(body: Injection) -> Dict[str, Any]:
    """Queue a SYNTHETIC fault in the simulator's stream. It never affects another source."""
    try:
        return service.inject_fault(runtime.get_manager(), body.anomaly_type, body.station_id, body.parameter, body.magnitude, body.duration_steps, body.decay)
    except StreamError as e:
        raise _http(e)


# ------------------------------------------------------------------------------------------------ WebSocket
def _origin_allowed(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin")
    if not origin:
        return True                                   # not a browser
    if origin in settings.CORS_ORIGINS:
        return True
    return urlparse(origin).netloc == ws.headers.get("host")


async def _ws_authorized(ws: WebSocket) -> bool:
    if not settings.REQUIRE_LOGIN:
        return True
    header = ws.headers.get("x-admin-token")
    cookie = ws.cookies.get(SESSION_COOKIE)
    client = ws.client.host if ws.client else "unknown"
    if auth_api.too_many(auth_api._token_failures, client, auth_api.TOKEN_MAX_FAILURES):
        return False
    if await auth_api.session_valid_async(header):
        return True
    if settings.ADMIN_TOKEN and header and auth_api._same(header, settings.ADMIN_TOKEN):
        return True
    if cookie and _origin_allowed(ws) and await auth_api.session_valid_async(cookie):
        return True
    if header or cookie:
        auth_api.record_failure(auth_api._token_failures, client)
    return False


@ws_router.websocket("/ws/live")
async def live(ws: WebSocket) -> None:
    """Frames: ``status`` on connect and on every state change, ``observation`` per reading (see stream/frames.py). Client messages are ignored."""
    if not await _ws_authorized(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    manager = runtime.get_manager()
    sub = manager.subscribe()
    receive = asyncio.ensure_future(ws.receive())
    nxt = asyncio.ensure_future(sub.get())
    try:
        await ws.send_json(frames.status_frame(manager.refresh_state().as_dict()))
        while True:
            done, _ = await asyncio.wait({receive, nxt}, return_when=asyncio.FIRST_COMPLETED)
            if receive in done:
                if receive.result().get("type") == "websocket.disconnect":
                    break
                receive = asyncio.ensure_future(ws.receive())
            if nxt in done:
                await ws.send_json(nxt.result())
                nxt = asyncio.ensure_future(sub.get())
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        receive.cancel()
        nxt.cancel()
        manager.unsubscribe(sub)
