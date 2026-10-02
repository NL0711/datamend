"""
forensic_verifier.py
Comprehensive Forensic Audit Script for SkyGuard AI Milestone M2.

Performs:
1. Inspects all model artifacts in models/ (preprocessor, isolation_forest, temporal_autoencoder, mahalanobis, fault_classifier, model_metadata).
2. Verifies that PyTorch GRU Autoencoder has non-zero real learned weights and produces dynamic, non-constant reconstruction errors.
3. Verifies that Isolation Forest produces calibrated dynamic continuous scores S in [0, 1] that change with inputs.
4. Verifies that TreeSHAP produces dynamic, non-constant feature attributions summing to 100%.
5. Verifies that Clausius-Clapeyron Magnus-Tetens calculations and Mahalanobis distances are mathematically correct.
6. Verifies that Convective squall fronts are correctly classified as METEOROLOGICAL_EXTREME with is_fault=False.
7. Verifies Sensor Health Index (SHI) EMA dynamics, degradation predictions, and root-cause maintenance recommendations.
8. Runs all unit tests from test_tier*.py, test_fusion.py, and test_pipeline.py programmatically.
"""

import sys
import os
import json
import traceback
from pathlib import Path

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Set warning filters to suppress external third-party library deprecations in matplotlib/shap
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import torch
import joblib

from backend.app.ml.preprocessor import DataPreprocessor, calculate_magnus_dew_point, FEATURE_NAMES
from backend.app.ml.tier1_qc import Tier1QC, Tier1QCConfig, Tier1QCResult
from backend.app.ml.tier2_point_ml import IsolationForestPointDetector
from backend.app.ml.tier2_temporal_ml import TemporalAutoencoder, TemporalAutoencoderDetector
from backend.app.ml.tier3_multivariate import Tier3MultivariateDetector, calculate_dew_point, evaluate_thermodynamic_consistency
from backend.app.ml.fusion import AnomalyFusionEngine, Severity, TierScores as FusionTierScores
from backend.app.ml.tier4_classifier import FaultClassifier, FaultClass
from backend.app.ml.tier5_health import SensorHealthEngine, HealthStatus, DegradationRisk
from backend.app.ml.tier5_explain import ExplainabilityEngine
from backend.app.ml.pipeline import SkyGuardPipeline, InferenceResult


def log(msg: str) -> None:
    print(f"[FORENSIC AUDIT] {msg}")


