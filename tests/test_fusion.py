"""
tests/test_fusion.py
Comprehensive Unit Test Suite for Multi-Tier Anomaly Fusion Engine.
"""

import pytest

from backend.app.ml.fusion import AnomalyFusionEngine, Severity, TierScores


@pytest.fixture
def fusion_engine() -> AnomalyFusionEngine:
    return AnomalyFusionEngine(
        weight_tier1=0.25,
        weight_tier2_point=0.20,
        weight_tier2_temporal=0.25,
        weight_tier3=0.30,
        anomaly_threshold=0.45,
        required_buffer_length=30,
    )


def test_fusion_tier1_hard_override(fusion_engine: AnomalyFusionEngine) -> None:
    scores = TierScores(
        tier1_hard_flag=True,
        tier1_soft_score=1.0,
        tier2_point_score=0.10,
        tier2_temporal_score=0.10,
        tier3_multivariate_score=0.10,
    )
    res = fusion_engine.fuse(scores, buffer_length=50)
    assert res.fused_score == 1.0
    assert res.is_anomaly is True
    assert res.severity == Severity.CRITICAL.value
    assert res.override_applied is True
    assert "tier1_qc" in res.contributing_tiers


def test_fusion_convex_weights_sum(fusion_engine: AnomalyFusionEngine) -> None:
    scores = TierScores(
        tier1_hard_flag=False,
        tier1_soft_score=0.40,
        tier2_point_score=0.60,
        tier2_temporal_score=0.80,
        tier3_multivariate_score=0.50,
    )
    # Expected: 0.25*0.4 + 0.20*0.6 + 0.25*0.8 + 0.30*0.5 = 0.10 + 0.12 + 0.20 + 0.15 = 0.57
    res = fusion_engine.fuse(scores, buffer_length=30)
    assert pytest.approx(res.fused_score, abs=1e-3) == 0.57
    assert res.is_anomaly is True
    assert res.severity == Severity.MEDIUM.value


def test_fusion_confidence_model_agreement(fusion_engine: AnomalyFusionEngine) -> None:
    # All ML and multivariate models agree that the observation is clean
    scores = TierScores(
        tier1_hard_flag=False,
        tier1_soft_score=0.05,
        tier2_point_score=0.05,
        tier2_temporal_score=0.05,
        tier3_multivariate_score=0.05,
    )
    res = fusion_engine.fuse(scores, buffer_length=30)
    assert res.is_anomaly is False
    assert res.confidence >= 0.85
    assert res.severity == Severity.NONE.value


def test_fusion_confidence_model_conflict(fusion_engine: AnomalyFusionEngine) -> None:
    # Strong conflict between point model (0.95) and others (0.05)
    scores = TierScores(
        tier1_hard_flag=False,
        tier1_soft_score=0.0,
        tier2_point_score=0.95,
        tier2_temporal_score=0.05,
        tier3_multivariate_score=0.05,
    )
    res = fusion_engine.fuse(scores, buffer_length=30)
    # Concordance is penalized due to high inter-model standard deviation
    assert res.confidence < 0.75


def test_fusion_confidence_cold_start_buffer_penalty(fusion_engine: AnomalyFusionEngine) -> None:
    scores = TierScores(
        tier1_hard_flag=False,
        tier1_soft_score=0.05,
        tier2_point_score=0.05,
        tier2_temporal_score=0.05,
        tier3_multivariate_score=0.05,
    )
    # Buffer has only 5 observations out of 30 required
    res_cold = fusion_engine.fuse(scores, buffer_length=5)
    res_warm = fusion_engine.fuse(scores, buffer_length=30)

    assert res_cold.confidence < res_warm.confidence
    assert pytest.approx(res_warm.confidence - res_cold.confidence, abs=0.05) == 0.166


@pytest.mark.parametrize(
    "fused_val, expected_sev",
    [
        (0.10, Severity.NONE.value),
        (0.30, Severity.LOW.value),
        (0.55, Severity.MEDIUM.value),
        (0.75, Severity.HIGH.value),
        (0.90, Severity.CRITICAL.value),
    ],
)
def test_fusion_severity_tier_thresholds(
    fusion_engine: AnomalyFusionEngine, fused_val: float, expected_sev: str
) -> None:
    sev = fusion_engine.map_severity(fused_val, override_applied=False)
    assert sev == expected_sev


def test_fusion_contributing_tiers_identification(fusion_engine: AnomalyFusionEngine) -> None:
    scores = TierScores(
        tier1_hard_flag=False,
        tier1_soft_score=0.20,  # Below threshold
        tier2_point_score=0.85,  # Active
        tier2_temporal_score=0.90,  # Active
        tier3_multivariate_score=0.10,  # Below threshold
    )
    res = fusion_engine.fuse(scores, buffer_length=30)
    assert "tier2_point_ml" in res.contributing_tiers
    assert "tier2_temporal_ml" in res.contributing_tiers
    assert "tier1_qc" not in res.contributing_tiers
    assert "tier3_multivariate" not in res.contributing_tiers


def test_fusion_clamping_bounds(fusion_engine: AnomalyFusionEngine) -> None:
    scores = TierScores(
        tier1_hard_flag=False,
        tier1_soft_score=1.5,
        tier2_point_score=2.0,
        tier2_temporal_score=1.8,
        tier3_multivariate_score=1.2,
    )
    res = fusion_engine.fuse(scores, buffer_length=30)
    assert res.fused_score <= 1.0
    assert 0.0 <= res.confidence <= 1.0
