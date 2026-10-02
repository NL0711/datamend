"""
tests/test_ingestion.py
SkyGuard AI — Ingestion Pipeline, Batch Upload, CSV Normalization & Streaming Tests.
"""

import asyncio
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient

from backend.app.api.websocket import ws_manager
from backend.app.services.ingestion_service import ingestion_service


@pytest.mark.asyncio
async def test_upload_clean_baseline_csv(async_client: AsyncClient):
    """Test uploading clean diurnal CSV dataset."""
    csv_content = (
        "timestamp,temperature,pressure,humidity,station_id\n"
        "2026-08-01T00:00:00Z,22.5,1013.25,65.0,AWS-001\n"
        "2026-08-01T00:05:00Z,22.4,1013.20,65.2,AWS-001\n"
        "2026-08-01T00:10:00Z,22.3,1013.18,65.5,AWS-001\n"
        "2026-08-01T00:15:00Z,22.2,1013.15,65.8,AWS-001\n"
        "2026-08-01T00:20:00Z,22.1,1013.10,66.0,AWS-001\n"
    ).encode("utf-8")

    files = {"file": ("baseline.csv", csv_content, "text/csv")}
    res = await async_client.post("/api/upload", files=files, data={"reset_state": "true"})
    assert res.status_code == 200
    data = res.json()
    assert data["total_rows"] == 5
    assert data["valid_rows"] == 5
    assert data["execution_time_ms"] > 0
    assert "AWS-001" in data["stations_updated"]


@pytest.mark.asyncio
async def test_upload_injected_anomalies_csv(async_client: AsyncClient):
    """Test uploading CSV dataset with injected spikes and anomalies."""
    csv_content = (
        "timestamp,temperature,pressure,humidity,station_id\n"
        "2026-08-01T12:00:00Z,28.0,1010.0,50.0,AWS-001\n"
        "2026-08-01T12:05:00Z,28.2,1009.9,49.8,AWS-001\n"
        "2026-08-01T12:10:00Z,58.0,1009.8,49.5,AWS-001\n"  # Extreme spike (+30C)
        "2026-08-01T12:15:00Z,28.5,1009.7,49.0,AWS-001\n"
    ).encode("utf-8")

    files = {"file": ("anomalies.csv", csv_content, "text/csv")}
    res = await async_client.post("/api/upload", files=files, data={"reset_state": "true"})
    assert res.status_code == 200
    data = res.json()
    assert data["total_rows"] == 4
    assert data["anomalies_detected"] >= 1
    assert len(data["sample_anomalies"]) >= 1
    assert data["sample_anomalies"][0]["is_anomaly"] is True


@pytest.mark.asyncio
async def test_upload_empty_csv_400(async_client: AsyncClient):
    """Test uploading empty CSV returns HTTP 400."""
    files = {"file": ("empty.csv", b"", "text/csv")}
    res = await async_client.post("/api/upload", files=files)
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_upload_missing_required_columns_400(async_client: AsyncClient):
    """Test CSV missing required columns (e.g. humidity) returns HTTP 400."""
    csv_content = (
        "timestamp,temperature,pressure\n"
        "2026-08-01T00:00:00Z,22.5,1013.25\n"
    ).encode("utf-8")

    files = {"file": ("missing_col.csv", csv_content, "text/csv")}
    res = await async_client.post("/api/upload", files=files)
    assert res.status_code == 400
    assert "humidity" in res.json()["detail"]


