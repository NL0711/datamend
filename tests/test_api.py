"""
tests/test_api.py
SkyGuard AI — Comprehensive Unit and Integration Test Suite for REST Endpoints.
"""

from datetime import datetime, timezone
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(async_client: AsyncClient):
    """Test root status metadata endpoint."""
    res = await async_client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "SkyGuard AI" in data["project"]
    assert data["docs_url"] == "/docs"


@pytest.mark.asyncio
async def test_system_health(async_client: AsyncClient):
    """Test fleet health summary endpoint."""
    res = await async_client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "total_stations" in data
    assert data["total_stations"] >= 4
    assert "average_health_score" in data
    assert 0.0 <= data["average_health_score"] <= 100.0


@pytest.mark.asyncio
async def test_list_stations(async_client: AsyncClient):
    """Test listing registered AWS stations."""
    res = await async_client.get("/api/stations")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) >= 4
    station_ids = [s["station_id"] for s in data["items"]]
    assert "AWS-001" in station_ids


@pytest.mark.asyncio
async def test_create_and_get_station(async_client: AsyncClient):
    """Test creating a new AWS station and fetching its details."""
    # Ensure clean state by deleting if already present
    await async_client.delete("/api/stations/AWS-TEST-01")
    payload = {
        "station_id": "AWS-TEST-01",
        "name": "Highland Test Station",
        "latitude": 31.1048,
        "longitude": 77.1734,
        "elevation": 2200.0,
        "status": "ACTIVE",
    }
    res = await async_client.post("/api/stations", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["station_id"] == "AWS-TEST-01"
    assert data["name"] == "Highland Test Station"

    # Get station detail
    detail_res = await async_client.get("/api/stations/AWS-TEST-01")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["station_id"] == "AWS-TEST-01"
    assert detail_data["elevation"] == 2200.0


@pytest.mark.asyncio
async def test_create_duplicate_station_400(async_client: AsyncClient):
    """Test duplicate station creation returns HTTP 400."""
    payload = {
        "station_id": "AWS-001",
        "name": "Duplicate Central Observatory",
        "latitude": 28.61,
        "longitude": 77.20,
    }
    res = await async_client.post("/api/stations", json=payload)
    assert res.status_code == 400
    assert "already exists" in res.json()["detail"]


@pytest.mark.asyncio
async def test_get_nonexistent_station_404(async_client: AsyncClient):
    """Test fetching non-existent station returns HTTP 404."""
    res = await async_client.get("/api/stations/NONEXISTENT-999")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_delete_station(async_client: AsyncClient):
    """Test deleting an existing station."""
    # Create temporary station
    await async_client.post("/api/stations", json={
        "station_id": "AWS-TEMP-DEL",
        "name": "To be deleted",
        "latitude": 0.0,
        "longitude": 0.0,
    })

    # Delete
    del_res = await async_client.delete("/api/stations/AWS-TEMP-DEL")
    assert del_res.status_code == 200

    # Verify deleted
    get_res = await async_client.get("/api/stations/AWS-TEMP-DEL")
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_station_404(async_client: AsyncClient):
    """Test deleting non-existent station returns HTTP 404."""
    res = await async_client.delete("/api/stations/AWS-NONEXISTENT-DEL")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_ingest_nominal_observation(async_client: AsyncClient):
    """Test real-time ingestion of nominal meteorological observation."""
    now_iso = datetime.now(timezone.utc).isoformat()
    payload = {
        "timestamp": now_iso,
        "station_id": "AWS-001",
        "temperature": 25.4,
        "pressure": 1013.25,
        "humidity": 55.0,
        "latitude": 28.6139,
        "longitude": 77.2090,
    }
    res = await async_client.post("/api/observations", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["persisted"] is True
    assert data["observation"]["station_id"] == "AWS-001"
    assert data["observation"]["temperature"] == 25.4
    assert data["execution_time_ms"] > 0
    assert "inference" in data
    assert 0.0 <= data["inference"]["anomaly_score"] <= 1.0
    assert 0.0 <= data["inference"]["sensor_health"] <= 100.0


@pytest.mark.asyncio
async def test_ingest_spike_observation(async_client: AsyncClient):
    """Test real-time ingestion and detection of a severe temperature spike."""
    # Warm up buffer with normal reading first
    await async_client.post("/api/observations", json={
        "timestamp": "2026-08-24T10:00:00Z",
        "station_id": "AWS-001",
        "temperature": 24.0,
        "pressure": 1012.0,
        "humidity": 60.0,
    })

    # Ingest massive +30C transient jump
    spike_payload = {
        "timestamp": "2026-08-24T10:05:00Z",
        "station_id": "AWS-001",
        "temperature": 55.0,
        "pressure": 1012.0,
        "humidity": 60.0,
    }
    res = await async_client.post("/api/observations", json=spike_payload)
    assert res.status_code == 201
    data = res.json()
    inf = data["inference"]
    assert inf["is_anomaly"] is True
    assert inf["anomaly_score"] >= 0.50
    assert inf["severity"] in ["HIGH", "CRITICAL"]
    assert inf["classification"] in ["SPIKE", "DATA_CORRUPTION"]
    assert inf["is_fault"] is True
    assert len(inf["explanation"]["contributing_features"]) > 0


@pytest.mark.asyncio
async def test_ingest_wmo_bounds_violation(async_client: AsyncClient):
    """Test physical WMO bounds violation (95°C temperature)."""
    payload = {
        "timestamp": "2026-08-24T11:00:00Z",
        "station_id": "AWS-001",
        "temperature": 95.0,
        "pressure": 1010.0,
        "humidity": 45.0,
    }
    res = await async_client.post("/api/observations", json=payload)
    assert res.status_code == 201
    data = res.json()
    inf = data["inference"]
    assert inf["is_anomaly"] is True
    assert inf["tier_scores"]["tier1_qc_flag"] is True
    assert inf["anomaly_score"] == 1.0


@pytest.mark.asyncio
async def test_ingest_malformed_observation_422(async_client: AsyncClient):
    """Test malformed observation payload rejected with HTTP 422."""
    payload = {
        "timestamp": "2026-08-24T12:00:00Z",
        "station_id": "AWS-001",
        "temperature": 999.0,  # exceeds ge=-100 le=100
        "pressure": 1013.25,
        "humidity": 50.0,
    }
    res = await async_client.post("/api/observations", json=payload)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_query_observations_paginated(async_client: AsyncClient):
    """Test querying observations with pagination."""
    res = await async_client.get("/api/observations?station_id=AWS-001&page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert data["page"] == 1
    assert data["page_size"] == 10


@pytest.mark.asyncio
async def test_query_anomalies_filtered(async_client: AsyncClient):
    """Test querying anomalies with filters."""
    res = await async_client.get("/api/anomalies?page=1&page_size=20")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_anomaly_stats_summary(async_client: AsyncClient):
    """Test anomaly statistics aggregation endpoint."""
    res = await async_client.get("/api/anomalies/stats/summary?hours=24")
    assert res.status_code == 200
    data = res.json()
    assert "total_anomalies" in data
    assert "by_severity" in data
    assert "by_classification" in data
    assert "sensor_faults" in data


@pytest.mark.asyncio
async def test_get_anomaly_detail_and_404(async_client: AsyncClient):
    """Test getting anomaly details and 404 for missing ID."""
    # Query any existing anomaly
    list_res = await async_client.get("/api/anomalies?page_size=1")
    items = list_res.json().get("items", [])
    if items:
        a_id = items[0]["id"]
        res = await async_client.get(f"/api/anomalies/{a_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == a_id
        assert "classification" in data

    # 404 on missing
    missing_res = await async_client.get("/api/anomalies/999999")
    assert missing_res.status_code == 404


@pytest.mark.asyncio
async def test_get_active_alerts(async_client: AsyncClient):
    """Test getting active alerts."""
    res = await async_client.get("/api/anomalies/alerts/active?min_severity=MEDIUM")
    assert res.status_code == 200
    alerts = res.json()
    assert isinstance(alerts, list)


@pytest.mark.asyncio
async def test_station_health_detail(async_client: AsyncClient):
    """Test station sensor health detail endpoint."""
    res = await async_client.get("/api/health/AWS-001")
    assert res.status_code == 200
    data = res.json()
    assert data["station_id"] == "AWS-001"
    assert 0.0 <= data["current_health"] <= 100.0
    assert data["health_status"] in ["EXCELLENT", "GOOD", "DEGRADED", "POOR", "CRITICAL"]
    assert "recent_history" in data


@pytest.mark.asyncio
async def test_station_health_detail_404(async_client: AsyncClient):
    """Test station health 404 for non-existent station."""
    res = await async_client.get("/api/health/NONEXISTENT-HEALTH")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_simulation_controls_lifecycle(async_client: AsyncClient):
    """Test simulation start, inject, status, and stop lifecycle."""
    # Check status
    st_res = await async_client.get("/api/simulate/status")
    assert st_res.status_code == 200

    # Start simulation
    start_res = await async_client.post("/api/simulate/start", json={
        "station_ids": ["AWS-001", "AWS-002"],
        "interval_seconds": 0.5,
        "noise_level": 0.05,
    })
    assert start_res.status_code == 200
    assert start_res.json()["running"] is True

    # Inject anomaly
    inj_res = await async_client.post("/api/simulate/inject", json={
        "station_id": "AWS-001",
        "anomaly_type": "SPIKE",
        "magnitude": 25.0,
        "duration_steps": 2,
        "parameter": "temperature",
    })
    assert inj_res.status_code == 200
    assert inj_res.json()["success"] is True

    # Stop simulation
    stop_res = await async_client.post("/api/simulate/stop")
    assert stop_res.status_code == 200
    assert stop_res.json()["running"] is False


@pytest.mark.asyncio
async def test_system_metrics_endpoint(async_client: AsyncClient):
    """Test aggregated system and ML analytics metrics endpoint."""
    res = await async_client.get("/api/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "total_observations" in data
    assert "average_inference_latency_ms" in data
    assert "p95_inference_latency_ms" in data
    assert "fleet_health_summary" in data
    assert data["system_status"] in ["HEALTHY", "DEGRADED", "CRITICAL"]


@pytest.mark.asyncio
async def test_adhoc_infer_endpoint(async_client: AsyncClient):
    """Test ad-hoc ML inference endpoint."""
    payload = {
        "timestamp": "2026-08-24T14:30:00Z",
        "station_id": "AWS-001",
        "temperature": 28.5,
        "pressure": 1011.5,
        "humidity": 62.0,
        "persist": False,
    }
    res = await async_client.post("/api/infer", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["station_id"] == "AWS-001"
    assert "anomaly_score" in data
    assert "tier_scores" in data
    assert "explanation" in data
