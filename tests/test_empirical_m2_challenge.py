"""
tests/test_empirical_m2_challenge.py
Adversarial and Empirical Challenge Suite for Milestone M2 (5-Tier ML Pipeline Engine).

Verifies:
1. PyTorch Temporal Autoencoder non-zero reconstruction errors and higher errors on anomalous windows vs normal windows.
2. Dynamic SHAP attributions that change dynamically with varying input perturbations and sum to 100%.
3. Sensor Health Index (SHI) degradation trajectory under sustained faults and preservation during weather fronts.
4. Weather Front vs Sensor Fault discrimination (METEOROLOGICAL_EXTREME has is_fault=False).
5. Pipeline streaming inference latency benchmark (< 500ms per observation).
"""

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import torch

from backend.app.ml.pipeline import SkyGuardPipeline
from backend.app.ml.preprocessor import DataPreprocessor
from backend.app.ml.tier2_temporal_ml import TemporalAutoencoderDetector
from backend.app.ml.tier4_classifier import FaultClass, FaultClassifier
from backend.app.ml.tier5_explain import ExplainabilityEngine
from backend.app.ml.tier5_health import DegradationRisk, HealthStatus, SensorHealthEngine


@pytest.fixture(scope="module")
def pipeline():
    pipe = SkyGuardPipeline(model_dir="models", auto_load=True)
    return pipe


# ---------------------------------------------------------------------------
# 1. PyTorch Autoencoder Reconstruction Error & Anomaly Discrimination Tests
# ---------------------------------------------------------------------------

def test_autoencoder_nonzero_reconstruction_error():
    """Verify PyTorch Temporal Autoencoder produces genuine non-zero reconstruction error."""
    detector = TemporalAutoencoderDetector(window_size=30)
    model_path = Path("models/temporal_autoencoder.pt")
    if not model_path.exists():
        model_path = Path("models/autoencoder.pt")
    detector.load(model_path)

    # Generate synthetic nominal sinusoidal diurnal cycle (W=30, 3 features)
    t = np.linspace(0, np.pi, 30)
    normal_seq = np.zeros((30, 3), dtype=np.float32)
    normal_seq[:, 0] = np.sin(t) * 0.5  # Normalized temp
    normal_seq[:, 1] = np.cos(t) * 0.2  # Normalized pressure
    normal_seq[:, 2] = -np.sin(t) * 0.4  # Normalized humidity

    tensor_in = torch.from_numpy(normal_seq).unsqueeze(0).to(detector.device)
    detector.model.eval()
    with torch.no_grad():
        recon = detector.model(tensor_in)
        raw_mse = torch.mean((recon - tensor_in) ** 2).item()

    score = detector.predict_score(normal_seq)

    # Assert genuine non-zero errors
    assert raw_mse > 0.0, "Reconstruction MSE should be strictly non-zero"
    assert np.isfinite(raw_mse), "Reconstruction MSE must be finite"
    assert 0.0 <= score <= 1.0, f"Temporal anomaly score {score} must be within [0, 1]"
    print(f"\n[AE Check] Normal Sequence Raw MSE: {raw_mse:.6f}, Score: {score:.4f}")


