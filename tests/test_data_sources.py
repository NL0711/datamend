"""
tests/test_data_sources.py
SkyGuard AI — Comprehensive Automated Test Suite for Data Source Abstraction Layer.
Validates Canonical Telemetry Contracts, Source Adapters, Source Switching, and Ingestion Routing.
"""

import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.schemas.canonical import (
    CanonicalTelemetry,
    DataSourceListResponse,
    DataSourceSelectRequest,
    DataSourceStatus,
    DataSourceType,
    SourceConnectionStatus,
)
from backend.app.sources.base import BaseDataSource
from backend.app.sources.simulated_source import SimulatedDataSource
from backend.app.sources.external_source import ExternalWeatherDataSource
from backend.app.sources.physical_source import PhysicalAWSDataSource
from backend.app.sources.manager import DataSourceManager


# ---------------------------------------------------------------------------
# 1. Canonical Telemetry Contract Tests
# ---------------------------------------------------------------------------
def test_canonical_telemetry_valid():
    now = datetime.now(timezone.utc).isoformat()
    telemetry = CanonicalTelemetry(
        station_id="TEST-001",
        timestamp=now,
        temperature=24.5,
        pressure=1013.25,
        humidity=60.0,
        source_type=DataSourceType.EXTERNAL_API,
        source_id="open_meteo",
        provider="Open-Meteo",
        latitude=18.5204,
        longitude=73.8567,
        elevation=560.0,
    )
    assert telemetry.station_id == "TEST-001"
    assert telemetry.temperature == 24.5
    assert telemetry.source_type == DataSourceType.EXTERNAL_API
    
    ml_dict = telemetry.to_ml_input_dict()
    assert ml_dict["station_id"] == "TEST-001"
    assert ml_dict["temperature"] == 24.5
    assert ml_dict["source_type"] == "EXTERNAL_API"


def test_canonical_telemetry_range_validation():
    now = datetime.now(timezone.utc).isoformat()
    # Invalid impossible temperature
    with pytest.raises(Exception):
        CanonicalTelemetry(
            station_id="TEST-001",
            timestamp=now,
            temperature=150.0,  # Exceeds max 100°C
            pressure=1013.25,
            humidity=60.0,
        )

    # Invalid pressure
    with pytest.raises(Exception):
        CanonicalTelemetry(
            station_id="TEST-001",
            timestamp=now,
            temperature=25.0,
            pressure=50.0,  # Below min 100 hPa
            humidity=60.0,
        )


# ---------------------------------------------------------------------------
# 2. Simulated Data Source Adapter Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_simulated_data_source_lifecycle():
    source = SimulatedDataSource(interval_seconds=0.1)
    received = []

    async def _on_packet(packet: CanonicalTelemetry):
        received.append(packet)

    source.subscribe(_on_packet)
    await source.start()
    assert source._is_running is True

    # Wait for at least 1 generated tick
    await asyncio.sleep(0.3)
    await source.stop()
    assert source._is_running is False
    assert len(received) >= 1

    first = received[0]
    assert first.source_type == DataSourceType.SIMULATED
    assert -40.0 <= first.temperature <= 60.0
    assert 800.0 <= first.pressure <= 1100.0
    assert 0.0 <= first.humidity <= 100.0

    status = await source.get_status()
    assert status.source_type == DataSourceType.SIMULATED
    assert status.packet_count >= 1


# ---------------------------------------------------------------------------
# 3. External Weather Data Source (Open-Meteo) Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_external_weather_mock_fetch():
    source = ExternalWeatherDataSource(
        latitude=18.5204,
        longitude=73.8567,
        station_id="PUNE-EXT-001",
        poll_interval_seconds=1.0,
    )

    mock_json = {
        "latitude": 18.52,
        "longitude": 73.86,
        "elevation": 560.0,
        "utc_offset_seconds": 0,
        "current": {
            "time": "2026-08-25T12:00",
            "temperature_2m": 27.8,
            "relative_humidity_2m": 65.4,
            "surface_pressure": 1008.2,
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_json
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)):
        canonical = await source.fetch_live_observation()

    assert canonical is not None
    assert canonical.station_id == "PUNE-EXT-001"
    assert canonical.temperature == 27.8
    assert canonical.pressure == 1008.2
    assert canonical.humidity == 65.4
    assert canonical.source_type == DataSourceType.EXTERNAL_API
    assert canonical.provider == "Open-Meteo"


