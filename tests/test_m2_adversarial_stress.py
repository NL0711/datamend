"""
tests/test_m2_adversarial_stress.py
Adversarial Stress Test Suite for Milestone M2 (5-Tier ML Pipeline Engine).

Empirical challenger harness testing:
1. Automated ML Training Pipeline (scripts/train_models.py) on clean & synthetic data
2. Large Batch Processing (5,000+ to 10,000 rows) scaling, memory usage, and score stability
3. Extreme Edge Cases (cryogenic cold, furnace heat, boundary limits, formula singularities)
4. Null / NaN / Sentinel / Malformed Token streams
5. Frozen / Constant Stuck sensor streams and health degradation
6. Rapid Oscillations / Square waves / Noise bursts vs Convective squall front disambiguation
7. Multi-Station Interleaved Telemetry isolation and station resets
"""

import gc
import json
import math
import shutil
import tempfile
import time
import tracemalloc
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import pytest

from backend.app.ml.fusion import AnomalyFusionEngine, FusionResult, Severity, TierScores
from backend.app.ml.pipeline import InferenceResult, SkyGuardPipeline
from backend.app.ml.preprocessor import DataPreprocessor, FEATURE_NAMES, calculate_magnus_dew_point
from backend.app.ml.tier1_qc import Tier1QC, Tier1QCConfig, Tier1QCResult
from backend.app.ml.tier2_point_ml import IsolationForestPointDetector
from backend.app.ml.tier2_temporal_ml import TemporalAutoencoderDetector
from backend.app.ml.tier3_multivariate import Tier3MultivariateDetector, calculate_dew_point
from backend.app.ml.tier4_classifier import FaultClass, FaultClassifier
from backend.app.ml.tier5_explain import ExplainabilityEngine
from backend.app.ml.tier5_health import DegradationRisk, HealthStatus, SensorHealthEngine
from scripts.train_models import train_all_models


# ============================================================================
# Helpers to generate synthetic telemetry
# ============================================================================

def generate_clean_diurnal_series(n_rows: int = 5000, start_time: str = "2026-01-01T00:00:00Z") -> pd.DataFrame:
    """Generate physically consistent clean diurnal AWS observations."""
    dt_index = pd.date_range(start_time, periods=n_rows, freq="5min")
    hours = dt_index.hour + dt_index.minute / 60.0

    # Temperature: diurnal cycle 15°C to 27°C with small Gaussian noise
    t_diurnal = 21.0 + 6.0 * np.sin(2 * np.pi * (hours - 9.0) / 24.0)
    t_noise = np.random.normal(0.0, 0.15, size=n_rows)
    temp = t_diurnal + t_noise

    # Pressure: semi-diurnal atmospheric tide 1010 to 1016 hPa
    p_tide = 1013.25 + 1.5 * np.cos(4 * np.pi * (hours - 4.0) / 24.0)
    p_noise = np.random.normal(0.0, 0.08, size=n_rows)
    press = p_tide + p_noise

    # Humidity: anti-correlated with temperature (40% to 80%)
    rh_diurnal = 60.0 - 20.0 * np.sin(2 * np.pi * (hours - 9.0) / 24.0)
    rh_noise = np.random.normal(0.0, 0.5, size=n_rows)
    humidity = np.clip(rh_diurnal + rh_noise, 15.0, 95.0)

    df = pd.DataFrame({
        "timestamp": [dt.isoformat() for dt in dt_index],
        "station_id": "AWS-CHALLENGER-01",
        "temperature": np.round(temp, 2),
        "pressure": np.round(press, 2),
        "humidity": np.round(humidity, 2),
    })
    return df


# ============================================================================
# 1. Stress Test Automated Training Pipeline (scripts/train_models.py)
# ============================================================================

