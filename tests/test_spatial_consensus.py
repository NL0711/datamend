"""
tests/test_spatial_consensus.py
SkyGuard AI — Test Suite for Tier 3.5 Spatial Consensus / AWS Buddy-Check Layer.
"""

import pytest

from backend.app.spatial.consensus import (
    SpatialConsensusEngine,
    SpatialConsensusResult,
    compute_robust_z,
    haversine_distance_km,
)


def test_haversine_distance_calculation():
    """Verifies Haversine great-circle distance calculation."""
    # Distance between Pune (18.5204, 73.8567) and Mumbai (19.0760, 72.8777) ~ 120 km
    dist = haversine_distance_km(18.5204, 73.8567, 19.0760, 72.8777)
    assert 110.0 <= dist <= 130.0

    # Distance between identical points is 0.0
    dist_zero = haversine_distance_km(28.6139, 77.2090, 28.6139, 77.2090)
    assert pytest.approx(dist_zero, abs=1e-5) == 0.0


def test_spatial_consensus_supported_regional_event():
    """Verifies that coherent regional readings across neighbor stations are marked SUPPORTED."""
    engine = SpatialConsensusEngine(default_radius_km=50.0, min_neighbors=2)

    # Target station in central Pune
    target_lat = 18.5204
    target_lon = 73.8567
    target_telemetry = {"temperature": 25.5, "pressure": 1010.0, "humidity": 65.0}

    # Neighbor stations in suburban Pune (~10-25 km away)
    neighbors = [
        {"station_id": "PUNE-EAST", "latitude": 18.5500, "longitude": 73.9500, "temperature": 25.2, "pressure": 1010.2, "humidity": 64.0},
        {"station_id": "PUNE-WEST", "latitude": 18.5000, "longitude": 73.7800, "temperature": 25.8, "pressure": 1009.8, "humidity": 66.0},
        {"station_id": "PUNE-SOUTH", "latitude": 18.4400, "longitude": 73.8600, "temperature": 25.4, "pressure": 1010.0, "humidity": 65.5},
    ]

    res = engine.evaluate_consensus(
        target_station_id="PUNE-CENTRAL",
        target_lat=target_lat,
        target_lon=target_lon,
        target_telemetry=target_telemetry,
        neighbor_observations=neighbors,
    )

    assert isinstance(res, SpatialConsensusResult)
    assert res.status == "SUPPORTED"
    assert res.neighbor_count == 3
    assert res.regional_event_supported is True
    assert res.consensus_score >= 0.80


def test_spatial_consensus_isolated_sensor_fault():
    """Verifies that an extreme isolated spike diverging from neighbor stations is marked ISOLATED."""
    engine = SpatialConsensusEngine(default_radius_km=50.0, min_neighbors=2)

    # Target station has broken sensor reading 55°C
    target_lat = 18.5204
    target_lon = 73.8567
    target_telemetry = {"temperature": 55.0, "pressure": 1010.0, "humidity": 65.0}

    # Neighbor stations report normal ~25°C
    neighbors = [
        {"station_id": "PUNE-EAST", "latitude": 18.5500, "longitude": 73.9500, "temperature": 25.2, "pressure": 1010.2, "humidity": 64.0},
        {"station_id": "PUNE-WEST", "latitude": 18.5000, "longitude": 73.7800, "temperature": 25.8, "pressure": 1009.8, "humidity": 66.0},
        {"station_id": "PUNE-SOUTH", "latitude": 18.4400, "longitude": 73.8600, "temperature": 25.4, "pressure": 1010.0, "humidity": 65.5},
    ]

    res = engine.evaluate_consensus(
        target_station_id="PUNE-CENTRAL",
        target_lat=target_lat,
        target_lon=target_lon,
        target_telemetry=target_telemetry,
        neighbor_observations=neighbors,
    )

    assert res.status == "ISOLATED"
    assert res.regional_event_supported is False
    assert res.temperature_deviation is not None
    assert res.temperature_deviation >= 25.0


def test_spatial_consensus_insufficient_neighbors():
    """Verifies INSUFFICIENT_DATA status when fewer than min_neighbors are within radius."""
    engine = SpatialConsensusEngine(default_radius_km=50.0, min_neighbors=2)

    # London station with only Tokyo in neighbor list (>9000 km away)
    res = engine.evaluate_consensus(
        target_station_id="LON-01",
        target_lat=51.5074,
        target_lon=-0.1278,
        target_telemetry={"temperature": 18.0, "pressure": 1013.0, "humidity": 70.0},
        neighbor_observations=[
            {"station_id": "TYO-01", "latitude": 35.6762, "longitude": 139.6503, "temperature": 28.0, "pressure": 1008.0, "humidity": 80.0},
        ],
    )

    assert res.status == "INSUFFICIENT_DATA"
    assert res.neighbor_count == 0