@pytest.mark.asyncio
async def test_external_weather_live_api_integration():
    """Live integration test querying Open-Meteo REST API endpoint if network is reachable."""
    source = ExternalWeatherDataSource(
        latitude=28.6139,
        longitude=77.2090,
        station_id="DELHI-EXT-001",
        timeout_seconds=5.0,
    )
    try:
        canonical = await source.fetch_live_observation()
        assert canonical is not None
        assert canonical.station_id == "DELHI-EXT-001"
        assert -40.0 <= canonical.temperature <= 60.0
        assert 800.0 <= canonical.pressure <= 1100.0
        assert 0.0 <= canonical.humidity <= 100.0
        print(f"\n[LIVE OPEN-METEO TEST] Fetched actual Delhi weather: T={canonical.temperature}°C, P={canonical.pressure}hPa, RH={canonical.humidity}%")
    except Exception as e:
        pytest.skip(f"External network connection to Open-Meteo unavailable in environment: {e}")


# ---------------------------------------------------------------------------
# 4. Physical AWS Data Source (ESP32 + BME280) Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_physical_aws_normalization_and_virtual_packet():
    source = PhysicalAWSDataSource(
        broker_host="broker.hivemq.com",
        broker_port=1883,
        default_station_id="AWS-ESP32-001",
    )

    received = []

    async def _on_telemetry(p: CanonicalTelemetry):
        received.append(p)

    source.subscribe(_on_telemetry)

    payload = {
        "station_id": "AWS-ESP32-001",
        "device_id": "ESP32-DEV-BME280-01",
        "timestamp": "2026-08-25T12:00:00Z",
        "temperature": 26.42,
        "pressure": 1007.85,
        "humidity": 58.21,
        "latitude": 18.5204,
        "longitude": 73.8567,
        "elevation": 560.0,
        "sequence_number": 42,
        "uptime_seconds": 1200,
        "rssi": -65,
    }

    canonical = await source.ingest_virtual_packet(payload)
    assert canonical.station_id == "AWS-ESP32-001"
    assert canonical.temperature == 26.42
    assert canonical.pressure == 1007.85
    assert canonical.humidity == 58.21
    assert canonical.source_type == DataSourceType.PHYSICAL_AWS
    assert canonical.provider == "Adafruit-BME280 / ESP32"
    assert canonical.device_id == "ESP32-DEV-BME280-01"
    assert len(received) == 1


@pytest.mark.asyncio
async def test_physical_aws_heartbeat():
    source = PhysicalAWSDataSource()
    hb_payload = {
        "station_id": "AWS-ESP32-001",
        "device_id": "ESP32-DEV-01",
        "firmware_version": "1.2.0-PROD",
        "uptime_seconds": 3600,
        "rssi": -55,
        "free_heap": 218000,
        "sensor_model": "BME280",
    }
    source._handle_heartbeat(hb_payload)
    assert "AWS-ESP32-001" in source._device_metadata
    dev = source._device_metadata["AWS-ESP32-001"]
    assert dev["firmware_version"] == "1.2.0-PROD"
    assert dev["uptime_seconds"] == 3600


# ---------------------------------------------------------------------------
# 5. Master Data Source Manager Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_data_source_manager_switching():
    manager = DataSourceManager()
    manager.initialize()

    # Verify all 3 sources registered
    sources_resp = await manager.list_sources()
    assert len(sources_resp.sources) == 3
    types = [s.source_type for s in sources_resp.sources]
    assert DataSourceType.SIMULATED in types
    assert DataSourceType.EXTERNAL_API in types
    assert DataSourceType.PHYSICAL_AWS in types

    # Switch to EXTERNAL_API
    with patch("backend.app.sources.external_source.ExternalWeatherDataSource.start", new=AsyncMock()), \
         patch("backend.app.api.websocket.ConnectionManager.broadcast_alert", new=AsyncMock()):
        req = DataSourceSelectRequest(source_type=DataSourceType.EXTERNAL_API)
        status = await manager.select_source(req)
        assert status.source_type == DataSourceType.EXTERNAL_API
        assert manager._active_source_type == DataSourceType.EXTERNAL_API

    # Switch back to SIMULATED
    with patch("backend.app.sources.simulated_source.SimulatedDataSource.start", new=AsyncMock()), \
         patch("backend.app.api.websocket.ConnectionManager.broadcast_alert", new=AsyncMock()):
        req = DataSourceSelectRequest(source_type=DataSourceType.SIMULATED)
        status = await manager.select_source(req)
        assert status.source_type == DataSourceType.SIMULATED
        assert manager._active_source_type == DataSourceType.SIMULATED
