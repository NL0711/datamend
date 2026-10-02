"""
backend/app/sources/physical_source.py
SkyGuard AI — Physical AWS Telemetry Data Source Adapter (ESP32 + BME280 via MQTT).
Listens for real physical telemetry and heartbeat topics over MQTT and normalizes into canonical telemetry.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import paho.mqtt.client as mqtt

from backend.app.config import settings
from backend.app.schemas.canonical import (
    CanonicalTelemetry,
    DataSourceStatus,
    DataSourceType,
    SourceConnectionStatus,
)
from backend.app.sources.base import BaseDataSource

logger = logging.getLogger(__name__)


class PhysicalAWSDataSource(BaseDataSource):
    """
    Adapter for Physical Automatic Weather Stations running ESP32 microcontrollers with BME280 sensors.
    Communicates via MQTT over standard telemetry and heartbeat topics.
    """

    def __init__(
        self,
        broker_host: str = settings.MQTT_BROKER_HOST,
        broker_port: int = settings.MQTT_BROKER_PORT,
        username: Optional[str] = settings.MQTT_USERNAME,
        password: Optional[str] = settings.MQTT_PASSWORD,
        use_tls: bool = settings.MQTT_TLS,
        telemetry_topic: str = settings.MQTT_TELEMETRY_TOPIC,
        heartbeat_topic: str = settings.MQTT_HEARTBEAT_TOPIC,
        timeout_seconds: float = settings.PHYSICAL_AWS_TIMEOUT_SECONDS,
        default_station_id: str = settings.PHYSICAL_DEFAULT_STATION_ID,
    ) -> None:
        super().__init__(
            source_type=DataSourceType.PHYSICAL_AWS,
            source_id="esp32_bme280",
            name="Physical AWS Microstation (ESP32 + BME280)",
            description="Real physical automatic weather station hardware streaming calibrated digital pressure, temperature, and humidity via MQTT.",
        )
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.telemetry_topic = telemetry_topic
        self.heartbeat_topic = heartbeat_topic
        self.timeout_seconds = timeout_seconds
        self.default_station_id = default_station_id

        self._mqtt_client: Optional[mqtt.Client] = None
        self._loop_task: Optional[asyncio.Task] = None
        self._device_metadata: Dict[str, Any] = {}
        self._last_heartbeat_at: Optional[datetime] = None
        self._active_stations: Dict[str, datetime] = {}
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

    async def start(self) -> None:
        """Connects to MQTT broker and begins listening to telemetry topics."""
        async with self._lock:
            if self._is_running:
                return

            self._event_loop = asyncio.get_running_loop()
            self._is_running = True
            self._status = SourceConnectionStatus.CONNECTING

            try:
                client_id = f"skyguard_backend_{int(time.time())}"
                # Handle paho-mqtt v1 / v2 callback api compatibility
                try:
                    self._mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
                except AttributeError:
                    self._mqtt_client = mqtt.Client(client_id=client_id)

                if self.username and self.password:
                    self._mqtt_client.username_pw_set(self.username, self.password)

                if self.use_tls:
                    self._mqtt_client.tls_set()

                self._mqtt_client.on_connect = self._on_connect
                self._mqtt_client.on_disconnect = self._on_disconnect
                self._mqtt_client.on_message = self._on_message

                # Run non-blocking background network loop in executor
                await asyncio.to_thread(self._connect_sync)
                logger.info("[DATA_SOURCE] PhysicalAWSDataSource connecting to MQTT broker %s:%d",
                            self.broker_host, self.broker_port)

            except Exception as e:
                logger.warning("[DATA_SOURCE] Could not connect to MQTT broker %s:%d (%s). Operating in listening/standby mode.",
                               self.broker_host, self.broker_port, e)
                self._status = SourceConnectionStatus.DISCONNECTED
                self._error_message = f"MQTT broker connection failed: {e}"

    def _connect_sync(self) -> None:
        if self._mqtt_client:
            try:
                self._mqtt_client.connect_async(self.broker_host, self.broker_port, keepalive=60)
                self._mqtt_client.loop_start()
            except Exception as e:
                logger.error("[DATA_SOURCE] MQTT synchronous connect failed: %s", e)
                self._status = SourceConnectionStatus.DISCONNECTED
                self._error_message = str(e)

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, rc: Any, *args: Any) -> None:
        # Check return code
        return_code = rc if isinstance(rc, int) else getattr(rc, "value", 0)
        if return_code == 0:
            logger.info("[DATA_SOURCE] Connected to MQTT broker %s:%d. Subscribing to topics: %s, %s",
                        self.broker_host, self.broker_port, self.telemetry_topic, self.heartbeat_topic)
            client.subscribe([(self.telemetry_topic, 1), (self.heartbeat_topic, 1)])
            self._status = SourceConnectionStatus.CONNECTED
            self._error_message = None
        else:
            logger.error("[DATA_SOURCE] MQTT connection refused with return code: %s", return_code)
            self._status = SourceConnectionStatus.ERROR
            self._error_message = f"MQTT connect refused (rc: {return_code})"

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, *args: Any) -> None:
        logger.warning("[DATA_SOURCE] Disconnected from MQTT broker.")
        if self._is_running:
            self._status = SourceConnectionStatus.DISCONNECTED

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        topic = msg.topic
        try:
            payload_str = msg.payload.decode("utf-8")
            payload = json.loads(payload_str)
        except Exception as e:
            logger.error("[DATA_SOURCE] Malformed MQTT payload on topic %s: %s", topic, e)
            return

        if "heartbeat" in topic:
            self._handle_heartbeat(payload)
        else:
            self._handle_telemetry(payload)

    def _handle_heartbeat(self, payload: Dict[str, Any]) -> None:
        st_id = payload.get("station_id") or self.default_station_id
        now = datetime.now(timezone.utc)
        self._last_heartbeat_at = now
        self._active_stations[st_id] = now
        self._device_metadata[st_id] = {
            "firmware_version": payload.get("firmware_version", "1.0.0"),
            "uptime_seconds": payload.get("uptime_seconds", 0),
            "rssi": payload.get("rssi"),
            "free_heap": payload.get("free_heap"),
            "sensor_model": payload.get("sensor_model", "BME280"),
            "last_heartbeat": now.isoformat(),
        }
        logger.info("[DATA_SOURCE] Heartbeat received from %s (uptime: %ss, RSSI: %s dBm)",
                    st_id, payload.get("uptime_seconds"), payload.get("rssi"))

    def _handle_telemetry(self, payload: Dict[str, Any]) -> None:
        """Parses incoming MQTT payload and dispatches canonical telemetry asynchronously."""
        try:
            canonical = self.normalize_mqtt_payload(payload)
            if self._event_loop and self._event_loop.is_running():
                asyncio.run_coroutine_threadsafe(self.dispatch_telemetry(canonical), self._event_loop)
            logger.info("[DATA_SOURCE] Physical AWS telemetry ingested from %s: T=%.2f°C, P=%.2fhPa, RH=%.2f%%",
                        canonical.station_id, canonical.temperature, canonical.pressure, canonical.humidity)
        except Exception as e:
            logger.error("[DATA_SOURCE] Error parsing physical AWS telemetry: %s", e)

    def normalize_mqtt_payload(self, payload: Dict[str, Any]) -> CanonicalTelemetry:
        """Converts raw physical hardware dictionary into CanonicalTelemetry."""
        raw_t = payload.get("temperature") or payload.get("temp")
        raw_p = payload.get("pressure") or payload.get("press")
        raw_rh = payload.get("humidity") or payload.get("hum") or payload.get("rh")
        st_id = str(payload.get("station_id") or self.default_station_id)

        if raw_t is None or raw_p is None or raw_rh is None:
            raise ValueError(f"Missing mandatory meteorological values in physical payload: T={raw_t}, P={raw_p}, RH={raw_rh}")

        t = float(raw_t)
        p = float(raw_p)
        rh = float(raw_rh)

        now = datetime.now(timezone.utc)
        self._active_stations[st_id] = now
        ts_val = payload.get("timestamp") or now.isoformat()

        return CanonicalTelemetry(
            station_id=st_id,
            timestamp=str(ts_val),
            temperature=round(t, 2),
            pressure=round(p, 2),
            humidity=round(rh, 2),
            source_type=DataSourceType.PHYSICAL_AWS,
            source_id=self.source_id,
            provider="Adafruit-BME280 / ESP32",
            device_id=str(payload.get("device_id") or f"ESP32-{st_id}"),
            latitude=payload.get("latitude", 18.5204),
            longitude=payload.get("longitude", 73.8567),
            elevation=payload.get("elevation", 560.0),
            unit_system="metric",
            sequence_number=payload.get("sequence_number") or (self._packet_count + 1),
            received_at=now.isoformat(),
            data_quality="GOOD",
            connectivity_status=SourceConnectionStatus.CONNECTED,
            raw_metadata={
                "uptime_seconds": payload.get("uptime_seconds"),
                "rssi": payload.get("rssi"),
                "vcc": payload.get("vcc"),
                "device_id": payload.get("device_id"),
            },
        )

    async def ingest_virtual_packet(self, payload: Dict[str, Any]) -> CanonicalTelemetry:
        """
        Allows tests, virtual hardware emitters, and developers without physical microcontrollers
        to inject genuine physical-schema MQTT packets into the live pipeline.
        """
        canonical = self.normalize_mqtt_payload(payload)
        await self.dispatch_telemetry(canonical)
        return canonical

    async def stop(self) -> None:
        """Stops MQTT client and closes connection."""
        async with self._lock:
            self._is_running = False
            self._status = SourceConnectionStatus.STOPPED
            if self._mqtt_client:
                try:
                    self._mqtt_client.loop_stop()
                    self._mqtt_client.disconnect()
                except Exception as e:
                    logger.warning("[DATA_SOURCE] MQTT client disconnect warning: %s", e)
                self._mqtt_client = None
            logger.info("[DATA_SOURCE] PhysicalAWSDataSource stopped.")

    async def get_status(self) -> DataSourceStatus:
        """Returns the current operational status of the physical hardware interface."""
        age = self.calculate_data_age_seconds()
        is_stale = bool(age and age > self.timeout_seconds)

        status = self._status
        if status == SourceConnectionStatus.CONNECTED and (self._packet_count == 0 or is_stale):
            # Connected to broker, but no physical telemetry packets received recently
            status = SourceConnectionStatus.DISCONNECTED if self._packet_count == 0 else SourceConnectionStatus.DEGRADED

        return DataSourceStatus(
            source_type=self.source_type,
            source_id=self.source_id,
            name=self.name,
            description=self.description,
            status=status,
            is_active=self._is_running,
            is_available=True,
            station_id=self.default_station_id,
            provider="Adafruit-BME280 / ESP32 Hardware",
            last_received_at=self._last_received_at.isoformat() if self._last_received_at else None,
            last_successful_fetch=self._last_successful_fetch.isoformat() if self._last_successful_fetch else None,
            last_error_at=self._last_error_at.isoformat() if self._last_error_at else None,
            error_message=self._error_message,
            data_age_seconds=round(age, 1) if age is not None else None,
            is_stale=is_stale,
            packet_count=self._packet_count,
            polling_interval_seconds=None,  # Event-driven streaming
            coordinates={"latitude": 18.5204, "longitude": 73.8567},
            metadata={
                "broker": f"{self.broker_host}:{self.broker_port}",
                "telemetry_topic": self.telemetry_topic,
                "heartbeat_topic": self.heartbeat_topic,
                "last_heartbeat": self._last_heartbeat_at.isoformat() if self._last_heartbeat_at else None,
                "devices": self._device_metadata,
            },
        )