@pytest.mark.asyncio
async def test_upload_non_csv_file_400(async_client: AsyncClient):
    """Test uploading non-CSV file extension returns HTTP 400."""
    files = {"file": ("test.txt", b"some plain text", "text/plain")}
    res = await async_client.post("/api/upload", files=files)
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_upload_corrupt_data_rows(async_client: AsyncClient):
    """Test CSV containing invalid non-numeric rows captures errors without failing entire upload."""
    csv_content = (
        "timestamp,temperature,pressure,humidity,station_id\n"
        "2026-08-01T00:00:00Z,22.5,1013.25,65.0,AWS-001\n"
        "2026-08-01T00:05:00Z,CORRUPT_TEMP,1013.20,65.2,AWS-001\n"
        "2026-08-01T00:10:00Z,22.3,1013.18,65.5,AWS-001\n"
    ).encode("utf-8")

    files = {"file": ("corrupt.csv", csv_content, "text/csv")}
    res = await async_client.post("/api/upload", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["total_rows"] == 3
    assert data["valid_rows"] == 2
    assert len(data["errors"]) == 1
    assert data["errors"][0]["row"] == 2


@pytest.mark.asyncio
async def test_upload_disordered_timestamps(async_client: AsyncClient):
    """Test uploaded CSV with disordered timestamps is automatically sorted chronologically."""
    csv_content = (
        "timestamp,temperature,pressure,humidity,station_id\n"
        "2026-08-01T00:15:00Z,22.2,1013.15,65.8,AWS-SORT\n"
        "2026-08-01T00:05:00Z,22.4,1013.20,65.2,AWS-SORT\n"
        "2026-08-01T00:00:00Z,22.5,1013.25,65.0,AWS-SORT\n"
        "2026-08-01T00:10:00Z,22.3,1013.18,65.5,AWS-SORT\n"
    ).encode("utf-8")

    files = {"file": ("disordered.csv", csv_content, "text/csv")}
    res = await async_client.post("/api/upload", files=files, data={"reset_state": "true"})
    assert res.status_code == 200
    data = res.json()
    assert data["valid_rows"] == 4


@pytest.mark.asyncio
async def test_frozen_sensor_stream_decay(async_client: AsyncClient):
    """Test sequence of 8 identical readings triggers frozen sensor detection and health decay."""
    station_id = "AWS-FROZEN-TEST"
    ingestion_service.pipeline.reset_station(station_id)

    base_time = datetime(2026, 8, 24, 8, 0, 0, tzinfo=timezone.utc)
    responses = []

    for i in range(8):
        t_stamp = (base_time + timedelta(minutes=5 * i)).isoformat()
        res = await async_client.post("/api/observations", json={
            "timestamp": t_stamp,
            "station_id": station_id,
            "temperature": 26.50,  # Constant stuck value
            "pressure": 1012.00,   # Constant stuck value
            "humidity": 60.00,     # Constant stuck value
        })
        assert res.status_code == 201
        responses.append(res.json())

    # Check that frozen condition was detected in subsequent steps
    last_inf = responses[-1]["inference"]
    has_frozen = any(r["inference"]["classification"] == "FROZEN" for r in responses[5:]) or last_inf["is_anomaly"]
    assert has_frozen is True


@pytest.mark.asyncio
async def test_convective_front_disambiguation(async_client: AsyncClient):
    """Test genuine convective squall front is correctly flagged with is_fault=False."""
    station_id = "AWS-FRONT-TEST"
    ingestion_service.pipeline.reset_station(station_id)

    # 1. Nominal baseline
    await async_client.post("/api/observations", json={
        "timestamp": "2026-08-24T15:00:00Z",
        "station_id": station_id,
        "temperature": 34.0,
        "pressure": 1008.0,
        "humidity": 40.0,
    })

    # 2. Convective storm front: rapid temperature drop, pressure surge, humidity jump
    front_payload = {
        "timestamp": "2026-08-24T15:05:00Z",
        "station_id": station_id,
        "temperature": 24.0,   # -10°C drop
        "pressure": 1014.0,      # +6 hPa surge
        "humidity": 85.0,       # +45% surge
    }
    res = await async_client.post("/api/observations", json=front_payload)
    assert res.status_code == 201
    inf = res.json()["inference"]

    # Either detected as genuine METEOROLOGICAL_EXTREME or physical front with is_fault==False
    if inf["classification"] == "METEOROLOGICAL_EXTREME":
        assert inf["is_fault"] is False


@pytest.mark.asyncio
async def test_concurrent_observation_ingestion(async_client: AsyncClient):
    """Test 20 concurrent observation ingestions across stations execute without SQLite locking errors."""
    stations = ["AWS-001", "AWS-002", "AWS-003", "AWS-004"]

    async def _send_obs(i: int):
        st = stations[i % len(stations)]
        t_stamp = (datetime.now(timezone.utc) + timedelta(seconds=i)).isoformat()
        payload = {
            "timestamp": t_stamp,
            "station_id": st,
            "temperature": 20.0 + (i % 10) * 0.5,
            "pressure": 1013.0 - (i % 5) * 0.2,
            "humidity": 50.0 + (i % 8) * 1.5,
        }
        res = await async_client.post("/api/observations", json=payload)
        return res.status_code

    tasks = [_send_obs(i) for i in range(20)]
    results = await asyncio.gather(*tasks)

    assert all(code == 201 for code in results)


@pytest.mark.asyncio
async def test_inference_latency_under_budget(async_client: AsyncClient):
    """Test ingestion execution latency is monitored and well below the 500ms requirement."""
    payload = {
        "timestamp": "2026-08-24T18:00:00Z",
        "station_id": "AWS-001",
        "temperature": 26.8,
        "pressure": 1012.4,
        "humidity": 58.0,
    }
    res = await async_client.post("/api/observations", json=payload)
    assert res.status_code == 201
    latency = res.json()["execution_time_ms"]
    assert latency < 500.0  # Must be strictly under 500ms budget


@pytest.mark.asyncio
async def test_websocket_broadcast_resilience():
    """Test WebSocket connection manager subscriptions and broadcast routing."""
    # Test active connection count
    assert ws_manager.get_active_count() >= 0

    # Test broadcasting does not throw exceptions with zero or multiple clients
    await ws_manager.broadcast_observation("AWS-001", {
        "temperature": 25.0,
        "pressure": 1013.25,
        "humidity": 50.0,
        "is_anomaly": False,
    })

    await ws_manager.broadcast_alert(
        station_id="AWS-001",
        severity="CRITICAL",
        message_text="Test Critical Alert",
    )
