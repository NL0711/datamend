"""
tests/test_event_station_integrity.py
SkyGuard AI — Multi-Station Incident Data Integrity and Routing Test Suite.
Verifies that telemetry, anomaly events, and REST APIs preserve true station identity
across all registered AWS nodes without station starvation or hardcoded fallbacks.
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_event_station_integrity_multi_station_persistence(async_client: AsyncClient):
    """
    Verifies that injecting anomalies across distinct stations generates and persists
    anomaly events with exact station_id integrity.
    """
    stations_to_test = [
        ("AWS-001", 75.0, 1013.25, 45.0),  # Exceeds physical max 60°C
        ("AWS-002", 25.0, 1200.0, 50.0),   # Exceeds physical max 1080 hPa
        ("AWS-004", -75.0, 1010.0, 10.0),  # Below physical min -60°C
    ]

    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Ingest anomalous telemetry for each distinct station
    for st_id, temp, press, hum in stations_to_test:
        payload = {
            "station_id": st_id,
            "timestamp": now_iso,
            "temperature": temp,
            "pressure": press,
            "humidity": hum,
            "source_type": "SIMULATED",
        }
        res = await async_client.post("/api/observations", json=payload)
        assert res.status_code == 201, f"Failed ingestion for {st_id}: {res.text}"
        data = res.json()
        assert data["observation"]["station_id"] == st_id
        assert data["inference"]["is_anomaly"] is True
        assert data["inference"]["station_id"] == st_id

    # 2. Query fleet-wide anomalies (no station filter, fleet_balanced=True)
    fleet_res = await async_client.get("/api/anomalies?limit=50&fleet_balanced=true")
    assert fleet_res.status_code == 200
    fleet_data = fleet_res.json()
    assert "items" in fleet_data
    assert len(fleet_data["items"]) > 0

    returned_stations = set(e["station_id"] for e in fleet_data["items"])
    # Verify that multiple stations are present in fleet-wide results
    assert len(returned_stations) >= 2, f"Fleet query returned only {returned_stations}, expected multi-station diversity"

    # 3. Test station-specific filtering for each station
    for st_id, _, _, _ in stations_to_test:
        st_res = await async_client.get(f"/api/anomalies?station_id={st_id}&limit=20")
        assert st_res.status_code == 200
        st_data = st_res.json()
        assert "items" in st_data
        assert len(st_data["items"]) > 0, f"No anomalies returned for station {st_id}"
        # Assert 100% of items belong to the requested station
        for item in st_data["items"]:
            assert item["station_id"] == st_id, f"Expected station {st_id}, got {item['station_id']}"


@pytest.mark.asyncio
async def test_anomaly_detail_by_id_preserves_station(async_client: AsyncClient):
    """
    Verifies that fetching anomaly details by ID returns the authentic station metadata.
    """
    # Fetch latest events
    res = await async_client.get("/api/anomalies?limit=10&fleet_balanced=true")
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) > 0

    for ev in items[:3]:
        detail_res = await async_client.get(f"/api/anomalies/{ev['id']}")
        assert detail_res.status_code == 200
        detail = detail_res.json()
        assert detail["id"] == ev["id"]
        assert detail["station_id"] == ev["station_id"]
        assert detail["classification"] == ev["classification"]
        assert "tier_scores" in detail
        assert "explanation" in detail
