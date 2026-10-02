import pytest
from backend.app.config import settings

@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["project"] == settings.PROJECT_NAME

@pytest.mark.asyncio
async def test_health_check_endpoint(async_client):
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "total_stations" in data
    assert "active_stations" in data

def test_settings_load():
    assert settings.PROJECT_NAME == "SkyGuard AI"
    assert settings.INFERENCE_WINDOW_SIZE == 30
    assert settings.HEALTH_ROLLING_WINDOW == 288
    assert settings.HEALTH_EMA_ALPHA == 0.10
    assert settings.ANOMALY_THRESHOLD == 0.50