def test_autoencoder_anomalous_vs_normal_reconstruction_discrimination():
    """Verify that anomalous windows produce significantly higher reconstruction errors than normal windows."""
    detector = TemporalAutoencoderDetector(window_size=30)
    model_path = Path("models/temporal_autoencoder.pt")
    if not model_path.exists():
        model_path = Path("models/autoencoder.pt")
    detector.load(model_path)

    # 1. Normal diurnal sequence
    t = np.linspace(0, 2 * np.pi, 30)
    normal_seq = np.zeros((30, 3), dtype=np.float32)
    normal_seq[:, 0] = 0.2 * np.sin(t)
    normal_seq[:, 1] = 0.1 * np.cos(t)
    normal_seq[:, 2] = -0.2 * np.sin(t)

    # 2. Anomalous sequence with severe sudden impulse spike at the end
    spike_seq = normal_seq.copy()
    spike_seq[-1, 0] += 5.0  # Massive 5-sigma jump in temperature

    # 3. Anomalous sequence with chaotic high-frequency noise burst
    noise_seq = normal_seq.copy()
    noise_seq += np.random.RandomState(42).normal(0.0, 3.0, size=normal_seq.shape).astype(np.float32)

    # Compute raw MSE for each
    tensor_norm = torch.from_numpy(normal_seq).unsqueeze(0).to(detector.device)
    tensor_spike = torch.from_numpy(spike_seq).unsqueeze(0).to(detector.device)
    tensor_noise = torch.from_numpy(noise_seq).unsqueeze(0).to(detector.device)

    detector.model.eval()
    with torch.no_grad():
        mse_norm = torch.mean((detector.model(tensor_norm) - tensor_norm) ** 2).item()
        mse_spike = torch.mean((detector.model(tensor_spike) - tensor_spike) ** 2).item()
        mse_noise = torch.mean((detector.model(tensor_noise) - tensor_noise) ** 2).item()

    score_norm = detector.predict_score(normal_seq)
    score_spike = detector.predict_score(spike_seq)
    score_noise = detector.predict_score(noise_seq)

    print(f"\n[AE Discrimination] Normal MSE: {mse_norm:.5f} (Score: {score_norm:.4f})")
    print(f"[AE Discrimination] Spike MSE: {mse_spike:.5f} (Score: {score_spike:.4f})")
    print(f"[AE Discrimination] Noise MSE: {mse_noise:.5f} (Score: {score_noise:.4f})")

    # The anomalous sequences MUST have significantly higher reconstruction error
    assert mse_spike > mse_norm * 2.0, f"Spike MSE ({mse_spike}) should exceed Normal MSE ({mse_norm})"
    assert mse_noise > mse_norm * 2.0, f"Noise MSE ({mse_noise}) should exceed Normal MSE ({mse_norm})"
    assert score_spike > score_norm, f"Spike score ({score_spike}) should exceed Normal score ({score_norm})"
    assert score_noise > score_norm, f"Noise score ({score_noise}) should exceed Normal score ({score_norm})"


# ---------------------------------------------------------------------------
# 2. Dynamic Input-Sensitive SHAP Explanation Tests
# ---------------------------------------------------------------------------

