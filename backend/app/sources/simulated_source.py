"""
backend/app/sources/simulated_source.py
SkyGuard AI — Simulated Telemetry Data Source Adapter.
Wraps the multi-station DiurnalGenerator and programmatic Anomaly Injector into BaseDataSource.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.schemas.canonical import (
    CanonicalTelemetry,
    DataSourceStatus,
    DataSourceType,
    SourceConnectionStatus,
)
from backend.app.sources.base import BaseDataSource
from backend.simulator.diurnal_generator import DiurnalGenerator, StationConfig, PRESETS
from backend.app.services.simulation_service import simulation_service

logger = logging.getLogger(__name__)


class SimulatedDataSource(BaseDataSource):
    """
    Adapter integrating SkyGuard's Diurnal Atmospheric Simulator into the Data Source Layer.
    Emits canonical telemetry for simulated AWS stations and handles anomaly injections.
    """

    def __init__(self, interval_seconds: float = 1.5) -> None:
        super().__init__(
            source_type=DataSourceType.SIMULATED,
            source_id="diurnal_generator",
            name="SkyGuard Diurnal Atmospheric Simulator",
            description="Synthetic meteorological generator modeling diurnal solar radiation, Magnus-Tetens thermodynamics, and barometric tides.",
        )
        self.interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._station_id: str = "AWS-001"

    async def start(self) -> None:
        """Starts background diurnal generation loop."""
        async with self._lock:
            if self._is_running and self._task and not self._task.done():
                return

            self._is_running = True
            self._status = SourceConnectionStatus.RUNNING
            self._task = asyncio.create_task(self._run_loop())
            logger.info("[DATA_SOURCE] SimulatedDataSource started (interval: %.2fs)", self.interval_seconds)

    async def stop(self) -> None:
        """Stops background diurnal generation loop."""
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
            logger.info("[DATA_SOURCE] SimulatedDataSource stopped.")

    async def _run_loop(self) -> None:
        """Asynchronous generation tick loop."""
        try:
            while self._is_running:
                now_ts = datetime.now(timezone.utc)

                # Iterate through active stations in simulation service
                for st_id, generator in simulation_service._generators.items():
                    prev_state = simulation_service._generator_states.get(st_id)
                    telemetry, new_state = generator.generate_streaming_step(now_ts, prev_state=prev_state)
                    simulation_service._generator_states[st_id] = new_state

                    # Apply any active anomaly injections
                    modified = simulation_service._apply_injection(telemetry, st_id)

                    # Build canonical telemetry
                    canonical = CanonicalTelemetry(
                        station_id=st_id,
                        timestamp=modified.get("timestamp") or now_ts.isoformat(),
                        temperature=float(modified["temperature"]),
                        pressure=float(modified["pressure"]),
                        humidity=float(modified["humidity"]),
                        source_type=DataSourceType.SIMULATED,
                        source_id=self.source_id,
                        provider="SkyGuard-DiurnalEngine",
                        latitude=generator.station_config.latitude if hasattr(generator, "station_config") else 28.6139,
                        longitude=generator.station_config.longitude if hasattr(generator, "station_config") else 77.2090,
                        elevation=generator.station_config.elevation if hasattr(generator, "station_config") else 216.0,
                        unit_system="metric",
                        sequence_number=self._packet_count + 1,
                        received_at=now_ts.isoformat(),
                        data_quality="GOOD",
                        connectivity_status=SourceConnectionStatus.RUNNING,
                        raw_metadata={"scenario": "diurnal_solar_cycle"},
                    )

                    await self.dispatch_telemetry(canonical)

                await asyncio.sleep(self.interval_seconds)

        except asyncio.CancelledError:
            logger.info("[DATA_SOURCE] Simulated loop cancelled.")
        except Exception as e:
            logger.error("[DATA_SOURCE] Error in SimulatedDataSource loop: %s", e)
            self._status = SourceConnectionStatus.ERROR
            self._error_message = str(e)
            self._is_running = False

    async def get_status(self) -> DataSourceStatus:
        """Returns the current runtime status of the simulator."""
        age = self.calculate_data_age_seconds()
        return DataSourceStatus(
            source_type=self.source_type,
            source_id=self.source_id,
            name=self.name,
            description=self.description,
            status=self._status,
            is_active=self._is_running,
            is_available=True,
            station_id=self._station_id,
            provider="SkyGuard Diurnal Engine",
            last_received_at=self._last_received_at.isoformat() if self._last_received_at else None,
            last_successful_fetch=self._last_successful_fetch.isoformat() if self._last_successful_fetch else None,
            last_error_at=self._last_error_at.isoformat() if self._last_error_at else None,
            error_message=self._error_message,
            data_age_seconds=round(age, 1) if age is not None else None,
            is_stale=bool(age and age > 30.0),
            packet_count=self._packet_count,
            polling_interval_seconds=self.interval_seconds,
            coordinates={"latitude": 28.6139, "longitude": 77.2090},
            metadata={"active_stations": list(simulation_service._generators.keys())},
        )
