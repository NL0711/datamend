"""
tests/test_city_presets.py
SkyGuard AI — Unit & Integration Test Suite for Multi-City Open-Meteo Presets.
"""

import pytest
from httpx import AsyncClient

from backend.app.schemas.canonical import DataSourceType, ExternalSourceConfigRequest
from backend.app.sources.external_source import ExternalWeatherDataSource
from backend.app.sources.manager import data_source_manager


@pytest.mark.asyncio
async def test_external_weather_set_location():
    """Verifies that ExternalWeatherDataSource.set_location dynamically updates coordinates."""
    ext = ExternalWeatherDataSource(latitude=18.5204, longitude=73.8567, station_name="Pune")
    assert ext.latitude == 18.5204
    assert ext.longitude == 73.8567

    # Reconfigure to Tokyo
    ext.set_location(latitude=35.6762, longitude=139.6503, station_id="TOKYO-EXT-001", station_name="Tokyo")
    assert ext.latitude == 35.6762
    assert ext.longitude == 139.6503
    assert ext.station_id == "TOKYO-EXT-001"
    assert "Tokyo" in ext.name


@pytest.mark.asyncio
async def test_data_source_manager_configure_external():
    """Verifies that DataSourceManager reconfigures Open-Meteo coordinates."""
    data_source_manager.initialize()
    status = await data_source_manager.configure_external_source(
        latitude=51.5074,
        longitude=-0.1278,
        station_id="LONDON-EXT-001",
        station_name="London",
    )
    assert status.source_type == DataSourceType.EXTERNAL_API
    assert status.station_id == "LONDON-EXT-001"
    assert status.coordinates is not None
    assert status.coordinates["latitude"] == 51.5074
    assert status.coordinates["longitude"] == -0.1278


@pytest.mark.asyncio
async def test_external_configure_endpoint(async_client: AsyncClient):
    """Verifies POST /api/data-sources/external/configure REST endpoint."""
    payload = {
        "latitude": 36.5323,
        "longitude": -116.9325,
        "station_id": "DV-EXT-001",
        "station_name": "Death Valley",
    }
    res = await async_client.post("/api/data-sources/external/configure", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["source_type"] == "EXTERNAL_API"
    assert data["station_id"] == "DV-EXT-001"
    assert data["coordinates"]["latitude"] == 36.5323
    assert data["coordinates"]["longitude"] == -116.9325


@pytest.mark.asyncio
async def test_external_configure_validation_error(async_client: AsyncClient):
    """Verifies invalid latitude/longitude triggers HTTP 422."""
    payload = {
        "latitude": 150.0,  # Invalid (>90)
        "longitude": 0.0,
    }
    res = await async_client.post("/api/data-sources/external/configure", json=payload)
    assert res.status_code == 422
