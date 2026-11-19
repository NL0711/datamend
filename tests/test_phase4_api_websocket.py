"""
tests/test_phase4_api_websocket.py
DataMend — Test Suite for Phase 4 Operational Serving, REST APIs & WebSocket Broadcaster.
"""

from datetime import datetime, timezone
import pytest
from httpx import AsyncClient

from backend.app.api.websocket import ws_manager


@pytest.mark.asyncio
async def test_task_4_1_process_telemetry_nominal(async_client: AsyncClient):
    """Verifies POST /api/telemetry/process for nominal observation."""
    payload = {
        "station_id": "AWS-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature_c": 26.5,
        "pressure_hpa": 1012.0,
        "humidity_pct": 55.0,
        "elevation_m": 215.0,
        "persist": False,
    }
    res = await async_client.post("/api/telemetry/process", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["station_id"] == "AWS-001"
    assert data["predicted_class"] == "NORMAL"
    assert data["is_fault"] is False
    assert 0.0 <= data["anomaly_score"] <= 0.50
    assert "explanation" in data
    assert "summary" in data["explanation"]
    assert "imputation" in data
    assert data["imputation"]["applied"] is False
    assert "health" in data
    assert data["health"]["sensor_health_index"] >= 80.0
    assert data["latency_ms"] <= 200.0


@pytest.mark.asyncio
async def test_task_4_1_process_telemetry_spike_and_imputation(async_client: AsyncClient):
    """Verifies POST /api/telemetry/process detects spike, attributes cause, and imputes value."""
    payload = {
        "station_id": "AWS-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature_c": 45.0,  # Sudden +19°C spike
        "pressure_hpa": 1012.0,
        "humidity_pct": 55.0,
        "elevation_m": 215.0,
        "persist": False,
    }
    res = await async_client.post("/api/telemetry/process", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["predicted_class"] == "SPIKE"
    assert data["is_fault"] is True
    assert data["anomaly_score"] > 0.50
    # XAI Explanation checks
    assert len(data["explanation"]["top_drivers"]) >= 1
    assert "temperature" in data["explanation"]["top_drivers"][0]
    # Safe Imputation checks
    assert data["imputation"]["applied"] is True
    assert data["imputation"]["parameter"] == "temperature_c"
    assert data["imputation"]["imputed_value"] is not None
    assert abs(data["imputation"]["imputed_value"] - 45.0) > 3.0  # Imputed value corrected downward


@pytest.mark.asyncio
async def test_task_4_1_process_telemetry_thermodynamic_corruption(async_client: AsyncClient):
    """Verifies physical consistency violation triggers DATA_CORRUPTION."""
    payload = {
        "station_id": "AWS-002",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature_c": 15.0,
        "pressure_hpa": 1013.0,
        "humidity_pct": 125.0,  # Supersaturation / illegal humidity
        "elevation_m": 100.0,
        "persist": False,
    }
    res = await async_client.post("/api/telemetry/process", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["predicted_class"] in ("DATA_CORRUPTION", "SPIKE")
    assert data["is_fault"] is True


@pytest.mark.asyncio
async def test_task_4_1_get_station_predictive_health(async_client: AsyncClient):
    """Verifies GET /api/stations/{id}/health returns SHI score and degradation metrics."""
    res = await async_client.get("/api/stations/AWS-001/health")
    assert res.status_code == 200
    data = res.json()
    assert data["station_id"] == "AWS-001"
    assert 0.0 <= data["sensor_health_index"] <= 100.0
    assert data["status"] in ("EXCELLENT", "STABLE", "DEGRADED", "CRITICAL")
    assert "degradation_slope_per_hour" in data
    assert "consecutive_frozen_streak" in data


@pytest.mark.asyncio
async def test_task_4_4_operator_feedback_lifecycle(async_client: AsyncClient):
    """Verifies operator feedback submission and validation."""
    # 1. Valid feedback submission
    feedback_payload = {
        "event_id": "1",
        "operator_id": "IMD_ANALYST_01",
        "verification_status": "CONFIRMED_FAULT",
        "override_class": "SPIKE",
        "imputation_accepted": True,
        "notes": "Verified against radar echo; confirmed hardware sensor spike.",
    }
    res = await async_client.post("/api/feedback", json=feedback_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["event_id"] == "1"
    assert data["operator_id"] == "IMD_ANALYST_01"
    assert data["verification_status"] == "CONFIRMED_FAULT"
    assert data["imputation_accepted"] is True

    # 2. Invalid status rejection
    invalid_payload = {
        "event_id": "1",
        "operator_id": "IMD_ANALYST_01",
        "verification_status": "INVALID_STATUS_CODE",
        "imputation_accepted": False,
    }
    bad_res = await async_client.post("/api/feedback", json=invalid_payload)
    assert bad_res.status_code == 400


@pytest.mark.asyncio
async def test_task_4_2_websocket_broadcaster_dispatch():
    """Verifies WebSocket ConnectionManager broadcast_phase3_event handles connected client dispatch without error."""
    # Test broadcasting event to active connections (empty pool handles gracefully)
    test_event = {
        "is_fault": True,
        "fault_class": "SPIKE",
        "anomaly_score": 0.85,
        "confidence": 0.92,
        "imputed_value": 31.4,
    }
    await ws_manager.broadcast_phase3_event("AWS-001", test_event)
    assert True
