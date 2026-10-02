"""
backend/app/sources/external_source.py
SkyGuard AI — Real External Weather API Data Source Adapter (Open-Meteo).
Fetches actual live meteorological observations via Open-Meteo REST API and normalizes into canonical telemetry.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import httpx

from backend.app.config import settings
from backend.app.schemas.canonical import (
    CanonicalTelemetry,
    DataSourceStatus,
    DataSourceType,
    SourceConnectionStatus,
)
from backend.app.sources.base import BaseDataSource

logger = logging.getLogger(__name__)


class ExternalWeatherDataSource(BaseDataSource):
    """
    Adapter fetching live observations from Open-Meteo Global Weather API.
    Normalizes temperature_2m (°C), surface_pressure (hPa), and relative_humidity_2m (%) into canonical telemetry.
    """

    def __init__(
        self,
        latitude: float = settings.EXTERNAL_WEATHER_LATITUDE,
        longitude: float = settings.EXTERNAL_WEATHER_LONGITUDE,
        station_id: str = settings.EXTERNAL_WEATHER_STATION_ID,
        station_name: str = settings.EXTERNAL_WEATHER_STATION_NAME,
        poll_interval_seconds: float = settings.EXTERNAL_API_POLL_INTERVAL_SECONDS,
        timeout_seconds: float = settings.EXTERNAL_API_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            source_type=DataSourceType.EXTERNAL_API,
            source_id="open_meteo",
            name=f"Open-Meteo Live Weather Feed ({station_name})",
            description="Real-time global numerical weather prediction and meteorological station observation feed provided by Open-Meteo.",
        )
        self.latitude = latitude
        self.longitude = longitude
        self.station_id = station_id
        self.station_name = station_name
        self.poll_interval_seconds = max(10.0, poll_interval_seconds)
        self.timeout_seconds = timeout_seconds

        self._task: Optional[asyncio.Task] = None
        self._elevation: Optional[float] = None
        self._last_fetch_latency_ms: Optional[float] = None
        self._retry_count: int = 0
        self._max_retry_backoff: float = 60.0

    def set_location(
        self,
        latitude: float,
        longitude: float,
        station_id: Optional[str] = None,
        station_name: Optional[str] = None,
    ) -> None:
        """Dynamically reconfigures geographic coordinates and station identifiers."""
        self.latitude = latitude
        self.longitude = longitude
        if station_id:
            self.station_id = station_id
        if station_name:
            self.station_name = station_name
            self.name = f"Open-Meteo Live Weather Feed ({station_name})"
        logger.info("[DATA_SOURCE] Reconfigured location to Lat: %.4f, Lon: %.4f, Station: %s (%s)",
                    self.latitude, self.longitude, self.station_id, self.station_name)

    async def start(self) -> None:
        """Starts asynchronous polling loop for Open-Meteo."""
        async with self._lock:
            if self._is_running and self._task and not self._task.done():
                return

            self._is_running = True
            self._status = SourceConnectionStatus.CONNECTING
            self._retry_count = 0
            self._task = asyncio.create_task(self._poll_loop())
            logger.info("[DATA_SOURCE] ExternalWeatherDataSource started for station %s (interval: %.1fs)",
                        self.station_id, self.poll_interval_seconds)

    async def stop(self) -> None:
        """Stops Open-Meteo polling loop."""
        async with self._lock:
            self._is_running = False
            self._status = SourceConnectionStatus.STOPPED
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
                self._task = None
            logger.info("[DATA_SOURCE] ExternalWeatherDataSource stopped.")

    async def fetch_live_observation(self) -> Optional[CanonicalTelemetry]:
        """
        Executes a single HTTP GET request to Open-Meteo API, parses and validates values.
        Returns CanonicalTelemetry if successful, raises exception if failed.
        """
        url = settings.EXTERNAL_WEATHER_BASE_URL
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current": "temperature_2m,relative_humidity_2m,surface_pressure",
            "timezone": "UTC",
        }

        t0 = time.perf_counter()
        last_err = None
        data = None
        
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=max(self.timeout_seconds, 15.0)) as client:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    break
            except Exception as e:
                last_err = e
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    
        if data is None:
            if last_err:
                raise last_err
            raise RuntimeError("Failed to obtain telemetry from Open-Meteo after 3 attempts")

        self._last_fetch_latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        current = data.get("current", {})
        self._elevation = data.get("elevation")

        raw_t = current.get("temperature_2m")
        raw_p = current.get("surface_pressure")
        raw_rh = current.get("relative_humidity_2m")
        raw_ts = current.get("time")

        # Validate numerical presence and validity (Reject NaN/None/Infinity)
        if raw_t is None or raw_p is None or raw_rh is None:
            raise ValueError(f"Open-Meteo response missing required fields: T={raw_t}, P={raw_p}, RH={raw_rh}")

        try:
            t = float(raw_t)
            p = float(raw_p)
            rh = float(raw_rh)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Non-numeric values in Open-Meteo response: {e}")

        # Format ISO timestamp
        if raw_ts:
            ts_str = f"{raw_ts}:00Z" if len(raw_ts) == 16 else raw_ts
        else:
            ts_str = datetime.now(timezone.utc).isoformat()

        canonical = CanonicalTelemetry(
            station_id=self.station_id,
            timestamp=ts_str,
            temperature=round(t, 2),
            pressure=round(p, 2),
            humidity=round(rh, 2),
            source_type=DataSourceType.EXTERNAL_API,
            source_id=self.source_id,
            provider="Open-Meteo",
            latitude=self.latitude,
            longitude=self.longitude,
            elevation=self._elevation,
            unit_system="metric",
            sequence_number=self._packet_count + 1,
            received_at=datetime.now(timezone.utc).isoformat(),
            data_quality="GOOD",
            connectivity_status=SourceConnectionStatus.CONNECTED,
            raw_metadata={
                "fetch_latency_ms": self._last_fetch_latency_ms,
                "elevation": self._elevation,
                "utc_offset_seconds": data.get("utc_offset_seconds"),
            },
        )
        return canonical

    async def _poll_loop(self) -> None:
        """Periodic background polling loop with exponential backoff on error."""
        logger.info("[DATA_SOURCE] Beginning Open-Meteo polling loop...")
        while self._is_running:
            try:
                canonical = await self.fetch_live_observation()
                if canonical:
                    self._status = SourceConnectionStatus.CONNECTED
                    self._retry_count = 0
                    await self.dispatch_telemetry(canonical)
                    logger.info("[DATA_SOURCE] Open-Meteo observation received: T=%.1f°C, P=%.1fhPa, RH=%.1f%% (lat=%.2f, lon=%.2f, latency=%.1fms)",
                                canonical.temperature, canonical.pressure, canonical.humidity,
                                self.latitude, self.longitude, self._last_fetch_latency_ms or 0.0)

                await asyncio.sleep(self.poll_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._last_error_at = datetime.now(timezone.utc)
                self._error_message = f"Open-Meteo fetch failed: {e}"
                self._retry_count += 1
                backoff = min(self._max_retry_backoff, 5.0 * (2 ** (self._retry_count - 1)))
                self._status = SourceConnectionStatus.DEGRADED if self._packet_count > 0 else SourceConnectionStatus.DISCONNECTED
                logger.warning("[DATA_SOURCE] Open-Meteo error (attempt %d): %s. Backing off for %.1fs",
                               self._retry_count, e, backoff)
                await asyncio.sleep(backoff)

    async def get_status(self) -> DataSourceStatus:
        """Returns the current operational status of the external API adapter."""
        age = self.calculate_data_age_seconds()
        is_stale = bool(age and age > (self.poll_interval_seconds * 2.5))
        status = self._status
        if is_stale and status == SourceConnectionStatus.CONNECTED:
            status = SourceConnectionStatus.DEGRADED

        return DataSourceStatus(
            source_type=self.source_type,
            source_id=self.source_id,
            name=self.name,
            description=self.description,
            status=status,
            is_active=self._is_running,
            is_available=True,
            station_id=self.station_id,
            provider="Open-Meteo",
            last_received_at=self._last_received_at.isoformat() if self._last_received_at else None,
            last_successful_fetch=self._last_successful_fetch.isoformat() if self._last_successful_fetch else None,
            last_error_at=self._last_error_at.isoformat() if self._last_error_at else None,
            error_message=self._error_message,
            data_age_seconds=round(age, 1) if age is not None else None,
            is_stale=is_stale,
            packet_count=self._packet_count,
            polling_interval_seconds=self.poll_interval_seconds,
            coordinates={"latitude": self.latitude, "longitude": self.longitude},
            metadata={
                "station_name": self.station_name,
                "elevation": self._elevation,
                "last_fetch_latency_ms": self._last_fetch_latency_ms,
            },
        )