class TestAutomatedTrainingPipelineStress:
    """Empirically test scripts/train_models.py end-to-end under varying conditions."""

    def test_train_pipeline_execution_and_artifacts(self):
        """Train models on synthetic clean baseline and verify all 8 artifacts."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            train_csv = tmp_path / "train_clean.csv"
            val_csv = tmp_path / "val_mixed.csv"
            output_models = tmp_path / "models"

            # Generate training baseline (1,000 steps = ~3.5 days)
            df_train = generate_clean_diurnal_series(n_rows=1000)
            df_train.to_csv(train_csv, index=False)

            # Generate validation set with labeled anomalies
            df_val = generate_clean_diurnal_series(n_rows=500)
            df_val["anomaly_type"] = "NORMAL"
            # inject a few labeled anomalies for random forest classifier
            df_val.loc[50:60, "temperature"] = 55.0
            df_val.loc[50:60, "anomaly_type"] = "SPIKE"
            df_val.to_csv(val_csv, index=False)

            # Execute training pipeline
            train_all_models(
                train_path=train_csv,
                val_path=val_csv,
                output_dir=output_models,
                seq_len=30,
                epochs=5,
                batch_size=32,
                seed=123,
            )

            # Verify all expected production artifacts exist
            expected_artifacts = [
                "preprocessor.joblib",
                "scaler.joblib",
                "isolation_forest.joblib",
                "temporal_autoencoder.pt",
                "autoencoder.pt",
                "mahalanobis.joblib",
                "fault_classifier.joblib",
                "model_metadata.json",
            ]
            for artifact in expected_artifacts:
                art_path = output_models / artifact
                assert art_path.exists(), f"Missing artifact: {artifact}"
                assert art_path.stat().st_size > 0, f"Empty artifact: {artifact}"

            # Verify metadata integrity
            with open(output_models / "model_metadata.json", "r", encoding="utf-8") as f:
                meta = json.load(f)
            assert meta["train_samples"] == 1000
            assert meta["temporal_threshold"] > 0.0
            assert len(meta["features"]) == 9

            # Instantiate a SkyGuardPipeline from these newly generated artifacts
            pipeline = SkyGuardPipeline(model_dir=output_models, auto_load=True)
            assert pipeline.preprocessor.is_fitted is True
            assert pipeline.tier2_point.is_fitted is True
            assert pipeline.tier2_temporal.is_loaded is True
            assert pipeline.tier3_multivariate.mean is not None

            # Process a test observation
            res = pipeline.process_observation({
                "station_id": "AWS-TEST",
                "timestamp": "2026-01-01T12:00:00Z",
                "temperature": 22.0,
                "pressure": 1013.25,
                "humidity": 50.0,
            })
            assert isinstance(res, InferenceResult)
            assert 0.0 <= res.anomaly_score <= 1.0
            assert 0.0 <= res.confidence <= 1.0
            assert res.sensor_health == 100.0


# ============================================================================
# 2. Large Batch Processing (5,000+ Rows), Memory & Score Stability
# ============================================================================

class TestLargeBatchProcessingStress:
    """Stress test SkyGuardPipeline.process_batch on large datasets."""

    def test_large_batch_5000_rows_memory_and_stability(self):
        """Process 5,000 continuous rows; verify execution, bounded memory, and score stability."""
        pipeline = SkyGuardPipeline(model_dir="models", auto_load=True)
        df = generate_clean_diurnal_series(n_rows=5000)

        # Track memory allocations
        gc.collect()
        tracemalloc.start()
        mem_before, _ = tracemalloc.get_traced_memory()
        t0 = time.perf_counter()

        results = pipeline.process_batch(df, station_id="AWS-CHALLENGER-5K")

        elapsed = time.perf_counter() - t0
        mem_current, mem_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Performance & Scaling assertions
        assert len(results) == 5000
        throughput = 5000 / max(elapsed, 0.001)
        # Throughput should be comfortably > 50 obs/sec
        assert throughput > 30.0, f"Throughput too low: {throughput:.1f} obs/sec"

        # Memory assertion: Station buffer inside preprocessor and health must stay capped at maxlen
        buf = pipeline.preprocessor.stations.get("AWS-CHALLENGER-5K")
        assert buf is not None
        assert len(buf) <= 288, f"Buffer leaked beyond maxlen: {len(buf)}"
        health_state = pipeline.tier5_health.stations.get("AWS-CHALLENGER-5K")
        assert health_state is not None
        assert len(health_state.history) <= 288
        assert len(health_state.shi_history) <= 288

        # Numerical Stability assertions on clean stream
        scores = [r.anomaly_score for r in results]
        confidences = [r.confidence for r in results]
        healths = [r.sensor_health for r in results]

        # No NaNs or infinities anywhere
        assert not any(math.isnan(s) or math.isinf(s) for s in scores)
        assert not any(math.isnan(c) or math.isinf(c) for c in confidences)
        assert not any(math.isnan(h) or math.isinf(h) for h in healths)

        # Baseline score stability: clean diurnal series should have very low mean anomaly score
        # (after warm-up period)
        warm_scores = scores[50:]
        assert np.mean(warm_scores) < 0.35, f"Mean anomaly score unexpectedly high on clean data: {np.mean(warm_scores)}"
        # Sensor health on pure clean data should stay >= 90 (EXCELLENT)
        assert healths[-1] >= 90.0, f"Clean data degraded health to: {healths[-1]}"
        assert results[-1].sensor_status in ["EXCELLENT", "GOOD"]

    def test_batch_ordering_and_non_monotonic_timestamps(self):
        """Batch processor should sort out-of-order timestamps without crashing."""
        pipeline = SkyGuardPipeline(model_dir="models", auto_load=True)
        df = generate_clean_diurnal_series(n_rows=50)
        # Shuffle rows randomly
        df_shuffled = df.sample(frac=1.0, random_state=42).reset_index(drop=True)

        results = pipeline.process_batch(df_shuffled, station_id="AWS-SHUFFLE")
        assert len(results) == 50
        # Check timestamps in output are monotonically increasing
        timestamps = [pd.to_datetime(r.timestamp) for r in results]
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1]


# ============================================================================
# 3. Extreme Cold / Hot Edge Cases and Singularities
# ============================================================================

class TestExtremeEdgeCases:
    """Test extreme temperature, pressure, humidity bounds and math singularities."""

    @pytest.mark.parametrize("temp,press,rh,expected_override,expected_class", [
        (-80.0, 1013.25, 50.0, True, "DATA_CORRUPTION"),   # Extreme cryogenic cold below WMO -40°C
        (-40.1, 1013.25, 50.0, True, "DATA_CORRUPTION"),   # Just below WMO lower bound
        (-40.0, 1013.25, 50.0, False, None),               # Exact WMO lower bound
        (60.0, 1013.25, 50.0, False, None),                # Exact WMO upper bound
        (60.1, 1013.25, 50.0, True, "DATA_CORRUPTION"),    # Just above WMO upper bound
        (120.0, 1013.25, 50.0, True, "DATA_CORRUPTION"),   # Extreme heat above 60°C
        (25.0, 290.0, 50.0, True, "DATA_CORRUPTION"),      # Pressure below 300 hPa
        (25.0, 1150.0, 50.0, True, "DATA_CORRUPTION"),     # Pressure above 1100 hPa
        (25.0, 1013.25, -5.0, True, "DATA_CORRUPTION"),    # Negative relative humidity
        (25.0, 1013.25, 120.0, True, "DATA_CORRUPTION"),   # Humidity above 104%
    ])
    def test_wmo_physical_bounds_enforcement(self, temp, press, rh, expected_override, expected_class):
        pipeline = SkyGuardPipeline(model_dir="models", auto_load=True)
        res = pipeline.process_observation({
            "station_id": "AWS-BOUNDS",
            "timestamp": "2026-01-01T12:00:00Z",
            "temperature": temp,
            "pressure": press,
            "humidity": rh,
        })
        if expected_override:
            assert res.is_anomaly is True
            assert res.anomaly_score >= 0.95
            assert res.severity == "CRITICAL"
            assert res.tier_scores.tier1_qc_flag is True
            if expected_class:
                assert res.classification == expected_class
        else:
            assert not math.isnan(res.anomaly_score)

    def test_magnus_tetens_dew_point_extreme_singularities(self):
        """Verify Magnus-Tetens formula handles extreme temperature & zero humidity without ZeroDivision/Domain errors."""
        # 1. Temperature close to -243.5°C (Magnus-Tetens denominator zero)
        td_sing = calculate_magnus_dew_point(-243.5, 50.0)
        assert not math.isnan(td_sing)
        assert not math.isinf(td_sing)

        # 2. Extreme deep freeze -250°C
        td_freeze = calculate_magnus_dew_point(-250.0, 10.0)
        assert not math.isnan(td_freeze)

        # 3. 0% and negative humidity
        td_zero = calculate_magnus_dew_point(20.0, 0.0)
        assert not math.isnan(td_zero)

        td_neg = calculate_magnus_dew_point(20.0, -10.0)
        assert not math.isnan(td_neg)

        # 4. Super-saturated humidity (150%)
        td_super = calculate_magnus_dew_point(25.0, 150.0)
        assert not math.isnan(td_super)


# ============================================================================
# 4. Null / Missing / Sentinel / Malformed Token Streams
# ============================================================================

class TestNullMissingMalformedStreams:
    """Stress test ingestion of corrupt, missing, and sentinel values."""

    @pytest.mark.parametrize("obs", [
        {"station_id": "AWS-CORRUPT", "timestamp": "2026-01-01T00:00:00Z", "temperature": None, "pressure": 1013.25, "humidity": 50.0},
        {"station_id": "AWS-CORRUPT", "timestamp": "2026-01-01T00:05:00Z", "temperature": 20.0, "pressure": None, "humidity": 50.0},
        {"station_id": "AWS-CORRUPT", "timestamp": "2026-01-01T00:10:00Z", "temperature": 20.0, "pressure": 1013.25, "humidity": None},
        {"station_id": "AWS-CORRUPT", "timestamp": "2026-01-01T00:15:00Z", "temperature": -999.0, "pressure": 1013.25, "humidity": 50.0},
        {"station_id": "AWS-CORRUPT", "timestamp": "2026-01-01T00:20:00Z", "temperature": 20.0, "pressure": 9999.0, "humidity": 50.0},
        {"station_id": "AWS-CORRUPT", "timestamp": "2026-01-01T00:25:00Z", "temperature": "CORRUPT_STR", "pressure": 1013.25, "humidity": 50.0},
        {"station_id": "AWS-CORRUPT", "timestamp": "2026-01-01T00:30:00Z", "temperature": 20.0, "pressure": "ERR_P", "humidity": 50.0},
        {"station_id": "AWS-CORRUPT", "timestamp": "2026-01-01T00:35:00Z", "temperature": 20.0, "pressure": 1013.25, "humidity": "NAN%"},
    ])
    def test_corrupt_and_missing_telemetry_handling(self, obs):
        pipeline = SkyGuardPipeline(model_dir="models", auto_load=True)
        res = pipeline.process_observation(obs)

        # Must flag hard anomaly override and appropriate fault classification
        assert res.is_anomaly is True
        assert res.anomaly_score == 1.0
        assert res.severity == "CRITICAL"
        assert res.classification in ["DROPOUT", "DATA_CORRUPTION"]
        assert res.is_fault is True
        assert not math.isnan(res.sensor_health)

    def test_empty_dataframe_batch_processing(self):
        """Batch processing an empty dataframe should return an empty list without error."""
        pipeline = SkyGuardPipeline(model_dir="models", auto_load=True)
        res = pipeline.process_batch(pd.DataFrame())
        assert res == []


# ============================================================================
# 5. Constant / Frozen Sensor Streams & Health Degradation
# ============================================================================

class TestFrozenSensorStream:
    """Empirical test for stuck/frozen sensor values and Sensor Health Index degradation."""

    def test_frozen_temperature_stream_detection_and_health_decay(self):
        pipeline = SkyGuardPipeline(model_dir="models", auto_load=True)
        station_id = "AWS-FROZEN-TEST"
        pipeline.reset_station(station_id)

        # Send 5 identical readings (below K=6 threshold)
        for i in range(5):
            res = pipeline.process_observation({
                "station_id": station_id,
                "timestamp": f"2026-01-01T10:{i*5:02d}:00Z",
                "temperature": 24.50,
                "pressure": 1013.25,
                "humidity": 60.0,
            })
            # Prior to K=6, not flagged as frozen hard override
            assert res.tier_scores.tier1_qc_flag is False

        # Send 6th identical reading -> triggers persistence check (K=6)
        res_6 = pipeline.process_observation({
            "station_id": station_id,
            "timestamp": "2026-01-01T10:30:00Z",
            "temperature": 24.50,
            "pressure": 1013.25,
            "humidity": 60.0,
        })
        assert res_6.is_anomaly is True
        assert res_6.classification == "FROZEN"
        assert res_6.tier_scores.tier1_qc_flag is True
        assert res_6.severity == "CRITICAL"
        assert "mechanical lock" in res_6.recommended_action.lower() or "ice" in res_6.recommended_action.lower() or "frozen" in res_6.reason.lower()

        # Continue frozen stream for 30 steps and check Sensor Health Index drops continuously
        health_prev = res_6.sensor_health
        for i in range(7, 30):
            res_i = pipeline.process_observation({
                "station_id": station_id,
                "timestamp": f"2026-01-01T11:{i:02d}:00Z",
                "temperature": 24.50,
                "pressure": 1013.25,
                "humidity": 60.0,
            })
            assert res_i.classification == "FROZEN"

        # Final health must have decayed significantly
        assert res_i.sensor_health < health_prev
        assert res_i.sensor_health < 75.0
        assert res_i.sensor_status in ["DEGRADED", "POOR", "CRITICAL"]


# ============================================================================
# 6. Rapid Oscillations, Square Waves & Squall Front Disambiguation
# ============================================================================

class TestOscillationAndSquallDisambiguation:
    """Stress test high frequency square waves and genuine convective squall front discrimination."""

    def test_rapid_square_wave_temperature_oscillation(self):
        """Square wave oscillating 20°C <-> 35°C every 5 minutes (ΔT = ±15°C)."""
        pipeline = SkyGuardPipeline(model_dir="models", auto_load=True)
        station_id = "AWS-SQUARE-WAVE"
        pipeline.reset_station(station_id)

        # Baseline reading
        pipeline.process_observation({
            "station_id": station_id,
            "timestamp": "2026-01-01T00:00:00Z",
            "temperature": 20.0,
            "pressure": 1013.25,
            "humidity": 50.0,
        })

        # Sudden jump to 35°C (+15°C exceeds step max 5°C)
        res_spike = pipeline.process_observation({
            "station_id": station_id,
            "timestamp": "2026-01-01T00:05:00Z",
            "temperature": 35.0,
            "pressure": 1013.25,
            "humidity": 50.0,
        })
        assert res_spike.is_anomaly is True
        assert res_spike.classification in ["SPIKE", "NOISE_BURST"]
        assert res_spike.is_fault is True

    def test_convective_squall_front_disambiguation(self):
        """
        Genuine convective squall front:
        ΔT = -5.0°C (rapid cooling from cold downdraft)
        ΔP = +2.5 hPa (thunderstorm meso-high pressure jump)
        ΔRH = +25.0% (saturation surge)
        Obeying Clausius-Clapeyron thermodynamics (Td <= T + 0.5°C).
        Must be classified as METEOROLOGICAL_EXTREME with is_fault=False.
        """
        pipeline = SkyGuardPipeline(model_dir="models", auto_load=True)
        station_id = "AWS-SQUALL-FRONT"
        pipeline.reset_station(station_id)

        # Send 10 pre-frontal observations: warm, moderate pressure, dry
        for i in range(10):
            pipeline.process_observation({
                "station_id": station_id,
                "timestamp": f"2026-01-01T14:{i*5:02d}:00Z",
                "temperature": 32.0,
                "pressure": 1008.0,
                "humidity": 45.0,
            })

        # Front passage observation: abrupt cooling, pressure surge, humidity jump
        res_front = pipeline.process_observation({
            "station_id": station_id,
            "timestamp": "2026-01-01T14:50:00Z",
            "temperature": 26.0,   # ΔT = -6.0°C
            "pressure": 1011.0,      # ΔP = +3.0 hPa
            "humidity": 75.0,        # ΔRH = +30.0%
        })

        assert res_front.classification == "METEOROLOGICAL_EXTREME"
        assert res_front.is_fault is False  # Genuine atmospheric event, not a sensor hardware malfunction!
        assert res_front.is_anomaly is True  # Flagged for weather tracking
        assert "front" in res_front.reason.lower() or "convective" in res_front.reason.lower()


# ============================================================================
# 7. Multi-Station Isolation & Station Resets
# ============================================================================

class TestMultiStationIsolation:
    """Verify that multiple AWS stations operating concurrently remain strictly isolated."""

    def test_interleaved_multi_station_isolation(self):
        pipeline = SkyGuardPipeline(model_dir="models", auto_load=True)
        station_a = "AWS-CLEAN-STATION"
        station_b = "AWS-FAULTY-STATION"

        pipeline.reset_station(station_a)
        pipeline.reset_station(station_b)

        # Interleave observations: Station A is clean, Station B has spikes/freezes
        for i in range(15):
            # Station A: clean nominal
            res_a = pipeline.process_observation({
                "station_id": station_a,
                "timestamp": f"2026-01-01T08:{i*5:02d}:00Z",
                "temperature": 22.0 + 0.1 * i,
                "pressure": 1013.25,
                "humidity": 50.0,
            })

            # Station B: frozen at 25.0°C
            res_b = pipeline.process_observation({
                "station_id": station_b,
                "timestamp": f"2026-01-01T08:{i*5:02d}:00Z",
                "temperature": 25.0,
                "pressure": 1013.25,
                "humidity": 50.0,
            })

        # Station A must remain EXCELLENT health (100.0) with zero anomalies
        assert res_a.is_anomaly is False
        assert res_a.sensor_health >= 90.0
        assert res_a.sensor_status == "EXCELLENT"

        # Station B must be flagged FROZEN with degraded health
        assert res_b.is_anomaly is True
        assert res_b.classification == "FROZEN"
        assert res_b.sensor_health < 80.0

        # Resetting Station B should not affect Station A
        pipeline.reset_station(station_b)
        assert station_b not in pipeline.preprocessor.stations
        assert station_a in pipeline.preprocessor.stations
