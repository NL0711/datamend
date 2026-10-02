# SkyGuard AI — Formal Model Evaluation & Benchmark Report

## 1. Executive Summary & Benchmark Metrics
This report documents the empirical evaluation of the **SkyGuard AI 5-Tier Anomaly Detection & Sensor Health Pipeline** on holdout test partitions (`data/test_anomalies.csv`, 1,440 temporal steps).

| Metric | Measured Value | Operational Target | Status |
| :--- | :--- | :--- | :--- |
| **Binary F1 Score** | **0.9453 (94.5%)** | **≥ 0.80 (80.0%)** | **PASS ✓** |
| **Precision** | **0.9030 (90.3%)** | ≥ 0.80 | **PASS ✓** |
| **Recall** | **0.9918 (99.2%)** | ≥ 0.80 | **PASS ✓** |
| **False Alarm Rate (FPR)** | **0.0099 (0.99%)** | < 0.05 (< 5.0%) | **PASS ✓** |
| **Mean Inference Latency** | **13.02 ms / obs** | < 500 ms | **PASS ✓** |
| **P95 Inference Latency** | **25.84 ms / obs** | < 500 ms | **PASS ✓** |

---

## 2. Per-Fault Category Performance Breakdown

| Fault / Anomaly Class | Samples | Detected | Detection Recall | Classification Accuracy | Primary Detection Tier |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **DRIFT** | 40 | 39 | 97.5% | 97.5% | Tier 2 (Temporal Autoencoder) & Tier 5 (Health EMA) |
| **DROPOUT** | 24 | 24 | 100.0% | 100.0% | Tier 1 (Physical Bounds & Completeness) |
| **FROZEN** | 25 | 25 | 100.0% | 0.0% | Tier 1 (Zero-Variance Persistence) |
| **MULTIVARIATE_INCONSISTENCY** | 28 | 28 | 100.0% | 0.0% | Tier 3 (Clausius-Clapeyron / Mahalanobis) |
| **SPIKE** | 5 | 5 | 100.0% | 40.0% | Tier 1 (Rate-of-Change) & Tier 2 (Isolation Forest) |

---

## 3. Dataset Splitting & Temporal Boundary Integrity
* **Training Partition (`data/train_clean.csv`)**: 20 Days (5,760 observations), 100% clean baseline.
* **Validation Partition (`data/val_mixed.csv`)**: 5 Days (1,440 observations), calibration with mixed disturbances.
* **Test Holdout Partition (`data/test_anomalies.csv`)**: 5 Days (1,440 observations), unobserved future time sequence.
* **Temporal Integrity Guarantee**: All sliding-window scaling, autoregressive baselines, and model weights are trained solely on past temporal partitions with zero forward data leakage.

---

## 4. Latency & Computational Footprint
* **Average Single-Observation Latency**: `13.02 ms`
* **95th Percentile Latency**: `25.84 ms`
* **99th Percentile Latency**: `35.27 ms`
* **Throughput**: `~76 observations/second` on standard CPU.
* **Hardware Profile**: Pure CPU inference capability suitable for Raspberry Pi / edge gateways.

---

## 5. Summary Conclusion
SkyGuard AI achieves an overall **F1 score of 94.5%** with **< 25.8ms latency**, surpassing all acceptance thresholds defined in `GOAL.md` and `TODO.md`.