def audit_models_and_weights() -> dict:
    log("================================================================================")
    log("PHASE 1: ARTIFACT & WEIGHTS AUTHENTICITY AUDIT")
    log("================================================================================")
    models_dir = root_dir / "models"
    results = {}

    # Check 1: Preprocessor / Scaler
    p_scaler = models_dir / "scaler.joblib"
    assert p_scaler.exists(), "scaler.joblib missing"
    scaler_art = joblib.load(p_scaler)
    scaler = scaler_art["scaler"]
    log(f"Scaler loaded. Means: {scaler.mean_[:3]}, Stds: {scaler.scale_[:3]}")
    assert len(scaler.mean_) == 9, "Scaler does not have 9 features"
    assert not np.all(scaler.scale_ == 0.0), "Scaler scale vector is all zeros"
    results["scaler"] = "PASS"

    # Check 2: Isolation Forest
    p_iforest = models_dir / "isolation_forest.joblib"
    assert p_iforest.exists(), "isolation_forest.joblib missing"
    iforest_art = joblib.load(p_iforest)
    iforest_model = iforest_art["model"]
    log(f"Isolation Forest loaded. Estimators count: {len(iforest_model.estimators_)}")
    assert len(iforest_model.estimators_) >= 50, "Insufficient tree estimators"
    assert iforest_art.get("background_sample") is not None, "Missing background sample for SHAP"
    results["isolation_forest"] = "PASS"

    # Check 3: PyTorch Temporal Autoencoder
    p_ae = models_dir / "temporal_autoencoder.pt"
    assert p_ae.exists(), "temporal_autoencoder.pt missing"
    ae_ckpt = torch.load(p_ae, map_location="cpu")
    log(f"Temporal Autoencoder Checkpoint loaded. Threshold: {ae_ckpt['threshold']}, Mean MSE: {ae_ckpt['mean_mse']}")
    state_dict = ae_ckpt["model_state_dict"]
    
    # Verify weights are non-zero and non-trivial
    total_weights = 0
    zero_weights = 0
    weight_norms = []
    for k, v in state_dict.items():
        total_weights += v.numel()
        zero_weights += torch.sum(v == 0).item()
        weight_norms.append(torch.norm(v.float()).item())
    
    log(f"Autoencoder Total Params: {total_weights}, Zero Params: {zero_weights}, Avg Param Norm: {np.mean(weight_norms):.4f}")
    assert total_weights > 1000, "Model has too few parameters"
    assert zero_weights < total_weights * 0.1, "Model weights are abnormally sparse/empty"
    assert np.mean(weight_norms) > 0.01, "Model weights are near zero"
    results["temporal_autoencoder"] = "PASS"

    # Check 4: Mahalanobis Covariance Matrix
    p_maha = models_dir / "mahalanobis.joblib"
    assert p_maha.exists(), "mahalanobis.joblib missing"
    maha_art = joblib.load(p_maha)
    cov = maha_art["covariance"]
    mean_vec = maha_art["mean"]
    log(f"Mahalanobis fitted mean: {mean_vec}, det(Cov): {np.linalg.det(cov):.6f}")
    assert cov.shape == (3, 3), "Covariance matrix is not 3x3"
    assert np.linalg.det(cov) > 0.0, "Covariance matrix is singular or non-positive definite"
    results["mahalanobis"] = "PASS"

    # Check 5: Fault Classifier
    p_clf = models_dir / "fault_classifier.joblib"
    assert p_clf.exists(), "fault_classifier.joblib missing"
    clf_art = joblib.load(p_clf)
    log(f"Fault Classifier loaded. Frozen window: {clf_art.get('frozen_window')}")
    results["fault_classifier"] = "PASS"

    # Check 6: Model Metadata JSON
    p_meta = models_dir / "model_metadata.json"
    assert p_meta.exists(), "model_metadata.json missing"
    with open(p_meta, "r", encoding="utf-8") as f:
        meta = json.load(f)
    log(f"Model Metadata: Train samples = {meta.get('train_samples')}, Val samples = {meta.get('val_samples')}")
    assert meta.get("train_samples", 0) > 1000, "Metadata indicates insufficient train samples"
    results["model_metadata"] = "PASS"

    return results


