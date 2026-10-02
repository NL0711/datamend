"""
tests/test_task4_parity.py
OpenSpec task4-parity-closeout, capability api-parity (tasks 1.1-1.4).

Proves spec-named aliases resolve identically to canonical contracts
while existing routes keep working.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from backend.app.schemas.schemas import (
    AnomalyEvent,
    AnomalyEventResponse,
    AWSReading,
    ObservationBase,
    SensorHealth,
    SensorHealthRecord,
)


@pytest.mark.asyncio
async def test_alerts_alias_matches_canonical(async_client: AsyncClient):
    """1.1: GET /api/alerts returns exactly what /anomalies/alerts/active returns."""
    params = {"min_severity": "MEDIUM", "limit": 5}
    canonical = await async_client.get("/api/anomalies/alerts/active", params=params)
    alias = await async_client.get("/api/alerts", params=params)
    assert canonical.status_code == 200
    assert alias.status_code == 200
    assert alias.json() == canonical.json()


@pytest.mark.asyncio
async def test_telemetry_live_ingests_and_persists(async_client: AsyncClient):
    """1.2: POST /api/telemetry/live persists through the standard ingest path."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "station_id": "AWS-PARITY-001",
        "temperature": 24.5,
        "pressure": 1012.5,
        "humidity": 58.0,
    }
    res = await async_client.post("/api/telemetry/live", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["persisted"] is True
    assert data["observation"]["station_id"] == "AWS-PARITY-001"

    listed = await async_client.get(
        "/api/observations", params={"station_id": "AWS-PARITY-001", "page": 1, "page_size": 5}
    )
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1


def _valid_reading_payload():
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "station_id": "AWS-001",
        "temperature": 25.4,
        "pressure": 1013.25,
        "humidity": 55.0,
    }


def test_reading_alias_validates_identically():
    """1.3a: AWSReading accepts/rejects exactly like ObservationBase."""
    valid = _valid_reading_payload()
    assert AWSReading(**valid).model_dump() == ObservationBase(**valid).model_dump()

    invalid = {**valid, "temperature": 500.0}
    for model in (AWSReading, ObservationBase):
        with pytest.raises(ValidationError):
            model(**invalid)


def test_event_and_health_aliases_mirror_canonical():
    """1.3b: AnomalyEvent/SensorHealth serialize exactly like canonical models."""
    now = datetime.now(timezone.utc)
    event = {
        "id": 1,
        "station_id": "AWS-001",
        "timestamp": now,
        "anomaly_score": 0.91,
        "confidence": 0.88,
        "severity": "HIGH",
        "classification": "SPIKE",
        "created_at": now,
    }
    assert AnomalyEvent(**event).model_dump() == AnomalyEventResponse(**event).model_dump()

    health = {
        "station_id": "AWS-001",
        "timestamp": now,
        "health_score": 92.5,
        "health_status": "EXCELLENT",
    }
    assert SensorHealth(**health).model_dump() == SensorHealthRecord(**health).model_dump()


@pytest.mark.asyncio
async def test_existing_routes_unchanged(async_client: AsyncClient):
    """Spec scenario: previously working routes return the same results."""
    stations = await async_client.get("/api/stations")
    assert stations.status_code == 200
    assert "items" in stations.json() and "total" in stations.json()

    health = await async_client.get("/api/health")
    assert health.status_code == 200

    anomalies = await async_client.get("/api/anomalies", params={"page_size": 5})
    assert anomalies.status_code == 200
