"""The ESP32 telemetry source: an MQTT subscriber (over an injected transport, mqtt_transport.py) plus a virtual-packet entry point.

NOT VERIFIED ON A REAL DEVICE: the owner has no ESP32 hardware (2026-11-21). The packet format below is this project's own definition, written
after the original app's topic layout; no firmware sends it yet. The source is tested against a fake transport only.

Topics (as in the original app): ``<prefix>/<station_id>/telemetry`` (a JSON object with temperature_c, pressure_hpa, humidity_pct, rain_mm and
optionally timestamp) and ``<prefix>/<station_id>/heartbeat`` (any payload; it only records that the device is alive). The default prefix is
``skyguard/aws``. Only the configured ESP32 station ids are accepted; a packet for another station is refused and counted.

A packet is stored as it came: a null value stays None (not filled), a value that is not a number rejects the packet, an absent timestamp means the
time of receipt, and a packet with no value at all is refused. With no MQTT host configured the source runs in virtual-packet mode only
(``POST /api/data-sources/physical/virtual-packet``): the reading is still labelled source ``esp32``, and the status says no broker is connected.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set

from backend.app.stream.mqtt_transport import MqttTransport, PahoTransport
from backend.app.stream.source import Emit
from backend.app.stream.types import BadPacket, SourceNotRunning, SourceStatus, StationInfo, StreamReading, UnknownStation, utcnow

logger = logging.getLogger(__name__)

ALIASES = {"temperature_c": ("temperature_c", "temperature"), "pressure_hpa": ("pressure_hpa", "pressure"),
           "humidity_pct": ("humidity_pct", "humidity"), "rain_mm": ("rain_mm", "rain")}
MAX_PACKET_BYTES = 4096
RETRY_S = 15.0


def _value(name: str, v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise BadPacket(f"{name} is not a finite number")
    return float(v)


def parse_packet(station_id: str, payload: Any, received_at: datetime) -> StreamReading:
    """A telemetry packet (already JSON-decoded) -> the reading. Raises BadPacket. Out-of-range numbers are kept as sent (the checks judge them)."""
    if not isinstance(payload, dict):
        raise BadPacket("the packet is not a JSON object")
    values: Dict[str, Optional[float]] = {}
    for field, names in ALIASES.items():
        got = next((payload[n] for n in names if n in payload), None)
        values[field] = _value(field, got)
    if all(v is None for v in values.values()):
        raise BadPacket("the packet holds none of temperature_c, pressure_hpa, humidity_pct, rain_mm")
    ts = payload.get("timestamp")
    if ts is None:
        when = received_at
    else:
        try:
            if isinstance(ts, (int, float)) and not isinstance(ts, bool):
                when = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            else:
                when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                when = when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)
        except (ValueError, OverflowError, OSError):
            raise BadPacket("timestamp is not an ISO time or an epoch number")
    return StreamReading(station_id, when, "esp32", **values)


class Esp32Source:
    source_id = "esp32"
    source_type = "PHYSICAL_AWS"
    name = "Physical ESP32 station"
    description = ("An ESP32 weather station publishing over MQTT, or virtual packets posted to the API. NOT verified on a real device: no "
                   "hardware exists yet.")

    def __init__(self, *, transport_factory: Callable[[], MqttTransport] = PahoTransport, clock: Callable[[], datetime] = utcnow,
                 sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep, retry_s: float = RETRY_S) -> None:
        self._factory, self._clock, self._sleep, self._retry_s = transport_factory, clock, sleep, retry_s
        self._station_ids: List[str] = []
        self._lat: Optional[float] = None
        self._lon: Optional[float] = None
        self._interval = 60.0
        self._host, self._port, self._prefix, self._user, self._password, self._tls = "", 1883, "skyguard/aws", "", "", False
        self._emit: Optional[Emit] = None
        self._state = "stopped"
        self._last_error: Optional[str] = None
        self._last_error_at: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None
        self._transport: Optional[MqttTransport] = None
        self._mqtt_up = False
        self._pending: Set[asyncio.Task] = set()
        self.heartbeats: Dict[str, datetime] = {}
        self.accepted = 0
        self.virtual = 0
        self.rejected = 0
        self.last_rejection: Optional[str] = None

    def configure(self, station_ids: Sequence[str], latitude: Optional[float], longitude: Optional[float], interval_s: float, host: str, port: int,
                  prefix: str, username: str, password: str, tls: bool) -> None:
        self._station_ids, self._lat, self._lon, self._interval = list(station_ids), latitude, longitude, interval_s
        self._host, self._port, self._prefix, self._user, self._password, self._tls = host, port, prefix, username, password, tls

    # -- the TelemetrySource interface
    def stations(self) -> Sequence[StationInfo]:
        if self._lat is None or self._lon is None:          # no coordinates, no map position: the readings are still stored
            return []
        return [StationInfo(s, s, self._lat, self._lon, None) for s in self._station_ids]

    def station_ids(self) -> List[str]:
        return list(self._station_ids)

    def status(self) -> SourceStatus:
        return SourceStatus(self._state, self._interval, self._last_error, self._last_error_at)  # type: ignore[arg-type]

    def extra_metadata(self) -> Dict[str, Any]:
        return {"verified_on_real_device": False, "mqtt": {"configured": bool(self._host), "connected": self._mqtt_up, "topic_prefix": self._prefix,
                                                            "host": self._host or None},
                "station_ids": list(self._station_ids), "packets_accepted": self.accepted, "virtual_packets": self.virtual, "packets_rejected": self.rejected,
                "last_rejection": self.last_rejection, "heartbeats": {k: v.isoformat() for k, v in self.heartbeats.items()}}

    async def start(self, emit: Emit) -> None:
        if self._state != "stopped":
            return
        self._emit = emit
        self._last_error = self._last_error_at = None
        if not self._host:
            self._state = "running"                          # virtual-packet mode: no broker to wait for
            return
        self._state = "disconnected"
        self._last_error, self._last_error_at = "not connected to the MQTT broker yet", self._clock()
        self._task = asyncio.create_task(self._supervise())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self._close_transport()
        for t in list(self._pending):
            t.cancel()
        self._pending.clear()
        self._emit, self._state, self._mqtt_up = None, "stopped", False

    # -- MQTT
    def _fail(self, reason: str) -> None:
        self._state, self._mqtt_up = "disconnected", False
        self._last_error, self._last_error_at = reason[:300], self._clock()

    async def _close_transport(self) -> None:
        t, self._transport = self._transport, None
        if t is not None:
            try:
                await t.disconnect()
            except Exception:
                logger.exception("closing the MQTT transport failed")

    async def _supervise(self) -> None:
        """Connect, subscribe, and wait until the connection is lost; then try again after a pause. Never fabricates a reading."""
        try:
            while True:
                lost = asyncio.Event()
                try:
                    self._transport = self._factory()
                    self._transport.set_handlers(self._on_message, lambda ok, why, ev=lost: self._on_connection(ok, why, ev))
                    await self._transport.connect(self._host, self._port, self._user, self._password, self._tls)
                    await self._transport.subscribe([f"{self._prefix}/+/telemetry", f"{self._prefix}/+/heartbeat"])
                    self._state, self._mqtt_up, self._last_error, self._last_error_at = "running", True, None, None
                    await lost.wait()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._fail(f"{type(exc).__name__}: {exc}")
                await self._close_transport()
                await self._sleep(self._retry_s)
        except asyncio.CancelledError:
            raise

    def _on_connection(self, ok: bool, reason: Optional[str], lost: asyncio.Event) -> None:
        if not ok:
            self._fail(f"MQTT connection lost: {reason or 'unknown'}")
            lost.set()
        else:
            self._state, self._mqtt_up, self._last_error = "running", True, None

    def _on_message(self, topic: str, payload: bytes) -> None:
        task = asyncio.ensure_future(self._handle(topic, payload))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    def _reject(self, why: str) -> None:
        self.rejected += 1
        self.last_rejection = why[:200]
        logger.info("[ESP32] packet refused: %s", self.last_rejection)

    async def _handle(self, topic: str, payload: bytes) -> None:
        parts = topic.split("/")
        prefix = self._prefix.split("/")
        if len(parts) != len(prefix) + 2 or parts[:len(prefix)] != prefix or parts[-1] not in ("telemetry", "heartbeat"):
            return self._reject(f"unexpected topic {topic[:80]!r}")
        station_id, kind = parts[-2], parts[-1]
        if station_id not in self._station_ids:
            return self._reject(f"packet for the unconfigured station {station_id[:64]!r}")
        if kind == "heartbeat":
            self.heartbeats[station_id] = self._clock()
            return
        if len(payload) > MAX_PACKET_BYTES:
            return self._reject("packet too large")
        try:
            reading = parse_packet(station_id, json.loads(payload.decode("utf-8")), self._clock())
        except (BadPacket, ValueError) as exc:
            return self._reject(f"{station_id}: {exc}")
        if self._emit is not None:
            self.accepted += 1
            await self._emit(reading)

    # -- the virtual packet
    async def inject_packet(self, payload: Any) -> StreamReading:
        """Inject ONE reading as if the device had sent it (the original app's virtual packet). The source must be running. NOT a hardware test."""
        if self._state == "stopped" or self._emit is None:
            raise SourceNotRunning("the ESP32 source is not running; select it before sending a virtual packet")
        if not isinstance(payload, dict):
            raise BadPacket("the packet is not a JSON object")
        sid = payload.get("station_id") or (self._station_ids[0] if len(self._station_ids) == 1 else None)
        if not isinstance(sid, str) or not sid:
            raise BadPacket("station_id is required (more than one ESP32 station is configured)")
        if sid not in self._station_ids:
            raise UnknownStation(f"'{sid}' is not a configured ESP32 station; configured: {', '.join(self._station_ids)}")
        reading = parse_packet(sid, payload, self._clock())
        self.virtual += 1
        await self._emit(reading)
        return reading