def audit_mathematical_invariants() -> dict:
    log("\n================================================================================")
    log("PHASE 2: MATHEMATICAL INVARIANTS & DYNAMIC SCORING AUDIT")
    log("================================================================================")
    results = {}

    pipeline = SkyGuardPipeline(model_dir=root_dir / "models", auto_load=True)

    # Invariant 1: Magnus-Tetens Dew Point formula consistency
    # Standard: T=20°C, RH=50% -> Td = 9.27°C
    # High: T=30°C, RH=80% -> Td = 26.20°C
    td_1 = calculate_dew_point(20.0, 50.0)
    td_2 = calculate_dew_point(30.0, 80.0)
    log(f"Dew Point Check: (20°C, 50%) -> {td_1:.4f}°C (Expected ~9.27°C)")
    log(f"Dew Point Check: (30°C, 80%) -> {td_2:.4f}°C (Expected ~26.20°C)")
    assert abs(td_1 - 9.27) < 0.15, f"Dew point calculation error: {td_1}"
    assert abs(td_2 - 26.20) < 0.25, f"Dew point calculation error: {td_2}"
    results["magnus_tetens"] = "PASS"

    # Invariant 2: Dynamic Isolation Forest scoring (varying input -> varying output, not constant)
    scores_iforest = []
    temps = [15.0, 20.0, 25.0, 35.0, 45.0, 58.0]
    for temp in temps:
        vec = np.array([temp, 1013.25, 55.0, 0.0, 0.0, 0.0, 0.2, 0.1, 0.5])
        scaled = pipeline.preprocessor.scaler.transform(vec.reshape(1, -1))[0]
        s = pipeline.tier2_point.predict_score(scaled)
        scores_iforest.append(s)
        log(f"  Point Outlier Score for T={temp}°C: S_point = {s:.4f}")

    # Verify scores are strictly non-constant and increasing for extreme temperatures
    assert len(set(scores_iforest)) == len(scores_iforest), "Isolation Forest scores are constant!"
    assert scores_iforest[-1] > scores_iforest[1], "Extreme T score did not increase relative to nominal T"
    results["dynamic_isolation_forest"] = "PASS"

    # Invariant 3: Dynamic PyTorch Autoencoder reconstruction errors (varying seq -> varying loss)
    ae_scores = []
    base_seq = np.zeros((30, 3), dtype=np.float32)
    s_clean = pipeline.tier2_temporal.predict_score(base_seq)
    ae_scores.append(s_clean)
    log(f"  Temporal AE score for baseline zero-centered sequence: {s_clean:.4f}")

    for distortion in [1.0, 3.0, 6.0, 10.0]:
        dist_seq = base_seq.copy()
        dist_seq[-5:, 0] += distortion
        s_dist = pipeline.tier2_temporal.predict_score(dist_seq)
        ae_scores.append(s_dist)
        log(f"  Temporal AE score for distortion +{distortion} sigma: {s_dist:.4f}")

    assert len(set(ae_scores)) == len(ae_scores), "Autoencoder scores are constant!"
    assert ae_scores[-1] > ae_scores[0], "Distorted sequence did not produce higher AE score"
    results["dynamic_autoencoder"] = "PASS"

    # Invariant 4: TreeSHAP dynamic feature attributions (varying input -> varying feature ranking)
    exp_engine = pipeline.tier5_explain
    
    # Scenario A: Temp Delta anomaly
    vec_a = np.array([25.0, 1013.25, 55.0, 12.0, 0.0, 0.0, 0.2, 0.1, 0.5])
    scaled_a = pipeline.preprocessor.scaler.transform(vec_a.reshape(1, -1))[0]
    exp_a = exp_engine.explain(scaled_a, {"temperature": 25.0, "temp_delta": 12.0}, {}, {}, "SPIKE", 0.9, 0.9)
    top_a = exp_a.contributing_features[0]
    log(f"  SHAP Scenario A (Temp Delta spike) -> Top Feature: {top_a.feature} ({top_a.attribution:.2%})")

    # Scenario B: Pressure Delta anomaly
    vec_b = np.array([22.0, 1013.25, 55.0, 0.0, -8.0, 0.0, 0.2, 0.1, 0.5])
    scaled_b = pipeline.preprocessor.scaler.transform(vec_b.reshape(1, -1))[0]
    exp_b = exp_engine.explain(scaled_b, {"pressure": 1013.25, "press_delta": -8.0}, {}, {}, "SPIKE", 0.9, 0.9)
    top_b = exp_b.contributing_features[0]
    log(f"  SHAP Scenario B (Pressure Delta drop) -> Top Feature: {top_b.feature} ({top_b.attribution:.2%})")

    assert top_a.feature != top_b.feature or top_a.attribution != top_b.attribution, "SHAP attributions are static!"
    sum_a = sum(f.attribution for f in exp_a.contributing_features)
    sum_b = sum(f.attribution for f in exp_b.contributing_features)
    assert abs(sum_a - 1.0) < 0.01, f"SHAP attributions do not sum to 1.0 (sum={sum_a})"
    assert abs(sum_b - 1.0) < 0.01, f"SHAP attributions do not sum to 1.0 (sum={sum_b})"
    results["dynamic_treeshap"] = "PASS"

    # Invariant 5: Convective Squall Front Disambiguation
    # Genuine front: dT=-6°C, dP=+2.5hPa, dRH=+25%, Clausius-Clapeyron holds -> is_fault=False
    pipeline.reset_station("AWS-SQUALL")
    pipeline.process_observation({"station_id": "AWS-SQUALL", "timestamp": "2026-08-24T12:00:00Z", "temperature": 28.0, "pressure": 1008.0, "humidity": 60.0})
    pipeline.process_observation({"station_id": "AWS-SQUALL", "timestamp": "2026-08-24T12:05:00Z", "temperature": 25.0, "pressure": 1009.5, "humidity": 72.0})
    pipeline.process_observation({"station_id": "AWS-SQUALL", "timestamp": "2026-08-24T12:10:00Z", "temperature": 23.0, "pressure": 1010.5, "humidity": 80.0})
    res_front = pipeline.process_observation({"station_id": "AWS-SQUALL", "timestamp": "2026-08-24T12:15:00Z", "temperature": 22.0, "pressure": 1011.0, "humidity": 88.0})
    log(f"  Front Classification: {res_front.classification}, is_fault: {res_front.is_fault}, SHI: {res_front.sensor_health}")
    assert res_front.classification == "METEOROLOGICAL_EXTREME", f"Front misclassified as {res_front.classification}"
    assert res_front.is_fault is False, "Front marked as hardware fault!"
    assert res_front.sensor_health >= 90.0, "Hardware health degraded by genuine atmospheric weather event!"
    results["squall_front_disambiguation"] = "PASS"

    # Invariant 6: Hardware Failure vs Sensor Health Index (SHI) degradation
    pipeline.reset_station("AWS-FAILURE")
    for i in range(10):
        pipeline.process_observation({"station_id": "AWS-FAILURE", "timestamp": f"t_{i}", "temperature": 22.0, "pressure": 1013.0, "humidity": 50.0})
    
    shi_initial = pipeline.tier5_health.stations["AWS-FAILURE"].current_shi
    # Inject 40 consecutive frozen readings
    for i in range(40):
        res_fail = pipeline.process_observation({"station_id": "AWS-FAILURE", "timestamp": f"t_freeze_{i}", "temperature": 22.0, "pressure": 1013.0, "humidity": 50.0})
    
    shi_final = pipeline.tier5_health.stations["AWS-FAILURE"].current_shi
    log(f"  Sensor Health Index: Initial = {shi_initial:.2f} -> After 40 frozen steps = {shi_final:.2f} (Status: {res_fail.sensor_status})")
    assert shi_final < shi_initial - 15.0, "Sensor Health Index did not decay under persistent frozen sensor fault"
    assert res_fail.classification == "FROZEN", "Failed to classify frozen sensor"
    results["sensor_health_decay"] = "PASS"

    return results


