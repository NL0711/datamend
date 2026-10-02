"""
tests/test_tier4_classifier.py
Comprehensive Unit Test Suite for Tier 4 Fault Taxonomy & Front vs Fault Classifier.
"""

import numpy as np
import pandas as pd
import pytest

from backend.app.ml.fusion import FusionResult, Severity
from backend.app.ml.tier1_qc import Tier1QCResult
from backend.app.ml.tier3_multivariate import Tier3Result
from backend.app.ml.tier4_classifier import FaultClass, FaultClassifier


@pytest.fixture
def classifier() -> FaultClassifier:
    return FaultClassifier()


def test_classifier_normal_telemetry(classifier: FaultClassifier) -> None:
    fusion = FusionResult(
        fused_score=0.10,
        confidence=0.95,
        severity=Severity.NONE.value,
        is_anomaly=False,
        tier_scores={},
        override_applied=False,
        contributing_tiers=[],
    )
    res = classifier.classify(
        current_observation={"temperature": 22.0, "pressure": 1013.0, "humidity": 55.0},
        fusion_result=fusion,
    )
    assert res.fault_class == FaultClass.NORMAL
    assert res.is_fault is False
    assert res.confidence >= 0.85


def test_classifier_dropout_nan_sentinel(classifier: FaultClassifier) -> None:
    fusion = FusionResult(
        fused_score=1.0,
        confidence=0.99,
        severity=Severity.CRITICAL.value,
        is_anomaly=True,
        tier_scores={},
        override_applied=True,
        contributing_tiers=["tier1_qc"],
    )
    t1_res = Tier1QCResult(is_valid=False, qc_flag=True, is_missing=True, is_hard_override=True)
    res = classifier.classify(
        current_observation={"temperature": np.nan, "pressure": 1013.0, "humidity": 55.0},
        tier1_result=t1_res,
        fusion_result=fusion,
    )
    assert res.fault_class == FaultClass.DROPOUT
    assert res.is_fault is True


def test_classifier_data_corruption_string_range(classifier: FaultClassifier) -> None:
    fusion = FusionResult(
        fused_score=1.0,
        confidence=0.99,
        severity=Severity.CRITICAL.value,
        is_anomaly=True,
        tier_scores={},
        override_applied=True,
        contributing_tiers=["tier1_qc"],
    )
    res = classifier.classify(
        current_observation={"temperature": 85.0, "pressure": 1013.0, "humidity": 55.0},
        fusion_result=fusion,
    )
    assert res.fault_class == FaultClass.DATA_CORRUPTION
    assert res.is_fault is True


def test_classifier_frozen_sensor_zero_variance(classifier: FaultClassifier) -> None:
    # 10 constant values
    df_frozen = pd.DataFrame({
        "temperature": [22.4] * 10,
        "pressure": [1013.0 + i * 0.1 for i in range(10)],
        "humidity": [50.0 + i * 0.5 for i in range(10)],
    })
    fusion = FusionResult(
        fused_score=0.90,
        confidence=0.92,
        severity=Severity.CRITICAL.value,
        is_anomaly=True,
        tier_scores={},
        override_applied=False,
        contributing_tiers=["tier1_qc"],
    )
    res = classifier.classify(
        current_observation={"temperature": 22.4, "pressure": 1014.0, "humidity": 55.0},
        buffer_df=df_frozen,
        fusion_result=fusion,
    )
    assert res.fault_class == FaultClass.FROZEN
    assert res.is_fault is True


def test_classifier_convective_squall_front_discrimination(classifier: FaultClassifier) -> None:
    """
    Validates genuine convective squall front discrimination:
    - Temperature drops > 3°C within 15 min (e.g. -6°C)
    - Pressure jumps > 1.5 hPa (e.g. +2.5 hPa)
    - Relative humidity surges > 15% (e.g. +25%)
    - Clausius-Clapeyron equilibrium holds (Td <= T)
    - Classifier MUST assign METEOROLOGICAL_EXTREME with is_fault = False!
    """
    buffer_data = pd.DataFrame({
        "temperature": [28.0, 26.0, 24.0, 22.0],
        "pressure": [1008.0, 1009.0, 1010.0, 1011.0],
        "humidity": [60.0, 70.0, 80.0, 88.0],
    })
    t3_result = Tier3Result(
        is_valid=True,
        dew_point=20.0,
        dew_point_diff=-2.0,
        thermo_violation=False,
        thermo_score=0.0,
        mahalanobis_distance=2.5,
        mahalanobis_sq=6.25,
        mahalanobis_score=0.90,
        tier3_score=0.90,
    )
    fusion = FusionResult(
        fused_score=0.75,
        confidence=0.88,
        severity=Severity.HIGH.value,
        is_anomaly=True,
        tier_scores={},
        override_applied=False,
        contributing_tiers=["tier2_temporal_ml"],
    )

    res = classifier.classify(
        current_observation={"temperature": 22.0, "pressure": 1011.0, "humidity": 88.0},
        buffer_df=buffer_data,
        tier3_result=t3_result,
        fusion_result=fusion,
    )
    assert res.fault_class == FaultClass.METEOROLOGICAL_EXTREME
    assert res.is_fault is False  # Genuine meteorological event, not a hardware fault!


