"""
backend/app/api/websocket.py
SkyGuard AI — WebSocket Live Telemetry Streaming & Multi-Client Connection Manager.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Manages active WebSocket connections with station-specific subscriptions and broadcast filtering."""

    def __init__(self) -> None:
        # Maps WebSocket connection -> Set of subscribed station IDs (or {"*"} / {"ALL"})
        self._active_connections: Dict[WebSocket, Set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, initial_stations: Optional[List[str]] = None) -> None:
        await websocket.accept()
        subs = set(initial_stations) if initial_stations else {"*"}
        async with self._lock:
            self._active_connections[websocket] = subs
        logger.info("WebSocket connected: %s (subscribed to: %s)", websocket.client, subs)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._active_connections.pop(websocket, None)
        logger.info("WebSocket disconnected: %s", getattr(websocket, "client", "unknown"))

    async def subscribe(self, websocket: WebSocket, stations: List[str]) -> None:
        async with self._lock:
            if websocket in self._active_connections:
                if "*" in stations or "ALL" in [s.upper() for s in stations]:
                    self._active_connections[websocket] = {"*"}
                else:
                    self._active_connections[websocket].discard("*")
                    self._active_connections[websocket].update(stations)

    async def unsubscribe(self, websocket: WebSocket, stations: List[str]) -> None:
        async with self._lock:
            if websocket in self._active_connections:
                for st in stations:
                    self._active_connections[websocket].discard(st)
                if not self._active_connections[websocket]:
                    self._active_connections[websocket] = {"*"}

    def get_active_count(self) -> int:
        return len(self._active_connections)

    async def broadcast_observation(self, station_id: str, data: Dict[str, Any]) -> None:
        """Broadcasts real-time observation and inference payload to subscribed clients."""
        payload = {
            "type": "observation",
            "station_id": station_id,
            "data": data,
            "server_time": datetime.now(timezone.utc).isoformat(),
        }
        message = json.dumps(payload, default=str)
        dead_clients: List[WebSocket] = []

        async with self._lock:
            targets = [
                ws for ws, subs in self._active_connections.items()
                if "*" in subs or "ALL" in subs or station_id in subs
            ]

        if not targets:
            return

        async def _safe_send(ws: WebSocket) -> None:
            try:
                await asyncio.wait_for(ws.send_text(message), timeout=1.5)
            except Exception:
                dead_clients.append(ws)

        await asyncio.gather(*[_safe_send(ws) for ws in targets], return_exceptions=True)

        if dead_clients:
            async with self._lock:
                for ws in dead_clients:
                    self._active_connections.pop(ws, None)

    async def broadcast_alert(
        self, station_id: str, severity: str, message_text: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Broadcasts an operational alert to subscribed clients."""
        payload = {
            "type": "alert",
            "station_id": station_id,
            "severity": severity,
            "message": message_text,
            "details": details or {},
            "server_time": datetime.now(timezone.utc).isoformat(),
        }
        message = json.dumps(payload, default=str)
        dead_clients: List[WebSocket] = []

        async with self._lock:
            targets = [
                ws for ws, subs in self._active_connections.items()
                if "*" in subs or "ALL" in subs or station_id in subs
            ]

        if not targets:
            return

        async def _safe_send(ws: WebSocket) -> None:
            try:
                await asyncio.wait_for(ws.send_text(message), timeout=1.5)
            except Exception:
                dead_clients.append(ws)

        await asyncio.gather(*[_safe_send(ws) for ws in targets], return_exceptions=True)

        if dead_clients:
            async with self._lock:
                for ws in dead_clients:
                    self._active_connections.pop(ws, None)


# Global WebSocket connection manager singleton
ws_manager = ConnectionManager()


@router.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """
    Bi-directional live telemetry and operational alerts WebSocket endpoint.
    Clients can subscribe to specific stations, send heartbeats (ping), or trigger actions.
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial connection ack
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": "Connected to SkyGuard AI Live Telemetry Stream",
            "server_time": datetime.now(timezone.utc).isoformat(),
        }))

        while True:
            text_data = await websocket.receive_text()
            try:
                msg = json.loads(text_data)
                msg_type = msg.get("type", "").lower()

                if msg_type == "subscribe":
                    stations = msg.get("stations", ["*"])
                    if isinstance(stations, str):
                        stations = [stations]
                    await ws_manager.subscribe(websocket, stations)
                    await websocket.send_text(json.dumps({
                        "type": "subscribed",
                        "stations": stations,
                    }))

                elif msg_type == "unsubscribe":
                    stations = msg.get("stations", [])
                    if isinstance(stations, str):
                        stations = [stations]
                    await ws_manager.unsubscribe(websocket, stations)
                    await websocket.send_text(json.dumps({
                        "type": "unsubscribed",
                        "stations": stations,
                    }))

                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "client_time": msg.get("client_time"),
                        "server_time": datetime.now(timezone.utc).isoformat(),
                    }))

                elif msg_type == "inject_anomaly":
                    # Dynamic anomaly injection via WebSocket command
                    from backend.app.services.simulation_service import simulation_service
                    from backend.app.schemas.schemas import AnomalyInjectRequest
                    
                    payload = msg.get("payload", {})
                    req = AnomalyInjectRequest(**payload)
                    res = await simulation_service.inject_anomaly(req)
                    await websocket.send_text(json.dumps({
                        "type": "inject_response",
                        "data": res.model_dump(),
                    }))

                else:
                    await websocket.send_text(json.dumps({
                        "type": "ack",
                        "received": msg,
                    }))

            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON format",
                }))
            except Exception as e:
                logger.error("Error processing websocket message: %s", e)
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": str(e),
                }))

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket unhandled exception: %s", e)
        await ws_manager.disconnect(websocket)
