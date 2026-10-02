"""
tests/test_pipeline.py
Comprehensive End-to-End Master Pipeline Tests for SkyGuard AI 5-Tier ML Engine.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from backend.app.ml.pipeline import InferenceResult, SkyGuardPipeline


@pytest.fixture
def pipeline() -> SkyGuardPipeline:
    # Initialize pipeline with auto-load from models/ if present
    return SkyGuardPipeline(model_dir="models", auto_load=True)


def test_pipeline_initialization(pipeline: SkyGuardPipeline) -> None:
    assert pipeline.preprocessor is not None
    assert pipeline.tier1 is not None
    assert pipeline.tier2_point is not None
    assert pipeline.tier2_temporal is not None
    assert pipeline.tier3_multivariate is not None
    assert pipeline.fusion is not None
    assert pipeline.tier4_classifier is not None
    assert pipeline.tier5_health is not None
    assert pipeline.tier5_explain is not None


def test_pipeline_single_nominal_observation(pipeline: SkyGuardPipeline) -> None:
    obs = {
        "timestamp": "2026-08-24T12:00:00Z",
        "station_id": "AWS-001",
        "temperature": 22.5,
        "pressure": 1013.25,
        "humidity": 55.0,
    }
    res: InferenceResult = pipeline.process_observation(obs)

    assert isinstance(res, InferenceResult)
    assert res.station_id == "AWS-001"
    assert res.is_anomaly is False
    assert res.anomaly_score < 0.45
    assert 0.0 <= res.confidence <= 1.0  # Cold-start single step confidence
    assert res.severity in ["NONE", "LOW"]
    assert res.classification == "NORMAL"
    assert res.is_fault is False
    assert res.sensor_health >= 90.0
    assert res.sensor_status == "EXCELLENT"
    assert len(res.explanation.contributing_features) == 9
    assert len(res.reason) > 0


def test_pipeline_detects_transient_spike(pipeline: SkyGuardPipeline) -> None:
    pipeline.reset_station("AWS-001")
    # Feed 5 baseline steps
    for i in range(5):
        pipeline.process_observation({
            "timestamp": f"2026-08-24T12:{i*5:02d}:00Z",
            "station_id": "AWS-001",
            "temperature": 20.0,
            "pressure": 1013.0,
            "humidity": 50.0,
        })

    # Injected temperature spike (+25°C step)
    spike_obs = {
        "timestamp": "2026-08-24T12:30:00Z",
        "station_id": "AWS-001",
        "temperature": 45.0,
        "pressure": 1013.0,
        "humidity": 50.0,
    }
    res = pipeline.process_observation(spike_obs)

    assert res.is_anomaly is True
    assert res.anomaly_score >= 0.60
    assert res.classification in ["SPIKE", "DATA_CORRUPTION", "MULTIVARIATE_INCONSISTENCY"]
    assert res.is_fault is True
    assert res.severity in ["HIGH", "CRITICAL"]


def test_pipeline_detects_convective_squall_front(pipeline: SkyGuardPipeline) -> None:
    pipeline.reset_station("AWS-FRONT")
    # Feed baseline
    pipeline.process_observation({"station_id": "AWS-FRONT", "timestamp": "t1", "temperature": 28.0, "pressure": 1008.0, "humidity": 60.0})
    pipeline.process_observation({"station_id": "AWS-FRONT", "timestamp": "t2", "temperature": 26.0, "pressure": 1009.0, "humidity": 70.0})
    pipeline.process_observation({"station_id": "AWS-FRONT", "timestamp": "t3", "temperature": 24.0, "pressure": 1010.0, "humidity": 80.0})

    # Convective squall front arrival (dT = -6°C, dP = +3.5 hPa, dRH = +28%)
    front_obs = {
        "station_id": "AWS-FRONT",
        "timestamp": "t4",
        "temperature": 22.0,
        "pressure": 1011.5,
        "humidity": 88.0,
    }
    res = pipeline.process_observation(front_obs)

    assert res.classification == "METEOROLOGICAL_EXTREME"
    assert res.is_fault is False
    assert res.sensor_health >= 90.0


def test_pipeline_detects_tier1_range_violation(pipeline: SkyGuardPipeline) -> None:
    pipeline.reset_station("AWS-002")
    bad_obs = {
        "timestamp": "2026-08-24T12:00:00Z",
        "station_id": "AWS-002",
        "temperature": 85.0,  # Far above 60.0°C WMO limit
        "pressure": 1013.25,
        "humidity": 50.0,
    }
    res = pipeline.process_observation(bad_obs)

    assert res.is_anomaly is True
    assert res.anomaly_score == 1.0
    assert res.severity == "CRITICAL"
    assert res.tier_scores.tier1_hard == 1.0
    assert res.classification == "DATA_CORRUPTION"


def test_pipeline_detects_frozen_sensor(pipeline: SkyGuardPipeline) -> None:
    pipeline.reset_station("AWS-FREEZE")
    # Stream 8 consecutive identical observations
    res = None
    for i in range(8):
        res = pipeline.process_observation({
            "timestamp": f"2026-08-24T12:{i*5:02d}:00Z",
            "station_id": "AWS-FREEZE",
            "temperature": 23.45,
            "pressure": 1013.25,
            "humidity": 50.0,
        })

    assert res is not None
    assert res.is_anomaly is True
    assert res.classification == "FROZEN"
    assert res.is_fault is True


def test_pipeline_batch_processing(pipeline: SkyGuardPipeline) -> None:
    pipeline.reset_station("AWS-BATCH")
    df = pd.DataFrame({
        "timestamp": [f"2026-08-24 12:{i*5:02d}:00" for i in range(15)],
        "temperature": [20.0 + 0.1 * i for i in range(15)],
        "pressure": [1013.0] * 15,
        "humidity": [50.0] * 15,
    })

    results = pipeline.process_batch(df, station_id="AWS-BATCH")
    assert len(results) == 15
    for r in results:
        assert isinstance(r, InferenceResult)
        assert r.station_id == "AWS-BATCH"
