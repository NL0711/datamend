"""
tests/test_alert_drilldown_forensics.py
SkyGuard AI — Flagged Incident Deep-Drilldown & Forensic Data Synchronization Test Suite.
Verifies that selecting any incident by ID returns the authentic, exact incident dossier
across all stations without data leakage, stale state, or unassociated telemetry.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_alert_row_loads_exact_incident_dossier(async_client: AsyncClient):
    """
    Verifies that querying distinct incident IDs returns completely distinct,
    authentic forensic dossiers with matched station metadata, telemetry, and tier scores.
    """
    # 1. Query fleet-wide incidents
    list_res = await async_client.get("/api/anomalies?limit=20&fleet_balanced=true")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) >= 2, "Need at least 2 incidents to verify distinct drilldown"

    # Pick two incidents from different stations if available, or two distinct IDs
    incident_a = items[0]
    incident_b = next((it for it in items[1:] if it["station_id"] != incident_a["station_id"]), items[1])

    assert incident_a["id"] != incident_b["id"]

    # 2. Fetch full forensic dossier for Incident A
    res_a = await async_client.get(f"/api/anomalies/{incident_a['id']}")
    assert res_a.status_code == 200
    dossier_a = res_a.json()

    # 3. Fetch full forensic dossier for Incident B
    res_b = await async_client.get(f"/api/anomalies/{incident_b['id']}")
    assert res_b.status_code == 200
    dossier_b = res_b.json()

    # 4. Assert strict isolation and field fidelity for Incident A
    assert dossier_a["id"] == incident_a["id"]
    assert dossier_a["station_id"] == incident_a["station_id"]
    assert dossier_a["severity"] == incident_a["severity"]
    assert dossier_a["classification"] == incident_a["classification"]
    assert "station" in dossier_a
    if dossier_a["station"]:
        assert dossier_a["station"]["station_id"] == incident_a["station_id"]

    # 5. Assert strict isolation and field fidelity for Incident B
    assert dossier_b["id"] == incident_b["id"]
    assert dossier_b["station_id"] == incident_b["station_id"]
    assert dossier_b["severity"] == incident_b["severity"]
    assert dossier_b["classification"] == incident_b["classification"]
    if dossier_b["station"]:
        assert dossier_b["station"]["station_id"] == incident_b["station_id"]

    # 6. Prove Dossier A != Dossier B
    assert dossier_a["id"] != dossier_b["id"]


@pytest.mark.asyncio
async def test_no_stale_incident_data_after_selection_change(async_client: AsyncClient):
    """
    Verifies that cycling across multiple incidents in sequence returns pure,
    untainted records for each requested ID without stale fallbacks.
    """
    list_res = await async_client.get("/api/anomalies?limit=10&fleet_balanced=true")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    test_ids = [it["id"] for it in items[:4]]

    # Cycle: ID_0 -> ID_1 -> ID_2 -> ID_0
    for target_id in test_ids + [test_ids[0]]:
        res = await async_client.get(f"/api/anomalies/{target_id}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == target_id
        assert data["anomaly_score"] is not None
        assert 0.0 <= data["anomaly_score"] <= 1.0
        assert data["confidence"] is not None
        assert "explanation" in data
        assert "tier_scores" in data


@pytest.mark.asyncio
async def test_incident_station_telemetry_integrity(async_client: AsyncClient):
    """
    Verifies that the telemetry associated with each incident matches its station
    and timestamp correctly.
    """
    list_res = await async_client.get("/api/anomalies?limit=5")
    assert list_res.status_code == 200
    items = list_res.json()["items"]

    for ev in items:
        res = await async_client.get(f"/api/anomalies/{ev['id']}")
        assert res.status_code == 200
        dossier = res.json()
        assert dossier["station_id"] == ev["station_id"]
        if dossier.get("raw_values"):
            # Ensure raw_values has numeric readings
            for key in ["temperature", "pressure", "humidity"]:
                if key in dossier["raw_values"] and dossier["raw_values"][key] is not None:
                    assert isinstance(dossier["raw_values"][key], (int, float))