def test_classifier_single_variable_spike(classifier: FaultClassifier) -> None:
    """Isolated impulse jump on a single sensor without front dynamics."""
    buffer_data = pd.DataFrame({
        "temperature": [20.0, 20.1, 20.2],
        "pressure": [1013.0, 1013.1, 1013.0],
        "humidity": [50.0, 50.1, 50.0],
    })
    fusion = FusionResult(
        fused_score=0.85,
        confidence=0.90,
        severity=Severity.CRITICAL.value,
        is_anomaly=True,
        tier_scores={},
        override_applied=False,
        contributing_tiers=["tier1_qc", "tier2_point_ml"],
    )

    res = classifier.classify(
        current_observation={
            "temperature": 38.0,  # Jump of +17.8°C
            "pressure": 1013.0,
            "humidity": 50.0,
            "temp_delta": 17.8,
            "press_delta": 0.0,
            "humid_delta": 0.0,
        },
        buffer_df=buffer_data,
        fusion_result=fusion,
    )
    assert res.fault_class == FaultClass.SPIKE
    assert res.is_fault is True


def test_classifier_thermodynamic_inconsistency(classifier: FaultClassifier) -> None:
    """Clausius-Clapeyron violation where calculated Td > T + 0.5."""
    t3_viol = Tier3Result(
        is_valid=True,
        dew_point=32.0,
        dew_point_diff=7.0,  # Td=32 > T=25 by 7°C
        thermo_violation=True,
        thermo_score=1.0,
        mahalanobis_distance=4.0,
        mahalanobis_sq=16.0,
        mahalanobis_score=0.99,
        tier3_score=1.0,
    )
    fusion = FusionResult(
        fused_score=0.80,
        confidence=0.92,
        severity=Severity.HIGH.value,
        is_anomaly=True,
        tier_scores={},
        override_applied=False,
        contributing_tiers=["tier3_multivariate"],
    )
    res = classifier.classify(
        current_observation={"temperature": 25.0, "pressure": 1013.0, "humidity": 104.0},
        tier3_result=t3_viol,
        fusion_result=fusion,
    )
    assert res.fault_class == FaultClass.MULTIVARIATE_INCONSISTENCY
    assert res.is_fault is True


def test_classifier_progressive_linear_drift(classifier: FaultClassifier) -> None:
    # 24 steps of continuous steady upward drift on temperature
    t_drift = [20.0 + i * 0.25 for i in range(24)]
    df_drift = pd.DataFrame({
        "temperature": t_drift,
        "pressure": [1013.0 + 0.05 * (i % 3) for i in range(24)],
        "humidity": [50.0 + 0.1 * (i % 5) for i in range(24)],
    })
    fusion = FusionResult(
        fused_score=0.60,
        confidence=0.85,
        severity=Severity.MEDIUM.value,
        is_anomaly=True,
        tier_scores={},
        override_applied=False,
        contributing_tiers=["tier2_temporal_ml"],
    )
    res = classifier.classify(
        current_observation={"temperature": t_drift[-1], "pressure": 1013.0, "humidity": 50.0},
        buffer_df=df_drift,
        fusion_result=fusion,
    )
    assert res.fault_class == FaultClass.DRIFT
    assert res.is_fault is True


def test_classifier_noise_burst(classifier: FaultClassifier) -> None:
    # High variance random noise on temperature
    np.random.seed(42)
    t_noisy = list(np.random.normal(20.0, 3.5, 12))  # Std ~ 3.5 >> nominal 0.35
    df_noise = pd.DataFrame({
        "temperature": t_noisy,
        "pressure": [1013.0 + 0.05 * (i % 3) for i in range(12)],
        "humidity": [50.0 + 0.1 * (i % 5) for i in range(12)],
    })
    fusion = FusionResult(
        fused_score=0.65,
        confidence=0.85,
        severity=Severity.HIGH.value,
        is_anomaly=True,
        tier_scores={},
        override_applied=False,
        contributing_tiers=["tier2_point_ml"],
    )
    res = classifier.classify(
        current_observation={"temperature": t_noisy[-1], "pressure": 1013.0, "humidity": 50.0},
        buffer_df=df_noise,
        fusion_result=fusion,
    )
    assert res.fault_class == FaultClass.NOISE_BURST
    assert res.is_fault is True