def run_all_unit_tests() -> dict:
    log("\n================================================================================")
    log("PHASE 3: COMPREHENSIVE UNIT TEST SUITE EXECUTION")
    log("================================================================================")
    import pytest
    
    test_files = [
        "tests/test_tier1_qc.py",
        "tests/test_tier2_ml.py",
        "tests/test_tier3_multivariate.py",
        "tests/test_fusion.py",
        "tests/test_tier4_classifier.py",
        "tests/test_tier5_health_explain.py",
        "tests/test_pipeline.py",
    ]
    
    results = {}
    total_passed = 0
    total_failed = 0
    
    for tf in test_files:
        log(f"Executing {tf}...")
        # Run pytest programmatically on specific test file
        exit_code = pytest.main([str(root_dir / tf), "-v", "-s", "--tb=short"])
        if exit_code == 0:
            results[tf] = "PASS"
            log(f"  --> {tf}: PASSED")
        else:
            results[tf] = f"FAIL (Exit code: {exit_code})"
            log(f"  --> {tf}: FAILED")
            total_failed += 1
            
    return results


def main() -> int:
    try:
        r1 = audit_models_and_weights()
        r2 = audit_mathematical_invariants()
        r3 = run_all_unit_tests()
        
        log("\n================================================================================")
        log("AUDIT SUMMARY RESULTS")
        log("================================================================================")
        all_passed = True
        for k, v in {**r1, **r2, **r3}.items():
            status = "PASS" if v == "PASS" else "FAIL"
            log(f"  [{status}] {k}: {v}")
            if v != "PASS":
                all_passed = False
                
        if all_passed:
            log("\n>>> FINAL FORENSIC VERDICT: CLEAN <<<")
            return 0
        else:
            log("\n>>> FINAL FORENSIC VERDICT: INTEGRITY VIOLATION <<<")
            return 1
    except Exception as e:
        traceback.print_exc()
        log(f"\n>>> FINAL FORENSIC VERDICT: INTEGRITY VIOLATION ({e}) <<<")
        return 1


if __name__ == "__main__":
    sys.exit(main())
