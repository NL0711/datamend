"""
backend/app/sources/manager.py
SkyGuard AI — Master Data Source Manager.
Orchestrates interchangeable telemetry sources (Simulator, Open-Meteo REST API, Physical ESP32 MQTT)
and routes canonical telemetry packets into the 5-Tier ML Quality Control and Persistence Engine.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.schemas.canonical import (
    CanonicalTelemetry,
    DataSourceListResponse,
    DataSourceSelectRequest,
    DataSourceStatus,
    DataSourceType,
    SourceConnectionStatus,
)
from backend.app.sources.base import BaseDataSource
from backend.app.sources.external_source import ExternalWeatherDataSource
from backend.app.sources.physical_source import PhysicalAWSDataSource
from backend.app.sources.simulated_source import SimulatedDataSource

logger = logging.getLogger(__name__)


class DataSourceManager:
    """
    Master coordinator for all SkyGuard AI telemetry sources.
    Maintains registered adapters, enforces single-active or multi-stream policies,
    and forwards canonical telemetry into the existing ingestion service.
    """

    def __init__(self) -> None:
        self._sources: Dict[DataSourceType, BaseDataSource] = {}
        self._active_source_type: DataSourceType = DataSourceType.SIMULATED
        self._lock = asyncio.Lock()
        self._is_initialized: bool = False
        self._last_forwarded_telemetry: Optional[CanonicalTelemetry] = None

    def initialize(self) -> None:
        """Registers the standard three telemetry adapters."""
        if self._is_initialized:
            return

        sim_source = SimulatedDataSource(interval_seconds=1.5)
        ext_source = ExternalWeatherDataSource(
            latitude=settings.EXTERNAL_WEATHER_LATITUDE,
            longitude=settings.EXTERNAL_WEATHER_LONGITUDE,
            station_id=settings.EXTERNAL_WEATHER_STATION_ID,
            station_name=settings.EXTERNAL_WEATHER_STATION_NAME,
            poll_interval_seconds=settings.EXTERNAL_API_POLL_INTERVAL_SECONDS,
            timeout_seconds=settings.EXTERNAL_API_TIMEOUT_SECONDS,
        )
        phy_source = PhysicalAWSDataSource(
            broker_host=settings.MQTT_BROKER_HOST,
            broker_port=settings.MQTT_BROKER_PORT,
            username=settings.MQTT_USERNAME,
            password=settings.MQTT_PASSWORD,
            use_tls=settings.MQTT_TLS,
            telemetry_topic=settings.MQTT_TELEMETRY_TOPIC,
            heartbeat_topic=settings.MQTT_HEARTBEAT_TOPIC,
            timeout_seconds=settings.PHYSICAL_AWS_TIMEOUT_SECONDS,
            default_station_id=settings.PHYSICAL_DEFAULT_STATION_ID,
        )

        # Register callbacks to route normalized packets into ingestion pipeline
        sim_source.subscribe(self._on_telemetry_received)
        ext_source.subscribe(self._on_telemetry_received)
        phy_source.subscribe(self._on_telemetry_received)

        self._sources[DataSourceType.SIMULATED] = sim_source
        self._sources[DataSourceType.EXTERNAL_API] = ext_source
        self._sources[DataSourceType.PHYSICAL_AWS] = phy_source

        # Set default active source from configuration
        try:
            self._active_source_type = DataSourceType(settings.DEFAULT_DATA_SOURCE.upper())
        except ValueError:
            self._active_source_type = DataSourceType.SIMULATED

        self._is_initialized = True
        logger.info("[DATA_SOURCE_MANAGER] Initialized with sources: %s. Default active: %s",
                    [s.value for s in self._sources.keys()], self._active_source_type.value)

    async def start(self) -> None:
        """Starts the default active data source upon application startup."""
        self.initialize()
        active_src = self._sources.get(self._active_source_type)
        if active_src:
            logger.info("[DATA_SOURCE_MANAGER] Starting active source: %s", self._active_source_type.value)
            await active_src.start()

    async def stop(self) -> None:
        """Stops all active data source workers upon application shutdown."""
        logger.info("[DATA_SOURCE_MANAGER] Stopping all data sources...")
        for stype, src in self._sources.items():
            try:
                await src.stop()
            except Exception as e:
                logger.error("[DATA_SOURCE_MANAGER] Error stopping source %s: %s", stype.value, e)

    async def _on_telemetry_received(self, telemetry: CanonicalTelemetry) -> None:
        """
        Receives normalized canonical telemetry from active source, forwards to ingestion service,
        and broadcasts over WebSocket with source provenance.
        """
        # Ensure only the active source (or explicitly allowed streams) forwards to ML ingestion
        if telemetry.source_type != self._active_source_type:
            logger.debug("[DATA_SOURCE_MANAGER] Dropping inactive source telemetry from %s", telemetry.source_type.value)
            return

        self._last_forwarded_telemetry = telemetry

        # Forward into existing ingestion service
        from backend.app.services.ingestion_service import ingestion_service
        try:
            obs_dict = telemetry.to_ml_input_dict()
            await ingestion_service.ingest_observation(
                obs_data=obs_dict,
                save_db=True,
                broadcast=True,
            )
        except Exception as e:
            logger.error("[DATA_SOURCE_MANAGER] Failed to ingest canonical observation from %s: %s",
                         telemetry.source_type.value, e)

    async def select_source(self, req: DataSourceSelectRequest) -> DataSourceStatus:
        """
        Switches the active telemetry data source safely:
        1. Gracefully stops current active source.
        2. Starts target data source.
        3. Updates active status.
        4. Broadcasts source switch update.
        """
        async with self._lock:
            self.initialize()
            target_type = req.source_type

            if target_type not in self._sources:
                raise ValueError(f"Unknown data source type: {target_type}")

            if target_type == self._active_source_type and self._sources[target_type]._is_running:
                logger.info("[DATA_SOURCE_MANAGER] Source %s is already active.", target_type.value)
                return await self._sources[target_type].get_status()

            logger.info("[DATA_SOURCE_MANAGER] Switching active data source from %s -> %s",
                        self._active_source_type.value, target_type.value)

            # Stop previously running source
            current_src = self._sources.get(self._active_source_type)
            if current_src:
                await current_src.stop()

            # Start newly selected source
            new_src = self._sources[target_type]
            await new_src.start()
            self._active_source_type = target_type

            status = await new_src.get_status()

            # Broadcast source switch notification over WebSocket
            from backend.app.api.websocket import ws_manager
            await ws_manager.broadcast_alert(
                station_id=status.station_id,
                severity="INFO",
                message_text=f"Telemetry Data Source switched to: {new_src.name}",
                details={
                    "source_type": target_type.value,
                    "source_id": new_src.source_id,
                    "status": status.status.value,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            return status

    async def get_active_status(self) -> DataSourceStatus:
        """Returns runtime status of the currently active source."""
        self.initialize()
        active_src = self._sources.get(self._active_source_type)
        if not active_src:
            raise RuntimeError(f"Active source {self._active_source_type} not found.")
        return await active_src.get_status()

    async def list_sources(self) -> DataSourceListResponse:
        """Returns the complete list of all registered sources and their runtime health."""
        self.initialize()
        statuses: List[DataSourceStatus] = []
        for stype, src in self._sources.items():
            st = await src.get_status()
            st.is_active = (stype == self._active_source_type and src._is_running)
            statuses.append(st)

        return DataSourceListResponse(
            active_source=self._active_source_type,
            active_source_id=self._sources[self._active_source_type].source_id,
            sources=statuses,
        )

    def get_source(self, source_type: DataSourceType) -> Optional[BaseDataSource]:
        """Retrieves a specific registered source instance."""
        self.initialize()
        return self._sources.get(source_type)

    async def configure_external_source(
        self,
        latitude: float,
        longitude: float,
        station_id: Optional[str] = None,
        station_name: Optional[str] = None,
    ) -> DataSourceStatus:
        """Dynamically reconfigures the Open-Meteo external weather source and fetches a fresh observation."""
        self.initialize()
        ext_source = self._sources.get(DataSourceType.EXTERNAL_API)
        if not isinstance(ext_source, ExternalWeatherDataSource):
            raise RuntimeError("External weather source adapter is not registered.")

        ext_source.set_location(
            latitude=latitude,
            longitude=longitude,
            station_id=station_id,
            station_name=station_name,
        )

        # If not currently active, switch active source to EXTERNAL_API
        if self._active_source_type != DataSourceType.EXTERNAL_API:
            curr = self._sources.get(self._active_source_type)
            if curr:
                await curr.stop()
            self._active_source_type = DataSourceType.EXTERNAL_API

        if not ext_source._is_running:
            await ext_source.start()

        # Trigger immediate live observation fetch
        try:
            obs = await ext_source.fetch_live_observation()
            if obs:
                await self._on_telemetry_received(obs)
        except Exception as e:
            logger.warning("[DATA_SOURCE_MANAGER] Immediate re-fetch after config failed: %s", e)

        return await ext_source.get_status()


# Global singleton instance
data_source_manager = DataSourceManager()