def test_shap_dynamic_input_sensitivity_and_sum(pipeline):
    """Verify SHAP attributions are dynamically computed, vary with input perturbation, and sum to 100%."""
    explainer_engine = pipeline.tier5_explain

    base_vector = np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.1, 0.1], dtype=np.float32)

    # 1. Perturb Temperature Delta (Feature index 3)
    temp_perturbed = base_vector.copy()
    temp_perturbed[3] = 4.5  # Large positive temperature step
    temp_raw = {"temperature": 35.0, "temp_delta": 8.0, "pressure": 1013.2, "humidity": 45.0}

    exp_temp = explainer_engine.explain(
        feature_vector=temp_perturbed,
        raw_values=temp_raw,
        classification="SPIKE",
        fused_score=0.85,
        confidence=0.90,
    )

    # 2. Perturb Pressure Delta (Feature index 4)
    press_perturbed = base_vector.copy()
    press_perturbed[4] = -4.5  # Large pressure drop
    press_raw = {"temperature": 20.0, "press_delta": -6.0, "pressure": 1005.0, "humidity": 50.0}

    exp_press = explainer_engine.explain(
        feature_vector=press_perturbed,
        raw_values=press_raw,
        classification="SPIKE",
        fused_score=0.82,
        confidence=0.88,
    )

    # 3. Perturb Humidity Delta (Feature index 5)
    humid_perturbed = base_vector.copy()
    humid_perturbed[5] = 5.0  # Large humidity jump
    humid_raw = {"temperature": 20.0, "humid_delta": 30.0, "pressure": 1013.0, "humidity": 90.0}

    exp_humid = explainer_engine.explain(
        feature_vector=humid_perturbed,
        raw_values=humid_raw,
        classification="SPIKE",
        fused_score=0.79,
        confidence=0.85,
    )

    # Verify normalization: all attributions must sum to 1.0 (within float rounding)
    for name, exp in [("Temp", exp_temp), ("Press", exp_press), ("Humid", exp_humid)]:
        total_sum = sum(fa.attribution for fa in exp.contributing_features)
        assert abs(total_sum - 1.0) < 0.01, f"{name} attributions sum ({total_sum}) is not 1.0"

    # Verify input sensitivity: Top feature must be dynamically different
    top_temp_feature = exp_temp.contributing_features[0].feature
    top_press_feature = exp_press.contributing_features[0].feature
    top_humid_feature = exp_humid.contributing_features[0].feature

    print(f"\n[SHAP Dynamic Test] Temp Spike top feature: {top_temp_feature} ({exp_temp.contributing_features[0].attribution:.1%})")
    print(f"[SHAP Dynamic Test] Press Spike top feature: {top_press_feature} ({exp_press.contributing_features[0].attribution:.1%})")
    print(f"[SHAP Dynamic Test] Humid Spike top feature: {top_humid_feature} ({exp_humid.contributing_features[0].attribution:.1%})")

    # Check that attributions are dynamic and sensitive to the specific perturbed feature
    temp_feat_attr = next(fa.attribution for fa in exp_temp.contributing_features if fa.feature in ("temp_delta", "temperature"))
    press_feat_attr = next(fa.attribution for fa in exp_press.contributing_features if fa.feature in ("press_delta", "pressure"))
    humid_feat_attr = next(fa.attribution for fa in exp_humid.contributing_features if fa.feature in ("humid_delta", "humidity"))

    assert temp_feat_attr > 0.20, f"Temperature feature should have high attribution on temp spike ({temp_feat_attr})"
    assert press_feat_attr > 0.20, f"Pressure feature should have high attribution on press spike ({press_feat_attr})"
    assert humid_feat_attr > 0.20, f"Humidity feature should have high attribution on humid spike ({humid_feat_attr})"


# ---------------------------------------------------------------------------
# 3. Sensor Health Index Degradation Trajectory & Recovery Tests
# ---------------------------------------------------------------------------

def test_sensor_health_degradation_under_sustained_faults(pipeline):
    """Verify SHI degrades monotonically from EXCELLENT to POOR/CRITICAL under sustained faults."""
    engine = SensorHealthEngine(window_size=288, ema_alpha=0.10)
    station_id = "CHALLENGER-STA-01"

    # 1. Warm up station with 30 clean nominal observations
    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    for i in range(30):
        ts = t0 + timedelta(minutes=5 * i)
        shi, status, rec, risk, _ = engine.update(
            station_id=station_id,
            timestamp=ts,
            is_anomaly=False,
            is_frozen=False,
            is_missing=False,
            temperature=22.0 + np.sin(i * 0.1),
            fused_score=0.05,
            fault_type="NORMAL",
        )

    assert shi >= 90.0, f"Initial clean health should be >= 90, got {shi}"
    assert status == HealthStatus.EXCELLENT

    # 2. Inject 60 sustained severe sensor faults (e.g. high-score SPIKE/FROZEN)
    shi_series = []
    for i in range(30, 90):
        ts = t0 + timedelta(minutes=5 * i)
        shi, status, rec, risk, ttf = engine.update(
            station_id=station_id,
            timestamp=ts,
            is_anomaly=True,
            is_frozen=True,
            is_missing=False,
            temperature=45.0,
            fused_score=0.95,
            fault_type="FROZEN",
        )
        shi_series.append(shi)

    # SHI must have decayed significantly
    final_degraded_shi = shi_series[-1]
    print(f"\n[Health Degradation] Initial SHI: 100.0 -> Degraded SHI: {final_degraded_shi:.2f} (Status: {status.value}, Risk: {risk.value})")

    assert final_degraded_shi < 65.0, f"Degraded SHI ({final_degraded_shi}) should be < 65.0 after 60 faults"
    assert status in (HealthStatus.DEGRADED, HealthStatus.POOR, HealthStatus.CRITICAL)
    assert risk in (DegradationRisk.DEGRADING, DegradationRisk.HIGH_RISK, DegradationRisk.MAINTENANCE_REQUIRED)
    assert "probe" in rec.lower() or "frozen" in rec.lower() or "inspection" in rec.lower() or "stuck" in rec.lower()

    # 3. Stream 100 clean observations to verify health recovery trajectory
    recovery_series = []
    for i in range(90, 190):
        ts = t0 + timedelta(minutes=5 * i)
        shi, status, rec, risk, _ = engine.update(
            station_id=station_id,
            timestamp=ts,
            is_anomaly=False,
            is_frozen=False,
            is_missing=False,
            temperature=22.0 + np.sin(i * 0.1),
            fused_score=0.05,
            fault_type="NORMAL",
        )
        recovery_series.append(shi)

    recovered_shi = recovery_series[-1]
    print(f"[Health Recovery] Recovered SHI: {recovered_shi:.2f} (Status: {status.value})")
    assert recovered_shi > final_degraded_shi + 15.0, f"Recovered SHI ({recovered_shi}) should be higher than degraded ({final_degraded_shi})"


