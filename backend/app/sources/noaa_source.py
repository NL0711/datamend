"""
backend/app/sources/noaa_source.py
DataMend — Real NOAA Integrated Surface Database (ISD) Data Source Adapter.

Streams real in-situ surface Automatic Weather Station (AWS) observations
from the NOAA ISD archive hosted on AWS Open Data / NOAA NCEI.
Emits real Temperature (°C), Atmospheric Pressure (hPa), and Relative Humidity (%)
in synchronized lockstep across the synoptic station topology.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.ml.screening import tier0_screener, Tier0Result
from backend.app.schemas.canonical import (
    CanonicalTelemetry,
    DataSourceStatus,
    DataSourceType,
    SourceConnectionStatus,
)
from backend.app.sources.base import BaseDataSource

logger = logging.getLogger(__name__)


class NoaaISDDataSource(BaseDataSource):
    """
    Adapter ingesting real surface observations from NOAA ISD on AWS Open Data.
    Replays real surface weather station observations in causal lockstep across all active stations.
    """

    def __init__(
        self,
        csv_path: str = "data/noaa_aws_network.csv",
        tick_interval_seconds: float = 1.5,
        loop_playback: bool = True,
    ) -> None:
        super().__init__(
            source_type=DataSourceType.NOAA_ISD,
            source_id="noaa_isd",
            name="NOAA ISD Surface AWS Network (AWS Open Data / NCEI)",
            description="Real surface Automatic Weather Station observations from NOAA Integrated Surface Database on AWS.",
        )
        self.csv_path = Path(csv_path)
        self.tick_interval_seconds = tick_interval_seconds
        self.loop_playback = loop_playback

        self._task: Optional[asyncio.Task] = None
        self._records_by_timestamp: Dict[str, List[Dict[str, Any]]] = {}
        self._sorted_timestamps: List[str] = []
        self._current_index: int = 0
        self._total_records_emitted: int = 0
        self._active_station_count: int = 0

    def load_dataset(self, file_path: Optional[Path] = None) -> int:
        """Loads and indexes real NOAA ISD observations grouped by timestamp."""
        target_path = file_path or self.csv_path
        if not target_path.exists():
            # Fallback to single-station benchmark file if network file not yet generated
            alt_path = Path("data/noaa_benchmark.csv")
            if alt_path.exists():
                target_path = alt_path
            else:
                logger.warning("[NOAA_ISD] Dataset file not found at %s or %s", target_path, alt_path)
                return 0

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        unique_stations = set()
        total = 0

        with open(target_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = row.get("timestamp") or row.get("time")
                if not ts:
                    continue

                def _parse_float(k: str) -> Optional[float]:
                    v = row.get(k)
                    if v is None or v == "":
                        return None
                    try:
                        val = float(v)
                        return None if math.isnan(val) else val
                    except ValueError:
                        return None

                station_id = row.get("station_id") or "AWS-001"
                unique_stations.add(station_id)

                parsed_row = {
                    "station_id": station_id,
                    "timestamp": ts,
                    "temperature": _parse_float("temperature") or _parse_float("temp"),
                    "pressure": _parse_float("pressure"),
                    "humidity": _parse_float("humidity") or _parse_float("rh"),
                    "latitude": _parse_float("latitude"),
                    "longitude": _parse_float("longitude"),
                    "elevation": _parse_float("elevation"),
                    "source_type": DataSourceType.NOAA_ISD,
                    "provider": row.get("provider") or "NOAA NCEI ISD-Lite",
                }

                if ts not in grouped:
                    grouped[ts] = []
                grouped[ts].append(parsed_row)
                total += 1

        self._records_by_timestamp = grouped
        self._sorted_timestamps = sorted(grouped.keys())
        self._current_index = 0
        self._active_station_count = len(unique_stations)

        logger.info(
            "[NOAA_ISD] Successfully loaded %d real NOAA observations across %d timestamps for %d stations.",
            total,
            len(self._sorted_timestamps),
            self._active_station_count,
        )
        return total

    async def start(self) -> None:
        """Starts asynchronous replay of real NOAA ISD telemetry."""
        async with self._lock:
            if self._is_running and self._task and not self._task.done():
                return

            if not self._sorted_timestamps:
                loaded = self.load_dataset()
                if loaded == 0:
                    self._status = SourceConnectionStatus.ERROR
                    self._error_message = "No NOAA ISD observations found in dataset."
                    return

            self._is_running = True
            self._status = SourceConnectionStatus.RUNNING
            self._error_message = None
            self._task = asyncio.create_task(self._replay_loop())
            logger.info("[NOAA_ISD] Started streaming NOAA ISD surface AWS feed.")

    async def stop(self) -> None:
        """Stops the NOAA ISD streaming task."""
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
            logger.info("[NOAA_ISD] Stopped streaming NOAA ISD telemetry.")

    async def _replay_loop(self) -> None:
        """Iterates through chronological timestamps emitting all stations concurrently."""
        while self._is_running:
            if self._current_index >= len(self._sorted_timestamps):
                if self.loop_playback:
                    self._current_index = 0
                    logger.info("[NOAA_ISD] Looping back to beginning of NOAA ISD dataset.")
                else:
                    self._status = SourceConnectionStatus.STOPPED
                    self._is_running = False
                    break

            current_ts = self._sorted_timestamps[self._current_index]
            station_records = self._records_by_timestamp[current_ts]

            # Ingest all stations for timestamp T concurrently
            dispatch_coros = []
            for record in station_records:
                # Tier 0 deterministic screening
                t0_eval: Tier0Result = tier0_screener.screen(
                    station_id=record["station_id"],
                    reading=record,
                    altitude_m=record.get("elevation") or 0.0,
                )

                telemetry = CanonicalTelemetry(
                    station_id=record["station_id"],
                    timestamp=record["timestamp"],
                    temperature=record["temperature"],
                    pressure=record["pressure"],
                    humidity=record["humidity"],
                    source_type=DataSourceType.NOAA_ISD,
                    source_id="noaa_isd",
                    provider=record.get("provider", "NOAA NCEI ISD-Lite"),
                    latitude=record.get("latitude"),
                    longitude=record.get("longitude"),
                    elevation=record.get("elevation"),
                    unit_system="metric",
                    tier0_flag=t0_eval.flag,
                    is_valid=(t0_eval.status != "REJECTED"),
                    validation_flags=[t0_eval.flag] if t0_eval.flag != "PASS" else [],
                    received_at=datetime.now(timezone.utc).isoformat(),
                )

                dispatch_coros.append(self.dispatch_telemetry(telemetry))
                self._total_records_emitted += 1

            if dispatch_coros:
                await asyncio.gather(*dispatch_coros, return_exceptions=True)

            self._current_index += 1
            await asyncio.sleep(self.tick_interval_seconds)

    async def get_status(self) -> DataSourceStatus:
        """Returns the current operational status of the NOAA ISD feed."""
        async with self._lock:
            return DataSourceStatus(
                source_type=self.source_type,
                source_id=self.source_id,
                name=self.name,
                description=self.description,
                status=self._status,
                is_active=self._is_running,
                is_available=True,
                station_id="NOAA-AWS-NETWORK",
                provider="NOAA NCEI ISD-Lite (AWS Open Data)",
                last_received_at=self._last_received_at.isoformat() if self._last_received_at else None,
                last_successful_fetch=self._last_successful_fetch.isoformat() if self._last_successful_fetch else None,
                last_error_at=self._last_error_at.isoformat() if self._last_error_at else None,
                error_message=self._error_message,
                data_age_seconds=self.calculate_data_age_seconds(),
                is_stale=False,
                packet_count=self._packet_count,
                polling_interval_seconds=self.tick_interval_seconds,
                coordinates={"latitude": 39.8561, "longitude": -104.6738},
                metadata={
                    "total_records_emitted": self._total_records_emitted,
                    "dataset_path": str(self.csv_path),
                    "active_stations": self._active_station_count,
                    "provider": "NOAA ISD Surface AWS",
                },
            )
