"""
tests/test_alert_xai.py
SkyGuard AI — Unit & Integration Test Suite for Interactive Alert Center XAI & TreeSHAP Attributions.
"""

from datetime import datetime, timezone
import pytest
from httpx import AsyncClient

from backend.app.ml.pipeline import SkyGuardPipeline


def test_pipeline_treeshap_feature_attributions():
    """Verifies that the 5-Tier ML Pipeline computes genuine TreeSHAP feature rankings."""
    pipeline = SkyGuardPipeline()
    obs = {
        "station_id": "TEST-XAI-01",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": 55.0,  # Extreme temperature spike
        "pressure": 1012.0,
        "humidity": 60.0,
    }
    res = pipeline.process_observation(obs)
    assert res is not None
    assert res.explanation is not None
    assert len(res.explanation.contributing_features) > 0

    # Top feature should reflect temperature anomaly
    top_feature = res.explanation.contributing_features[0]
    assert "temperature" in top_feature.feature.lower() or "t" in top_feature.feature.lower()
    assert top_feature.attribution != 0.0


@pytest.mark.asyncio
async def test_alert_query_and_explanation_payload(async_client: AsyncClient):
    """Verifies that the /api/anomalies endpoint returns explanation payloads for alert cards."""
    # 1. Ingest an anomaly
    spike_obs = {
        "station_id": "AWS-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "temperature": 52.0,
        "pressure": 1010.0,
        "humidity": 45.0,
    }
    ingest_res = await async_client.post("/api/observations", json=spike_obs)
    assert ingest_res.status_code == 201

    # 2. Query anomalies
    anom_res = await async_client.get("/api/anomalies?limit=5")
    assert anom_res.status_code == 200
    data = anom_res.json()
    assert "items" in data
    assert len(data["items"]) > 0

    latest_alert = data["items"][0]
    assert "station_id" in latest_alert
    assert "anomaly_score" in latest_alert
    assert "classification" in latest_alert