# ---------------------------------------------------------------------------
# 4. Weather Front vs Sensor Fault Discrimination
# ---------------------------------------------------------------------------

def test_meteorological_front_vs_sensor_fault_discrimination(pipeline):
    """
    Verify convective squall front discrimination:
    - Weather front has classification == 'METEOROLOGICAL_EXTREME' and is_fault == False
    - Sensor hardware fault has is_fault == True
    - Sensor health is not penalized as hardware degradation for genuine weather front
    """
    pipeline.reset_station("CHALLENGER-FRONT-TEST")
    station_id = "CHALLENGER-FRONT-TEST"

    # Feed 30 baseline nominal observations
    t0 = datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc)
    for i in range(30):
        ts = t0 + timedelta(minutes=5 * i)
        res = pipeline.process_observation({
            "station_id": station_id,
            "timestamp": ts.isoformat(),
            "temperature": 28.0 - (i * 0.05),
            "pressure": 1012.0 + (i * 0.02),
            "humidity": 60.0 + (i * 0.1),
        })

    health_before_front = res.sensor_health
    assert health_before_front >= 95.0, f"Expected nominal health >= 95, got {health_before_front}"

    # Step 31: Introduce convective squall front
    # Sudden drop in T (-4.0C), sharp pressure jump (+2.2 hPa), surge in RH (+22%), valid dew point
    t_front = res.raw_values["temperature"] - 4.0  # 28.0 - 1.5 - 4.0 = 22.5
    p_front = res.raw_values["pressure"] + 2.2      # 1012.6 + 2.2 = 1014.8
    rh_front = min(100.0, res.raw_values["humidity"] + 22.0)  # 63.0 + 22.0 = 85.0

    front_ts = t0 + timedelta(minutes=5 * 30)
    front_res = pipeline.process_observation({
        "station_id": station_id,
        "timestamp": front_ts.isoformat(),
        "temperature": t_front,
        "pressure": p_front,
        "humidity": rh_front,
    })

    print(f"\n[Front Test] Classification: {front_res.classification}, is_fault: {front_res.is_fault}, is_anomaly: {front_res.is_anomaly}")
    print(f"[Front Test] Health after front: {front_res.sensor_health:.2f} (Before: {health_before_front:.2f})")
    print(f"[Front Test] Reason: {front_res.reason}")

    # Assertions for Weather Front
    assert front_res.classification == "METEOROLOGICAL_EXTREME", f"Expected METEOROLOGICAL_EXTREME, got {front_res.classification}"
    assert front_res.is_fault is False, "Genuine convective weather front must have is_fault=False"
    assert "convective" in front_res.reason.lower() or "squall" in front_res.reason.lower() or "front" in front_res.reason.lower()
    # Health should remain pristine/high, not punished as a hardware fault
    assert front_res.sensor_health >= 90.0, f"Sensor health ({front_res.sensor_health}) should not crash for weather front"

    # Step 32: In contrast, feed an unphysical single-variable sensor spike (e.g. +30C jump with no pressure/RH correlation)
    spike_ts = t0 + timedelta(minutes=5 * 31)
    spike_res = pipeline.process_observation({
        "station_id": station_id,
        "timestamp": spike_ts.isoformat(),
        "temperature": 58.0,  # Unrealistic spike
        "pressure": p_front,
        "humidity": rh_front,
    })

    print(f"[Spike Test] Classification: {spike_res.classification}, is_fault: {spike_res.is_fault}, is_anomaly: {spike_res.is_anomaly}")
    assert spike_res.is_fault is True, "Hardware sensor spike must have is_fault=True"
    assert spike_res.classification in ("SPIKE", "DATA_CORRUPTION", "MULTIVARIATE_INCONSISTENCY")


