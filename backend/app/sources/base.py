"""
backend/app/sources/base.py
SkyGuard AI — Abstract Base Class for Real-Time Telemetry Data Sources.
Defines the standard lifecycle, subscription, and health contract for all adapters.
"""

from __future__ import annotations

import abc
import asyncio
import logging
from typing import Any, Callable, Coroutine, List, Optional
from datetime import datetime, timezone

from backend.app.schemas.canonical import (
    CanonicalTelemetry,
    DataSourceStatus,
    DataSourceType,
    SourceConnectionStatus,
)

logger = logging.getLogger(__name__)

TelemetryCallback = Callable[[CanonicalTelemetry], Coroutine[Any, Any, None]]


class BaseDataSource(abc.ABC):
    """
    Abstract Base Class for SkyGuard AI Telemetry Data Sources.
    Subclasses wrap specific telemetry providers (Simulator, Open-Meteo REST API, Physical MQTT/ESP32).
    """

    def __init__(self, source_type: DataSourceType, source_id: str, name: str, description: str) -> None:
        self.source_type = source_type
        self.source_id = source_id
        self.name = name
        self.description = description
        
        self._is_running: bool = False
        self._status: SourceConnectionStatus = SourceConnectionStatus.STOPPED
        self._subscribers: List[TelemetryCallback] = []
        self._lock = asyncio.Lock()
        
        # Provenance and Health tracking
        self._packet_count: int = 0
        self._last_received_at: Optional[datetime] = None
        self._last_successful_fetch: Optional[datetime] = None
        self._last_error_at: Optional[datetime] = None
        self._error_message: Optional[str] = None

    @abc.abstractmethod
    async def start(self) -> None:
        """Starts the data ingestion worker or connection loop."""
        pass

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stops the data ingestion worker gracefully."""
        pass

    @abc.abstractmethod
    async def get_status(self) -> DataSourceStatus:
        """Returns the current operational status, packet counters, and latency."""
        pass

    async def health_check(self) -> bool:
        """Verifies if the source is currently healthy and receiving/generating valid data."""
        return self._is_running and self._status in [SourceConnectionStatus.CONNECTED, SourceConnectionStatus.RUNNING]

    def subscribe(self, callback: TelemetryCallback) -> None:
        """Registers a callback to receive normalized canonical telemetry packets."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: TelemetryCallback) -> None:
        """Removes a registered callback."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def dispatch_telemetry(self, telemetry: CanonicalTelemetry) -> None:
        """Dispatches a normalized canonical telemetry packet to all registered subscribers."""
        self._packet_count += 1
        self._last_received_at = datetime.now(timezone.utc)
        self._last_successful_fetch = self._last_received_at
        self._error_message = None

        if not self._subscribers:
            return

        tasks = [cb(telemetry) for cb in self._subscribers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                logger.error("Error in telemetry subscriber callback for source %s: %s", self.source_id, r)

    def calculate_data_age_seconds(self) -> Optional[float]:
        """Calculates seconds elapsed since the last received telemetry packet."""
        if not self._last_received_at:
            return None
        return (datetime.now(timezone.utc) - self._last_received_at).total_seconds()
