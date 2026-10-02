"""
SkyGuard AI — Empirical Stress Harness for Multi-Duration Benchmark Scenarios.

Verifies that MultiStationNetworkScenario, SingleFaultScenario, WeatherFrontScenario,
HealthDegradationScenario, CleanBaselineScenario, and MultiFaultStressScenario execute
flawlessly with zero crashes across 1d, 2d, 3d, 7d, and 30d durations.
"""

import pytest
import pandas as pd
from backend.simulator.scenarios import (
    MultiStationNetworkScenario,
    SingleFaultScenario,
    WeatherFrontScenario,
    HealthDegradationScenario,
    CleanBaselineScenario,
    MultiFaultStressScenario,
)

DURATIONS = [1.0, 2.0, 3.0, 7.0, 30.0]
SINGLE_FAULTS = ["spike", "drift", "frozen", "dropout", "noise", "noise_burst", "multivariate"]


@pytest.mark.parametrize("duration", DURATIONS)
def test_multi_station_network_durations(duration: float):
    sc = MultiStationNetworkScenario(duration_days=duration)
    df = sc.generate(seed=42)
    meta = sc.get_metadata()
    expected_rows_per_station = int(round(duration * 288))
    expected_total_rows = expected_rows_per_station * 4

    assert len(df) == expected_total_rows
    assert df["station_id"].nunique() == 4
    assert set(df["station_id"].unique()) == {"AWS-DEL-01", "AWS-MUM-02", "AWS-LEH-03", "AWS-JAI-04"}
    assert df["is_anomaly"].sum() == meta.expected_anomaly_count
    assert df["is_anomaly"].sum() > 0


@pytest.mark.parametrize("fault_type", SINGLE_FAULTS)
@pytest.mark.parametrize("duration", DURATIONS)
def test_single_fault_all_types_durations(fault_type: str, duration: float):
    sc = SingleFaultScenario(fault_type=fault_type, duration_days=duration)
    df = sc.generate(seed=42)
    meta = sc.get_metadata()
    expected_rows = int(round(duration * 288))

    assert len(df) == expected_rows
    assert df["is_anomaly"].sum() == meta.expected_anomaly_count
    assert df["is_anomaly"].sum() > 0
    assert df["is_fault"].sum() == df["is_anomaly"].sum()


@pytest.mark.parametrize("duration", DURATIONS)
def test_weather_front_durations(duration: float):
    sc = WeatherFrontScenario(duration_days=duration)
    df = sc.generate(seed=42)
    meta = sc.get_metadata()
    expected_rows = int(round(duration * 288))

    assert len(df) == expected_rows
    assert df["is_anomaly"].sum() == meta.expected_anomaly_count
    
    extremes = (df["anomaly_type"] == "METEOROLOGICAL_EXTREME").sum()
    spikes = (df["anomaly_type"] == "SPIKE").sum()
    assert extremes > 0
    assert spikes > 0
    assert df["is_fault"].sum() == spikes


@pytest.mark.parametrize("duration", DURATIONS)
def test_health_degradation_durations(duration: float):
    sc = HealthDegradationScenario(duration_days=duration)
    df = sc.generate(seed=42)
    meta = sc.get_metadata()
    expected_rows = int(round(duration * 288))

    assert len(df) == expected_rows
    assert df["is_anomaly"].sum() == meta.expected_anomaly_count
    assert df["is_anomaly"].sum() > 0

    # Ensure all 3 degradation fault types are present
    types = set(df[df["is_anomaly"]]["anomaly_type"].unique())
    assert "DRIFT" in types
    assert "SPIKE" in types
    assert "FROZEN" in types


@pytest.mark.parametrize("duration", DURATIONS)
def test_clean_baseline_durations(duration: float):
    sc = CleanBaselineScenario(duration_days=duration)
    df = sc.generate(seed=42)
    meta = sc.get_metadata()
    expected_rows = int(round(duration * 288))

    assert len(df) == expected_rows
    assert df["is_anomaly"].sum() == 0
    assert meta.expected_anomaly_count == 0


@pytest.mark.parametrize("duration", DURATIONS)
def test_multi_fault_stress_durations(duration: float):
    sc = MultiFaultStressScenario(duration_days=duration)
    df = sc.generate(seed=42)
    meta = sc.get_metadata()
    expected_rows = int(round(duration * 288))

    assert len(df) == expected_rows
    assert df["is_anomaly"].sum() > 0