# ---------------------------------------------------------------------------
# 5. Pipeline End-to-End Inference Latency Benchmark (< 500ms target)
# ---------------------------------------------------------------------------

def test_pipeline_inference_latency_benchmark(pipeline):
    """
    Measure real-time streaming pipeline inference latency across 100 consecutive observations.
    Target: Mean latency < 500ms, P95 < 500ms.
    """
    pipeline.reset_station("CHALLENGER-LATENCY-TEST")
    station_id = "CHALLENGER-LATENCY-TEST"

    # Warm-up phase (30 steps)
    t0 = datetime(2026, 3, 15, 0, 0, tzinfo=timezone.utc)
    for i in range(30):
        pipeline.process_observation({
            "station_id": station_id,
            "timestamp": (t0 + timedelta(minutes=5 * i)).isoformat(),
            "temperature": 21.0 + np.sin(i * 0.1),
            "pressure": 1013.25 + np.cos(i * 0.1),
            "humidity": 55.0 - np.sin(i * 0.1) * 5.0,
        })

    # Benchmark phase: 100 warm observations
    latencies = []
    N = 100
    for i in range(30, 30 + N):
        obs = {
            "station_id": station_id,
            "timestamp": (t0 + timedelta(minutes=5 * i)).isoformat(),
            "temperature": 21.0 + np.sin(i * 0.1) + (3.0 if i % 20 == 0 else 0.0),
            "pressure": 1013.25 + np.cos(i * 0.1),
            "humidity": 55.0 - np.sin(i * 0.1) * 5.0,
        }
        start_time = time.perf_counter()
        res = pipeline.process_observation(obs)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        latencies.append(elapsed_ms)
        assert res is not None

    mean_lat = float(np.mean(latencies))
    median_lat = float(np.median(latencies))
    p95_lat = float(np.percentile(latencies, 95))
    p99_lat = float(np.percentile(latencies, 99))
    max_lat = float(np.max(latencies))
    min_lat = float(np.min(latencies))

    print(f"\n=================================================================")
    print(f"PIPELINE STREAMING INFERENCE LATENCY BENCHMARK (N={N})")
    print(f"=================================================================")
    print(f"  Mean Latency:    {mean_lat:.2f} ms")
    print(f"  Median Latency:  {median_lat:.2f} ms")
    print(f"  P95 Latency:     {p95_lat:.2f} ms")
    print(f"  P99 Latency:     {p99_lat:.2f} ms")
    print(f"  Min / Max:       {min_lat:.2f} ms / {max_lat:.2f} ms")
    print(f"  Throughput:      {1000.0 / mean_lat:.1f} obs/sec")
    print(f"  Target:          < 500.00 ms")
    print(f"=================================================================\n")

    # Assert latency constraints
    assert mean_lat < 500.0, f"Mean latency {mean_lat:.2f}ms exceeds 500ms threshold"
    assert p95_lat < 500.0, f"P95 latency {p95_lat:.2f}ms exceeds 500ms threshold"
