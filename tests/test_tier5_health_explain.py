"""
tests/test_tier5_health_explain.py
Comprehensive Unit Test Suite for Tier 5 Sensor Health Index & TreeSHAP Explainability.
"""

import numpy as np
import pytest

from backend.app.ml.tier5_explain import ExplainabilityEngine
from backend.app.ml.tier5_health import (
    DegradationRisk,
    HealthStatus,
    SensorHealthEngine,
)


def test_sensor_health_clean_baseline() -> None:
    engine = SensorHealthEngine(window_size=288, ema_alpha=0.10)
    for i in range(50):
        shi, status, action, risk, ttf = engine.update(
            station_id="AWS-001",
            timestamp=f"2026-08-24T12:{i:02d}:00Z",
            is_anomaly=False,
            is_frozen=False,
            is_missing=False,
            temperature=22.0,
            fused_score=0.05,
            fault_type="NORMAL",
        )
    assert shi >= 95.0
    assert status == HealthStatus.EXCELLENT
    assert risk == DegradationRisk.STABLE
    assert "nominal" in action.lower() or "no maintenance" in action.lower()


def test_sensor_health_decay_under_persistent_faults() -> None:
    engine = SensorHealthEngine(window_size=288, ema_alpha=0.10)
    # Inject 100 consecutive frozen faults
    for i in range(100):
        shi, status, action, risk, ttf = engine.update(
            station_id="AWS-001",
            timestamp=f"2026-08-24T12:{i:02d}:00Z",
            is_anomaly=True,
            is_frozen=True,
            is_missing=False,
            temperature=22.0,
            fused_score=1.0,
            fault_type="FROZEN",
        )
    assert shi < 75.0
    assert status in [HealthStatus.DEGRADED, HealthStatus.POOR, HealthStatus.CRITICAL]
    assert ("probe" in action.lower()) or ("frozen" in action.lower()) or ("mechanical" in action.lower())


def test_sensor_health_weather_front_preserves_score() -> None:
    """A genuine meteorological squall front should not degrade hardware health."""
    engine = SensorHealthEngine(window_size=288, ema_alpha=0.10)
    # Stream 30 baseline
    for i in range(30):
        engine.update(
            station_id="AWS-001",
            timestamp=f"2026-08-24T12:{i:02d}:00Z",
            is_anomaly=False,
            is_frozen=False,
            is_missing=False,
            temperature=22.0,
            fused_score=0.05,
            fault_type="NORMAL",
        )
    # Ingest 5 convective front steps (is_anomaly=True, but fault_type=METEOROLOGICAL_EXTREME)
    for i in range(5):
        shi, status, action, risk, ttf = engine.update(
            station_id="AWS-001",
            timestamp=f"2026-08-24T13:{i:02d}:00Z",
            is_anomaly=True,
            is_frozen=False,
            is_missing=False,
            temperature=16.0,
            fused_score=0.80,
            fault_type="METEOROLOGICAL_EXTREME",
        )
    # Health remains in EXCELLENT tier
    assert shi >= 90.0
    assert status == HealthStatus.EXCELLENT


def test_sensor_health_ema_smoothing() -> None:
    engine = SensorHealthEngine(window_size=288, ema_alpha=0.10, baseline_temp_mean=22.0)
    # 20 clean steps at baseline
    for i in range(20):
        engine.update("AWS-001", f"t_{i}", False, False, False, 22.0, 0.05, "NORMAL")

    shi_before = engine.stations["AWS-001"].current_shi

    # Single severe transient spike
    shi_after, _, _, _, _ = engine.update(
        "AWS-001", "t_spike", True, False, False, 45.0, 0.95, "SPIKE"
    )

    # SHI drops smoothly due to EMA alpha=0.10 (not dropping straight to 0)
    assert shi_after < shi_before
    assert shi_after >= (shi_before - 15.0)


def test_treeshap_feature_attribution_sum() -> None:
    engine = ExplainabilityEngine()
    vec = np.array([2.5, -1.0, 1.2, 3.5, 0.1, -0.5, 1.0, 0.2, 0.8])
    raw_vals = {"temperature": 35.0, "temp_delta": 8.0, "pressure": 1013.0, "humidity": 50.0}

    res = engine.explain(
        feature_vector=vec,
        raw_values=raw_vals,
        tier1_flags={"out_of_bounds": False},
        tier3_info={"thermo_violation": False},
        classification="SPIKE",
        fused_score=0.88,
        confidence=0.91,
    )
    total_attr = sum(f.attribution for f in res.contributing_features)
    assert pytest.approx(total_attr, abs=1e-2) == 1.0
    assert len(res.summary) > 10


def test_treeshap_identifies_top_anomalous_feature() -> None:
    engine = ExplainabilityEngine()
    # Large deviation in temp_delta (feature index 3)
    vec = np.array([0.1, 0.1, 0.1, 8.5, 0.1, 0.1, 0.1, 0.1, 0.1])
    raw_vals = {"temperature": 32.0, "temp_delta": 12.0}

    res = engine.explain(
        feature_vector=vec,
        raw_values=raw_vals,
        tier1_flags={"rate_of_change_exceeded": True, "violating_param": "temperature"},
        tier3_info={"thermo_violation": False},
        classification="SPIKE",
        fused_score=0.90,
        confidence=0.95,
    )
    top_feature = res.contributing_features[0]
    assert top_feature.feature in ["temp_delta", "delta_temp", "temperature"]
    assert "rapid" in res.summary.lower() or "jump" in res.summary.lower() or "spike" in res.summary.lower()
