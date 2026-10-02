"""
tests/test_phase1_replay_pipeline.py
Phase 1 Integration Tests: Historical Database Replay, Tier 0 Screening & TimescaleDB Persistence.
"""

import asyncio
import pytest
from pathlib import Path
from typing import List

from backend.app.schemas.canonical import CanonicalTelemetry
from backend.app.sources.replay_source import HistoricalReplayDataSource
from backend.app.ml.tier0_screener import Tier0Screener


def test_dataset_loading_and_grouping():
    """Verify HistoricalReplayDataSource parses and indexes records chronologically."""
    csv_file = Path("data/historical_benchmark_30d.csv")
    assert csv_file.exists(), "Benchmark dataset must exist before running test."

    source = HistoricalReplayDataSource(
        csv_path=str(csv_file),
        replay_speed=0.0,  # Burst
        loop_playback=False,
    )
    count = source.load_dataset()
    assert count == 11520, f"Expected 11520 records, got {count}"
    assert len(source._sorted_timestamps) == 2880, f"Expected 2880 ticks, got {len(source._sorted_timestamps)}"

    # Check ascending monotonic timestamps
    for i in range(len(source._sorted_timestamps) - 1):
        assert source._sorted_timestamps[i] <= source._sorted_timestamps[i + 1]


def test_replay_lockstep_emission_and_tier0_flags():
    """Verify lockstep multi-station emission at each timestamp tick with Tier 0 flags."""
    async def _run():
        csv_file = Path("data/historical_benchmark_30d.csv")
        source = HistoricalReplayDataSource(
            csv_path=str(csv_file),
            replay_speed=0.0,
            loop_playback=False,
            tick_delay_seconds=0.001,
        )
        source.load_dataset()

        emitted_packets: List[CanonicalTelemetry] = []

        async def _collector(telemetry: CanonicalTelemetry):
            emitted_packets.append(telemetry)

        source.subscribe(_collector)

        await source.start()
        for _ in range(50):
            if source._current_index >= 10:
                break
            await asyncio.sleep(0.01)

        await source.stop()

        assert len(emitted_packets) >= 40
        first_40 = emitted_packets[:40]
        # Verify all 4 stations present in first tick
        tick0_stations = {p.station_id for p in first_40[:4]}
        assert tick0_stations == {"AWS-001", "AWS-002", "AWS-003", "AWS-004"}

        # Verify canonical schema normalization
        for p in first_40:
            assert p.station_id.startswith("AWS-")
            assert p.provider == "historical_timescale_replay"
            assert p.is_valid is True or len(p.validation_flags) > 0

    asyncio.run(_run())


def test_tier0_screener_on_replayed_spikes():
    """Verify Tier 0 screener flags sudden spikes and null dropouts."""
    screener = Tier0Screener()

    # Step spike
    screener.screen("AWS-001", {"temperature": 25.0, "pressure": 1010.0, "humidity": 60.0})
    spike_res = screener.screen("AWS-001", {"temperature": 39.5, "pressure": 1010.0, "humidity": 60.0})
    assert spike_res.status == "SUSPICIOUS"
    assert spike_res.flag == "STEP_SPIKE"

    # Dropout
    drop_res = screener.screen("AWS-004", {"temperature": None, "pressure": 1012.0, "humidity": 50.0})
    assert drop_res.status == "REJECTED"
    assert drop_res.flag == "NULL_DROPOUT"
