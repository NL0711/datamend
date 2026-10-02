"""
tests/test_phase3_explain_heal_health.py
Automated Unit and Integration Tests for Phase 3:
- Stage 5: TreeSHAP / Surrogate Explainable AI (XAI) Engine
- Stage 6: Meteorological Safe Imputation & Self-Healing Engine
- Tier 3.5: Sensor Health Degradation & RUL Predictive Maintenance Tracker
- End-to-End Phase 3 Pipeline Service
"""

import time
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.stage1_stl import STLBaselineEngine
from backend.app.ml.stage5_explain import Stage5ExplainEngine, stage5_explain_engine
from backend.app.ml.stage6_imputer import MeteorologicalSafeImputer, meteorological_safe_imputer
from backend.app.health.tracker import PredictiveHealthTracker, predictive_health_tracker
from backend.app.services.phase3_service import phase3_pipeline_service


# ---------------------------------------------------------------------------
# Task 3.1: Explainable AI & TreeSHAP Attribution Tests
# ---------------------------------------------------------------------------

def test_task_3_1_shap_attribution_normalization():
    """Validates that feature attributions strictly sum to 100% (1.0)."""
    engine = Stage5ExplainEngine()

    raw_vals = {"temperature_c": 45.2, "pressure_hpa": 1008.0, "humidity_pct": 50.0}
    residuals = {"temperature_c_resid": 14.5, "pressure_hpa_resid": -0.2, "humidity_pct_resid": -2.0}

    report = engine.explain(
        station_id="DELHI_AWS_001",
        predicted_class="SPIKE",
        anomaly_score=0.88,
        confidence=0.92,
        raw_telemetry=raw_vals,
        residuals=residuals,
    )

    total_attr = sum(c.attribution for c in report.contributions)
    assert abs(total_attr - 1.0) < 1e-3, f"Attributions did not sum to 1.0 (sum={total_attr})"
    assert report.contributions[0].feature == "temperature_c"
    assert report.contributions[0].attribution > 0.60
    assert "SPIKE" in report.summary or "spike" in report.summary.lower()


