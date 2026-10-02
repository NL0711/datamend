"""
backend/app/sources/replay_source.py
SkyGuard AI / DataMend — Historical Database & Multi-Station Replay Data Source Adapter.

Simulates real-time multi-station AWS networks from historical CSV files or database archives:
1. Enforces strict global chronological ordering across all stations (eliminates lookahead bias).
2. Executes multi-station lockstep timestamp dispatch: emits all active stations for timestamp T before advancing to T + dt.
3. Runs in-memory Tier 0 deterministic screening before dispatching to pipeline.
4. Supports configurable virtual clock pacing (real-time 1x, accelerated 10x/100x, or burst 0x).
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
from backend.app.ml.tier0_screener import tier0_screener, Tier0Result
from backend.app.schemas.canonical import (
    CanonicalTelemetry,
    DataSourceStatus,
    DataSourceType,
    SourceConnectionStatus,
)
from backend.app.sources.base import BaseDataSource

logger = logging.getLogger(__name__)


class HistoricalReplayDataSource(BaseDataSource):
    """
    Adapter for replaying multi-station historical weather datasets through the live pipeline.
    Maintains causal temporal integrity and guarantees spatial synchronization.
    """

    def __init__(
        self,
        csv_path: str = settings.HISTORICAL_DATA_PATH,
        replay_speed: float = settings.HISTORICAL_REPLAY_SPEED,
        loop_playback: bool = True,
        tick_delay_seconds: float = 1.0,
    ) -> None:
        super().__init__(
            source_type=DataSourceType.HISTORICAL_REPLAY,
            source_id="historical_replay",
            name="Historical Timescale Telemetry Replay",
            description="Chronological multi-station historical observation replay with virtual clock pacing and Tier 0 screening.",
        )
        self.csv_path = Path(csv_path)
        self.replay_speed = replay_speed
        self.loop_playback = loop_playback
        self.tick_delay_seconds = tick_delay_seconds

        self._worker_task: Optional[asyncio.Task] = None
        self._current_sim_timestamp: Optional[datetime] = None
        self._total_records_replayed: int = 0
        self._current_index: int = 0
        self._records_by_timestamp: Dict[str, List[Dict[str, Any]]] = {}
        self._sorted_timestamps: List[str] = []

    def load_dataset(self, file_path: Optional[Path] = None) -> int:
        """
        Parses CSV dataset and indexes records by chronological timestamp.
        Returns total count of loaded records.
        """
        target_path = file_path or self.csv_path
        if not target_path.exists():
            logger.warning("[HISTORICAL_REPLAY] Dataset file not found at %s", target_path)
            return 0

        grouped: Dict[str, List[Dict[str, Any]]] = {}
        total = 0

        with open(target_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = row.get("timestamp") or row.get("time")
                if not ts:
                    continue
                
                # Parse numeric values
                def _parse_float(k: str) -> Optional[float]:
                    v = row.get(k)
                    if v is None or v == "":
                        return None
                    try:
                        val = float(v)
                        return None if math.isnan(val) else val
                    except ValueError:
                        return None

                parsed_row = {
                    "station_id": row.get("station_id") or row.get("station") or "AWS-001",
                    "timestamp": ts,
                    "temperature": _parse_float("temperature") or _parse_float("temp") or _parse_float("temperature_c"),
                    "pressure": _parse_float("pressure") or _parse_float("pressure_hpa"),
                    "humidity": _parse_float("humidity") or _parse_float("relative_humidity") or _parse_float("humidity_pct"),
                    "latitude": _parse_float("latitude") or _parse_float("lat"),
                    "longitude": _parse_float("longitude") or _parse_float("lon"),
                    "elevation": _parse_float("elevation") or _parse_float("altitude"),
                }

                if ts not in grouped:
                    grouped[ts] = []
                grouped[ts].append(parsed_row)
                total += 1

        self._records_by_timestamp = grouped
        self._sorted_timestamps = sorted(list(grouped.keys()))
        logger.info(
            "[HISTORICAL_REPLAY] Loaded %d historical records spanning %d distinct timestamps from %s",
            total,
            len(self._sorted_timestamps),
            target_path.name,
        )
        return total

    async def start(self) -> None:
        """Starts the chronological replay loop."""
        async with self._lock:
            if self._is_running:
                return

            # Ensure dataset is loaded
            if not self._sorted_timestamps:
                self.load_dataset()

            if not self._sorted_timestamps:
                self._status = SourceConnectionStatus.ERROR
                self._error_message = f"Dataset at {self.csv_path} is empty or missing."
                logger.error("[HISTORICAL_REPLAY] Cannot start replay: %s", self._error_message)
                return

            self._is_running = True
            self._status = SourceConnectionStatus.RUNNING
            self._worker_task = asyncio.create_task(self._replay_loop(), name="historical_replay_worker")
            logger.info("[HISTORICAL_REPLAY] Worker loop started at %sx speed.", self.replay_speed)

    async def stop(self) -> None:
        """Gracefully halts the replay loop."""
        async with self._lock:
            if not self._is_running:
                return

            self._is_running = False
            self._status = SourceConnectionStatus.STOPPED
            if self._worker_task and not self._worker_task.done():
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
            self._worker_task = None
            logger.info("[HISTORICAL_REPLAY] Worker loop stopped.")

    async def _replay_loop(self) -> None:
        """Chronological multi-station replay worker."""
        while self._is_running:
            if self._current_index >= len(self._sorted_timestamps):
                if self.loop_playback:
                    logger.info("[HISTORICAL_REPLAY] Reached end of historical dataset; looping back to start.")
                    self._current_index = 0
                else:
                    logger.info("[HISTORICAL_REPLAY] Finished replaying historical dataset.")
                    self._status = SourceConnectionStatus.CONNECTED
                    self._is_running = False
                    break

            ts = self._sorted_timestamps[self._current_index]
            station_readings = self._records_by_timestamp.get(ts, [])

            # Emit all active stations for timestamp T (lockstep synchronization)
            for reading in station_readings:
                sid = reading["station_id"]

                # Run Tier 0 in-memory deterministic screening
                t0_res: Tier0Result = tier0_screener.screen(sid, reading)

                canonical = CanonicalTelemetry(
                    station_id=sid,
                    timestamp=ts,
                    temperature=t0_res.telemetry.get("temperature"),
                    pressure=t0_res.telemetry.get("pressure"),
                    humidity=t0_res.telemetry.get("humidity"),
                    latitude=reading.get("latitude"),
                    longitude=reading.get("longitude"),
                    elevation=reading.get("elevation"),
                    source_type=self.source_type,
                    source_id=self.source_id,
                    provider="historical_timescale_replay",
                    tier0_flag=t0_res.flag,
                    is_valid=(t0_res.status != "REJECTED"),
                    validation_flags=[t0_res.flag] if t0_res.flag != "PASS" else [],
                    received_at=datetime.now(timezone.utc).isoformat(),
                )

                await self.dispatch_telemetry(canonical)
                self._total_records_replayed += 1

            self._current_index += 1

            # Virtual clock pacing
            if self.replay_speed > 0:
                sleep_duration = max(0.01, self.tick_delay_seconds / self.replay_speed)
                await asyncio.sleep(sleep_duration)
            else:
                # Burst mode: yield event loop without sleeping
                await asyncio.sleep(0)

    async def get_status(self) -> DataSourceStatus:
        """Returns the current operational status, packet counters, and latency."""
        progress_pct = (
            round((self._current_index / len(self._sorted_timestamps)) * 100.0, 1)
            if self._sorted_timestamps
            else 0.0
        )
        return DataSourceStatus(
            source_type=self.source_type,
            source_id=self.source_id,
            name=self.name,
            description=self.description,
            station_id="AWS-REPLAY-FLEET",
            status=self._status,
            is_active=self._is_running,
            packet_count=self._total_records_replayed,
            last_received_at=self._last_received_at,
            data_age_seconds=self.calculate_data_age_seconds(),
            error_message=self._error_message,
            metadata={
                "total_timestamps": len(self._sorted_timestamps),
                "current_tick": self._current_index,
                "progress_pct": progress_pct,
                "replay_speed": self.replay_speed,
                "dataset_path": str(self.csv_path),
            },
        )
