"""
tests/test_task4_triage.py
OpenSpec task4-parity-closeout, capability triage-ui (task 3.3).

Proves the UI payload contract end to end: ingest a spiking observation,
resolve its anomaly event id, then send the exact JSON shape TriageActions
sends -> POST /api/feedback -> persisted audit row with operator ID,
event ID, verification status, and timestamp.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

STATION = "AWS-TRIAGE-001"


def _payload(event_id: str, status: str) -> dict:
    return {
        "event_id": event_id,
        "operator_id": "IMD_ANALYST_TASK4",
        "verification_status": status,
        "imputation_accepted": status == "IMPUTATION_APPROVED",
        "notes": "task4-parity-closeout round-trip",
    }


async def _spike_event_id(async_client: AsyncClient) -> str:
    """Ingest a spike and return its anomaly event id as string."""
    await async_client.post("/api/telemetry/live", json={
        "timestamp": "2026-09-01T10:00:00Z",
        "station_id": STATION,
        "temperature": 24.0,
        "pressure": 1012.0,
        "humidity": 60.0,
    })
    spike = await async_client.post("/api/telemetry/live", json={
        "timestamp": "2026-09-01T10:05:00Z",
        "station_id": STATION,
        "temperature": 55.0,
        "pressure": 1012.0,
        "humidity": 60.0,
    })
    assert spike.status_code == 201

    listed = await async_client.get(
        "/api/anomalies", params={"station_id": STATION, "page_size": 10}
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert items, "spike ingest produced no anomaly event"
    return str(items[0]["id"])


@pytest.mark.asyncio
async def test_triage_confirm_fault_round_trip(async_client: AsyncClient):
    """3.3: Confirm Fault payload persists a full audit row."""
    event_id = await _spike_event_id(async_client)
    res = await async_client.post(
        "/api/feedback", json=_payload(event_id, "CONFIRMED_FAULT")
    )
    assert res.status_code == 200
    data = res.json()
    assert data["event_id"] == event_id
    assert data["operator_id"] == "IMD_ANALYST_TASK4"
    assert data["verification_status"] == "CONFIRMED_FAULT"
    assert isinstance(data["id"], int)
    # Timestamp present and parseable.
    datetime.fromisoformat(data["created_at"])


@pytest.mark.asyncio
async def test_triage_all_statuses_persist_distinct_rows(async_client: AsyncClient):
    """3.3: each triage action stores its own audit row."""
    event_id = await _spike_event_id(async_client)
    ids = set()
    for status in ("CONFIRMED_FAULT", "FALSE_POSITIVE", "IMPUTATION_APPROVED"):
        res = await async_client.post("/api/feedback", json=_payload(event_id, status))
        assert res.status_code == 200
        data = res.json()
        assert data["event_id"] == event_id
        assert data["verification_status"] == status
        assert data["operator_id"] == "IMD_ANALYST_TASK4"
        ids.add(data["id"])
    assert len(ids) == 3, "each triage action must persist its own row"


@pytest.mark.asyncio
async def test_triage_invalid_status_rejected(async_client: AsyncClient):
    """Invalid verification statuses are still rejected with 400."""
    res = await async_client.post("/api/feedback", json=_payload("1", "NOT_A_STATUS"))
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_triage_unknown_event_rejected(async_client: AsyncClient):
    """Feedback for a nonexistent event fails loudly with 404, never silently."""
    res = await async_client.post(
        "/api/feedback", json=_payload("999999999", "CONFIRMED_FAULT")
    )
    assert res.status_code == 404