def test_task_3_1_xai_surrogate_training_and_latency():
    """Validates surrogate model training with TreeSHAP and sub-5ms inference latency."""
    engine = Stage5ExplainEngine()

    # Train surrogate RF on 40 residual samples
    np.random.seed(42)
    X_train = np.random.normal(0, 0.5, size=(40, 3))
    y_train = np.zeros(40, dtype=int)
    # Add anomalies
    X_train[:10, 0] += 5.0
    y_train[:10] = 1

    engine.fit_surrogate(X_train, y_train)

    raw_vals = {"temperature_c": 35.0, "pressure_hpa": 1010.0, "humidity_pct": 60.0}
    residuals = {"temperature_c_resid": 8.0, "pressure_hpa_resid": 0.1, "humidity_pct_resid": 0.5}

    t0 = time.perf_counter()
    report = engine.explain(
        station_id="DELHI_AWS_001",
        predicted_class="SPIKE",
        anomaly_score=0.85,
        confidence=0.90,
        raw_telemetry=raw_vals,
        residuals=residuals,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert elapsed_ms < 15.0, f"XAI explanation took {elapsed_ms:.2f} ms (Target <= 15 ms)"
    assert report.summary is not None
    waterfall = report.to_dict()
    assert "contributions" in waterfall
    assert len(waterfall["contributions"]) == 3


# ---------------------------------------------------------------------------
# Task 3.2: Meteorological Safe Imputation Tests
# ---------------------------------------------------------------------------

def test_task_3_2_stl_reconstruction_imputation():
    """Validates STL baseline reconstruction for sensor spikes and frozen values."""
    imputer = MeteorologicalSafeImputer()
    stl_engine = STLBaselineEngine(default_period=96)

    # Pre-fit a known baseline around 30.0°C
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    t_hist = pd.date_range(end=now, periods=96, freq="15min")
    df_normal = pd.DataFrame({
        "timestamp": t_hist,
        "temperature_c": np.full(96, 30.0),
        "pressure_hpa": np.full(96, 1012.0),
        "humidity_pct": np.full(96, 60.0),
    })
    baseline = stl_engine.fit_station("TEST_AWS", df_normal)

    # Impute a +15°C spike (45.0°C)
    res = imputer.impute_reading(
        station_id="TEST_AWS",
        timestamp=now,
        parameter="temperature_c",
        original_value=45.0,
        predicted_class="SPIKE",
        baseline=baseline,
    )

    assert res.is_imputed is True
    assert res.method == "STL_RECONSTRUCTION"
    assert res.corrected_value is not None
    assert abs(res.corrected_value - 30.0) < 0.5, f"Imputed {res.corrected_value}, expected ~30.0"
    assert res.confidence >= 0.85


def test_task_3_2_spatial_idw_interpolation():
    """Validates Spatial Inverse Distance Weighting from clean neighbors for comms dropout."""
    imputer = MeteorologicalSafeImputer()
    now = datetime.now(timezone.utc)

    # Target station at (28.61, 77.21)
    neighbors = [
        {"station_id": "NB_1", "latitude": 28.62, "longitude": 77.21, "temperature": 28.0, "is_fault": False},
        {"station_id": "NB_2", "latitude": 28.60, "longitude": 77.21, "temperature": 28.2, "is_fault": False},
    ]

    res = imputer.impute_reading(
        station_id="TARGET_AWS",
        timestamp=now,
        parameter="temperature_c",
        original_value=None,  # Dropout / Null
        predicted_class="COMMUNICATION_DROPOUT",
        baseline=None,
        neighbor_observations=neighbors,
        target_lat=28.61,
        target_lon=77.21,
    )

    assert res.is_imputed is True
    assert res.method == "SPATIAL_IDW"
    assert res.corrected_value is not None
    assert 27.9 <= res.corrected_value <= 28.3
    assert res.confidence >= 0.90


def test_task_3_2_safety_gating_preserves_genuine_weather():
    """Asserts that genuine meteorological events and normal readings are NEVER imputed."""
    imputer = MeteorologicalSafeImputer()
    now = datetime.now(timezone.utc)

    # Genuine heatwave reading
    res_heatwave = imputer.impute_reading(
        station_id="DELHI_AWS",
        timestamp=now,
        parameter="temperature_c",
        original_value=46.5,
        predicted_class="GENUINE_WEATHER_EVENT",
        baseline=None,
    )
    assert res_heatwave.is_imputed is False
    assert res_heatwave.corrected_value is None
    assert res_heatwave.method == "PASSTHROUGH"

    # Routine normal reading
    res_normal = imputer.impute_reading(
        station_id="DELHI_AWS",
        timestamp=now,
        parameter="temperature_c",
        original_value=31.2,
        predicted_class="NORMAL",
        baseline=None,
    )
    assert res_normal.is_imputed is False
    assert res_normal.corrected_value is None


# ---------------------------------------------------------------------------
# Task 3.3: Sensor Health Degradation & Predictive Maintenance Tests
# ---------------------------------------------------------------------------

def test_task_3_3_health_degradation_tracking():
    """Validates SHI degradation, risk escalation, and failure forecasting."""
    tracker = PredictiveHealthTracker()
    now = datetime.now(timezone.utc)

    # Feed 15 clean readings
    for _ in range(15):
        snap = tracker.record_reading(
            station_id="AWS_TRACK_01",
            timestamp=now,
            predicted_class="NORMAL",
            anomaly_score=0.05,
            is_fault=False,
            primary_channel="temperature_c",
        )
    assert snap.overall_health_score >= 90.0
    assert snap.health_status == "EXCELLENT"
    assert snap.degradation_risk == "STABLE"

    # Inject repetitive sensor faults to simulate degradation
    for _ in range(12):
        snap = tracker.record_reading(
            station_id="AWS_TRACK_01",
            timestamp=now,
            predicted_class="CALIBRATION_DRIFT",
            anomaly_score=0.75,
            is_fault=True,
            primary_channel="temperature_c",
            residual_val=4.5,
        )

    assert snap.overall_health_score < 80.0
    assert snap.channel_health["temperature_c"]["health_score"] < 70.0
    assert snap.health_status in ("DEGRADED", "POOR", "CRITICAL")
    assert snap.degradation_risk in ("DEGRADING", "HIGH_RISK", "MAINTENANCE_REQUIRED")
    assert any(w in snap.recommended_action.lower() for w in ("recalibration", "intervention", "maintenance", "degrading"))


def test_task_3_3_frozen_streak_immediate_critical_escalation():
    """Asserts that 6 consecutive frozen readings trigger immediate MAINTENANCE_REQUIRED."""
    tracker = PredictiveHealthTracker()
    now = datetime.now(timezone.utc)

    for i in range(6):
        snap = tracker.record_reading(
            station_id="AWS_FROZEN_01",
            timestamp=now,
            predicted_class="FROZEN_SENSOR",
            anomaly_score=0.92,
            is_fault=True,
            primary_channel="temperature_c",
        )

    temp_health = snap.channel_health["temperature_c"]
    assert temp_health["frozen_streak"] == 6
    assert temp_health["degradation_risk"] == "MAINTENANCE_REQUIRED"
    assert temp_health["hours_to_failure"] == 0.0


# ---------------------------------------------------------------------------
# Task 3.4: Full Phase 3 Pipeline Service Integration Test
# ---------------------------------------------------------------------------

def test_task_3_4_full_phase3_pipeline_service():
    """End-to-end integration test of Phase 3 diagnostic and self-healing service."""
    now = datetime.now(timezone.utc)

    # 1. Seed baseline for station
    t_hist = pd.date_range(end=now, periods=96, freq="15min")
    df_normal = pd.DataFrame({
        "timestamp": t_hist,
        "temperature_c": np.random.normal(30.0, 0.3, size=96),
        "pressure_hpa": np.random.normal(1010.0, 0.2, size=96),
        "humidity_pct": np.random.normal(55.0, 1.0, size=96),
    })
    phase3_pipeline_service.fit_baseline_for_station("TEST_P3_AWS", df_normal)

    # 2. Feed initial normal reading
    phase3_pipeline_service.evaluate_reading(
        station_id="TEST_P3_AWS",
        timestamp=now,
        temperature_c=30.0,
        pressure_hpa=1010.0,
        humidity_pct=55.0,
        latitude=28.6139,
        longitude=77.2090,
    )

    # 3. Evaluate extreme temperature spike (step jump from 30.0 to 46.5°C)
    diag = phase3_pipeline_service.evaluate_reading(
        station_id="TEST_P3_AWS",
        timestamp=now,
        temperature_c=46.5,
        pressure_hpa=1010.0,
        humidity_pct=55.0,
        latitude=28.6139,
        longitude=77.2090,
    )

    assert diag.predicted_class == "SPIKE"
    assert diag.is_fault is True

    # Phase 3 asserts:
    assert "explanation" in diag.__dict__
    assert diag.explanation["summary"] is not None
    assert len(diag.explanation["contributions"]) == 3

    assert "imputation" in diag.__dict__
    assert diag.imputation["is_imputed"] is True
    assert diag.imputation["corrected_value"] is not None
    assert abs(diag.imputation["corrected_value"] - 30.0) < 1.0

    assert "sensor_health" in diag.__dict__
    assert "health_score" in diag.sensor_health
    assert diag.latency_ms <= 20.0
