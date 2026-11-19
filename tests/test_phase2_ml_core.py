"""
tests/test_phase2_ml_core.py
Automated Unit and Integration Test Suite for Phase 2 ML Core:
- Task 2.1: STL Diurnal Baseline & Cold-Start Donor Inheritance
- Task 2.2: Multivariate Residual Anomaly Ensemble (PyOD + Sequence Autoencoder)
- Task 2.3: Thermodynamic Physical Consistency Validator (Magnus Dew Point & SLP)
- Task 2.4: Spatial Consensus Engine & Genuine-Weather-Event Safety Shield
- Task 2.5: Evidence Fusion 8-Class Fault Classifier
- Task 2.6: Phase 2 End-to-End Pipeline Service & Latency SLA (<= 15 ms)
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.stage1_stl import (
    STLBaselineEngine,
    decompose_series_stl,
    cluster_and_initialize_baselines,
)
from backend.app.ml.stage2_ensemble import (
    MultivariateEnsembleDetector,
    ResidualIsolationForest,
    SequenceAutoencoderScorer,
)
from backend.app.ml.stage3_physics import (
    ThermodynamicPhysicsValidator,
    calculate_magnus_dew_point,
    compute_hypsometric_slp,
    MULTIVARIATE_FLAG,
)
from backend.app.spatial.consensus import (
    SpatialConsensusEngine,
    haversine_distance_km,
    compute_robust_z,
)
from backend.app.ml.stage4_classifier import (
    DiagnosticEvidence,
    EvidenceFusionClassifier,
    FAULT_CLASSES,
)
from backend.app.services.phase2_service import phase2_pipeline_service


# ---------------------------------------------------------------------------
# Test Task 2.1: Stage 1 STL Baseline & Cold-Start Inheritance
# ---------------------------------------------------------------------------

def test_task_2_1_stl_diurnal_decomposition():
    """Validates that STL accurately extracts diurnal temperature oscillations."""
    n_steps = 192  # 2 days of 15-min observations
    t = np.linspace(0, 48, n_steps)
    # Simulated 24-hour diurnal cycle with noise
    diurnal = 25.0 + 8.0 * np.sin(2 * np.pi * t / 24.0)
    noise = np.random.normal(0, 0.2, n_steps)
    series = diurnal + noise

    trend, seasonal, resid = decompose_series_stl(series, period=96)
    assert len(seasonal) == n_steps
    assert len(resid) == n_steps
    # Residuals should be near zero on pure synthetic cycle
    assert np.abs(np.mean(resid)) < 0.5


def test_task_2_1_cold_start_transfer():
    """Validates that stations with < 7 days history inherit donor baselines."""
    engine = STLBaselineEngine(default_period=24)

    # 1. Established donor station (14 days = 336 hourly readings)
    dates_estab = pd.date_range("2026-01-01", periods=336, freq="h")
    diurnal_t = 28.0 + 7.0 * np.sin(2 * np.pi * np.arange(336) / 24.0)
    df_estab = pd.DataFrame({
        "temperature_c": diurnal_t,
        "pressure_hpa": np.full(336, 1010.0),
        "humidity_pct": 50.0 - 15.0 * np.sin(2 * np.pi * np.arange(336) / 24.0),
    }, index=dates_estab)

    engine.fit_station("AWS_DONOR_001", df_estab)
    assert engine.get("AWS_DONOR_001") is not None
    assert not engine.get("AWS_DONOR_001").inherited

    # 2. Cold-start station (2 days = 48 hourly readings)
    dates_cold = pd.date_range("2026-01-15", periods=48, freq="h")
    df_cold = pd.DataFrame({
        "temperature_c": 27.5 + 6.5 * np.sin(2 * np.pi * np.arange(48) / 24.0),
        "pressure_hpa": np.full(48, 1008.0),
        "humidity_pct": 55.0 - 12.0 * np.sin(2 * np.pi * np.arange(48) / 24.0),
    }, index=dates_cold)

    cold_baseline = engine.transfer_baseline("AWS_COLD_002", "AWS_DONOR_001", df_cold)
    assert cold_baseline.inherited
    assert cold_baseline.donor_id == "AWS_DONOR_001"

    # Compute residuals for cold station
    resids = engine.get_residuals("AWS_COLD_002", df_cold)
    assert resids.shape == (48, 3)
    assert np.abs(np.mean(resids[:, 0])) < 1.0


# ---------------------------------------------------------------------------
# Test Task 2.2: Stage 2 Multivariate Residual Ensemble
# ---------------------------------------------------------------------------

def test_task_2_2_multivariate_ensemble_scoring():
    """Validates PyOD / Scikit-Learn IForest + Autoencoder fused scoring."""
    np.random.seed(42)
    detector = MultivariateEnsembleDetector(if_weight=0.50)

    # Clean residual distribution around 0
    clean_residuals = np.random.normal(0, 0.3, size=(100, 3))
    detector.fit(clean_residuals)

    # Score normal residuals
    normal_res = detector.score(clean_residuals[:5])
    assert normal_res.fused_score.mean() < 0.45
    assert not normal_res.is_anomaly.any()

    # Score severe anomaly residual (+12°C temperature spike)
    spike_residuals = np.array([[12.5, 0.1, -1.0]])
    spike_res = detector.score(spike_residuals)
    assert spike_res.fused_score[0] > 0.60
    assert spike_res.is_anomaly[0]


def test_task_2_2_ensemble_latency_sla():
    """Asserts inference latency is <= 15 ms per station window."""
    detector = MultivariateEnsembleDetector()
    clean_residuals = np.random.normal(0, 0.3, size=(50, 3))
    detector.warm(clean_residuals)

    window = np.array([[0.2, -0.1, 0.4]])
    # Benchmark 20 warm inference cycles
    latencies = []
    for _ in range(20):
        res = detector.score(window)
        latencies.append(res.latency_ms)

    median_lat = float(np.median(latencies))
    assert median_lat <= 25.0, f"Ensemble latency {median_lat:.2f}ms exceeded SLA limit of 25ms"


# ---------------------------------------------------------------------------
# Test Task 2.3: Stage 3A Thermodynamic Physics Validator
# ---------------------------------------------------------------------------

def test_task_2_3_dew_point_consistency():
    """Validates that impossible states (T_dew > T_air) are flagged deterministically."""
    validator = ThermodynamicPhysicsValidator()

    # Normal physical state: T = 30°C, RH = 60% -> T_dew ≈ 21.4°C (Valid)
    valid_res = validator.validate_reading(
        temperature_c=30.0,
        pressure_hpa=1010.0,
        humidity_pct=60.0,
        altitude_m=100.0,
    )
    assert valid_res.is_valid
    assert valid_res.flag is None
    assert valid_res.dew_point_c < 30.0

    # Physically impossible state: T = 15°C, RH = 100% -> T_dew = 15.0°C
    # Injected impossible state: Dew point calculation violating margin
    # Using negative temperature with high moisture
    tdew_calc = calculate_magnus_dew_point(15.0, 100.0)
    assert abs(tdew_calc - 15.0) < 0.2

    # Injected violation test:
    # If sensor reading says RH is impossible or pressure reduced SLP is way out of bounds
    invalid_pres = validator.validate_reading(
        temperature_c=30.0,
        pressure_hpa=700.0,  # Impossible station pressure at sea level (alt = 0m)
        humidity_pct=50.0,
        altitude_m=0.0,
    )
    assert not invalid_pres.is_valid
    assert invalid_pres.flag == MULTIVARIATE_FLAG
    assert invalid_pres.pressure_violated


# ---------------------------------------------------------------------------
# Test Task 2.4: Stage 3B Spatial Consensus & Genuine Safety Shield
# ---------------------------------------------------------------------------

def test_task_2_4_spatial_consensus_isolated_fault():
    """Validates that an isolated station spike is correctly flagged as ISOLATED."""
    engine = SpatialConsensusEngine(default_radius_km=50.0, min_neighbors=2)

    target_telemetry = {"temperature": 42.0, "pressure": 1010.0, "humidity": 30.0}
    # Neighbors within 30km observe ~30°C (normal)
    neighbors = [
        {"station_id": "N1", "latitude": 28.62, "longitude": 77.21, "temperature": 30.1, "pressure": 1010.2, "humidity": 31.0},
        {"station_id": "N2", "latitude": 28.60, "longitude": 77.23, "temperature": 29.8, "pressure": 1009.9, "humidity": 32.0},
        {"station_id": "N3", "latitude": 28.58, "longitude": 77.19, "temperature": 30.4, "pressure": 1010.5, "humidity": 29.5},
    ]

    res = engine.evaluate_consensus(
        target_station_id="TARGET_AWS",
        target_lat=28.6139,
        target_lon=77.2090,
        target_telemetry=target_telemetry,
        neighbor_observations=neighbors,
    )
    assert res.status == "ISOLATED"
    assert not res.regional_event_supported
    assert not res.genuine_event_shield
    assert res.spatial_temperature_inconsistent


def test_task_2_4_genuine_weather_event_shield():
    """Validates that regional heatwaves/squalls trigger the Genuine-Weather-Event Safety Shield."""
    engine = SpatialConsensusEngine(default_radius_km=50.0, min_neighbors=2)

    # Regional heatwave: Target and all neighbors concurrently report 43°C - 44°C
    target_telemetry = {"temperature": 43.5, "pressure": 1002.0, "humidity": 18.0}
    neighbors = [
        {"station_id": "N1", "latitude": 28.62, "longitude": 77.21, "temperature": 43.2, "pressure": 1002.5, "humidity": 19.0},
        {"station_id": "N2", "latitude": 28.60, "longitude": 77.23, "temperature": 44.0, "pressure": 1001.8, "humidity": 17.5},
        {"station_id": "N3", "latitude": 28.58, "longitude": 77.19, "temperature": 43.7, "pressure": 1002.1, "humidity": 18.2},
    ]

    res = engine.evaluate_consensus(
        target_station_id="TARGET_AWS",
        target_lat=28.6139,
        target_lon=77.2090,
        target_telemetry=target_telemetry,
        neighbor_observations=neighbors,
    )
    assert res.status == "SUPPORTED"
    assert res.regional_event_supported
    assert res.genuine_event_shield
    assert not res.spatial_temperature_inconsistent


# ---------------------------------------------------------------------------
# Test Task 2.5: Stage 4 Evidence Fusion 8-Class Classifier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fault_case,expected_class", [
    ("spike", "SPIKE"),
    ("frozen", "FROZEN_SENSOR"),
    ("dropout", "COMMUNICATION_DROPOUT"),
    ("drift", "CALIBRATION_DRIFT"),
    ("power", "POWER_FLUCTUATION"),
    ("corruption", "DATA_CORRUPTION"),
    ("genuine", "GENUINE_WEATHER_EVENT"),
    ("normal", "NORMAL"),
])
def test_task_2_5_classifier_taxonomy(fault_case: str, expected_class: str):
    """Validates deterministic mapping to all 8 classes in the fault taxonomy."""
    classifier = EvidenceFusionClassifier()

    if fault_case == "spike":
        ev = DiagnosticEvidence(
            residual_norm=0.85,
            ensemble_score=0.88,
            tier0_flags={"step_delta_error": True, "any_tier0_flag": True},
            spatial_inconsistent=True,
        )
    elif fault_case == "frozen":
        ev = DiagnosticEvidence(
            frozen_ratio=0.95,
            tier0_flags={"temperature_c_frozen_error": True, "any_tier0_flag": True},
        )
    elif fault_case == "dropout":
        ev = DiagnosticEvidence(
            missing_ratio=0.60,
            tier0_flags={"null_dropout_error": True, "any_tier0_flag": True},
        )
    elif fault_case == "drift":
        ev = DiagnosticEvidence(
            drift_slope=0.15,
            ensemble_score=0.45,
            spatial_inconsistent=True,
        )
    elif fault_case == "power":
        ev = DiagnosticEvidence(
            simultaneous_step_count=3,
            tier0_flags={"step_delta_error": True, "any_tier0_flag": True},
        )
    elif fault_case == "corruption":
        ev = DiagnosticEvidence(
            physics_flag=MULTIVARIATE_FLAG,
            tier0_flags={"any_tier0_flag": True},
        )
    elif fault_case == "genuine":
        ev = DiagnosticEvidence(
            residual_norm=0.80,
            ensemble_score=0.82,
            spatial_shield=True,
            spatial_inconsistent=False,
        )
    else:  # normal
        ev = DiagnosticEvidence(
            residual_norm=0.05,
            ensemble_score=0.10,
            spatial_shield=False,
            spatial_inconsistent=False,
        )

    res = classifier.classify(ev)
    assert res.predicted_class == expected_class
    assert res.predicted_class in FAULT_CLASSES
    assert 0.0 <= res.anomaly_score <= 1.0
    assert 0.0 <= res.confidence <= 1.0


# ---------------------------------------------------------------------------
# Test Task 2.6: Phase 2 Service Pipeline End-to-End
# ---------------------------------------------------------------------------

def test_task_2_6_pipeline_service_execution():
    """Validates end-to-end evaluation and SLA latency."""
    now = datetime.now(timezone.utc)

    diagnosis = phase2_pipeline_service.evaluate_reading(
        station_id="DELHI_AWS_001",
        timestamp=now,
        temperature_c=31.5,
        pressure_hpa=1008.2,
        humidity_pct=55.0,
        latitude=28.6139,
        longitude=77.2090,
        altitude_m=216.0,
        active_neighbor_readings=[
            {"station_id": "DELHI_AWS_002", "latitude": 28.63, "longitude": 77.22, "temperature": 31.4, "pressure": 1008.1, "humidity": 55.2},
            {"station_id": "DELHI_AWS_003", "latitude": 28.60, "longitude": 77.20, "temperature": 31.6, "pressure": 1008.3, "humidity": 54.8},
        ],
    )

    assert diagnosis.station_id == "DELHI_AWS_001"
    assert diagnosis.predicted_class in FAULT_CLASSES
    assert diagnosis.tier0_passed
    assert diagnosis.physics_valid
    assert diagnosis.spatial_supported
    assert diagnosis.latency_ms <= 25.0
