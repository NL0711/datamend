# SkyGuard AI — NOAA ISD Observational Benchmark Report

**Benchmark Date:** 2026-08-25T10:18:27.472373+00:00  
**Dataset Source:** `data\noaa_benchmark.csv`  
**Station Evaluated:** `['725650-03017']`  
**Observation Span:** `2023-07-01T00:00:00+00:00` to `2023-07-21T19:00:00+00:00`  
**Total Observations:** 500 records  

---

## 1. Executive Summary & Empirical Results

The verified 5-Tier ML Quality Control & Anomaly Detection Pipeline was evaluated against real-world observational AWS time series from NOAA ISD archives.

- **Total Anomaly Detections:** **0** (0.00%)
- **Likely Sensor / Data Faults:** **0**
- **Likely Genuine Meteorological Extremes:** **0**
- **Mean Anomaly Score:** **0.3857**
- **P95 Anomaly Score:** **0.4048**
- **P99 Anomaly Score:** **0.4092**
- **Fleet Sensor Health Index (SHI):** **77.8 / 100**

---

## 2. Multi-Tier Contribution Breakdown

| ML Tier Subsystem | Metric | Measured Value |
| :--- | :--- | :---: |
| **Tier 1 (Deterministic QC)** | Rule Violation Count | 0 (0.00%) |
| **Tier 2 (Isolation Forest)** | Mean Point Outlier Score | 0.7373 |
| **Tier 2 (GRU Autoencoder)** | Mean Sequence Loss | 0.9420 |
| **Tier 3 (Mahalanobis & Dew Point)**| Mean Multivariate Score | 0.0000 |

---

## 3. 7-Class Fault Taxonomy Classification Breakdown

| Fault Classification Category | Observed Count | Percentage |
| :--- | :---: | :---: |
| `NORMAL` | **500** | 100.00% |

---

## 4. Scientific Findings & Real-World Generalization

1. **Nominal Stability:** Over 95% of nominal real-world weather observations generate calibrated anomaly scores below operational alert thresholds ($< 0.50$).
2. **Coupled Diurnal Dynamics:** Natural diurnal solar warming coupled with vapor pressure changes are recognised by Tier 3 Magnus-Tetens as thermodynamically consistent.
3. **Model Artifact Preservation:** Production models (`models/*.joblib`, `models/*.pt`) remained strictly unmodified throughout the benchmarking run.
