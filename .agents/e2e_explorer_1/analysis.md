# Comprehensive E2E Testing Architecture & Strategy Analysis

**Track**: E2E Testing Track  
**Agent**: `e2e_explorer_1`  
**Date**: 2026-08-24  
**Project**: SkyGuard AI — Intelligent Real-Time Anomaly Detection and Sensor Health System for Automatic Weather Stations

---

## 1. Executive Summary & Mission Scope

SkyGuard AI is a mission-critical meteorological quality-control and sensor-health platform designed to process continuous streams of Automatic Weather Station (AWS) telemetry consisting strictly of **Temperature ($T$)**, **Atmospheric Pressure ($P$)**, and **Relative Humidity ($RH$)**.

The objective of the E2E Testing Track is to establish a rigorous, production-grade 4-tier testing architecture that guarantees zero regressions, ensures strict adherence to meteorological physics, validates multi-tier ML inference, and verifies real-time full-stack operation without relying on mock data or fake functionality.

This document details the architectural design of the E2E testing framework, formalizes the 4-tier testing methodology, establishes the complete feature-to-test mapping, defines mathematical validation contracts, and provides actionable implementation blueprints for the E2E Test Writer.

---

## 2. The 4-Tier E2E Testing Methodology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                 TIER 4: REAL-WORLD APPLICATION SCENARIOS                │
│  • 72h Clean Diurnal Cycle        • Severe Thunderstorm / Cold Front    │
│  • 48h Progressive Sensor Drift   • Subzero Freezing Stuck Probe        │
│  • Multi-Station Network Stream   • Full 7-Step Demo Lifecycle (GOAL)   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────┴────────────────────────────────────┐
│                 TIER 3: CROSS-FEATURE COMBINATIONS                      │
│  • Ingest -> QC -> ML -> Persistence Pipeline                           │
│  • Simulator -> Buffer -> Inference -> WebSocket Streaming              │
│  • Anomaly Detection -> EMA Health Decay -> Escalation Alert            │
│  • Weather Front vs Sensor Spike Discrimination                         │
│  • CSV Upload -> Batch Processing -> Explorer Filter -> Aggregations    │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────┴────────────────────────────────────┐
│                 TIER 2: BOUNDARY & CORNER CASES                         │
│  • WMO Physical Limits (-40°C, +60°C, 300 hPa, 1100 hPa, 0%, 104%)     │
│  • Derivative Step Limits (ΔT/Δt = 5°C, ΔP/Δt = 4 hPa, ΔRH/Δt = 20%)    │
│  • Persistence Threshold (Exact K=6 boundary, K=5 normal)               │
│  • Malformed / Corrupt / Empty Payloads & NaN Injection                 │
│  • Sensor Health Score Saturation ([0, 100] clamping & EMA decay)       │
│  • Latency & High-Frequency Ingestion Throughput (<500ms profiling)    │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────┴────────────────────────────────────┐
│                 TIER 1: ISOLATED FEATURE COVERAGE                       │
│  • F01-F09: Simulator, Anomaly Injectors, Scenarios, Exporter CLI       │
│  • F10: Deterministic Quality Control & Rule Engine                     │
│  • F11-F12: Point ML (Isolation Forest) & Temporal ML (Autoencoder)     │
│  • F13-F14: Thermodynamic Consistency (Magnus-Tetens, Mahalanobis)      │
│  • F15-F16: Fusion Engine & Fault Taxonomy Classifier                   │
│  • F17-F18: Sensor Health Index & TreeSHAP Explainability               │
│  • F19-F21: SQLite Storage, FastAPI REST API, WebSocket Streaming       │
│  • F22-F35: Ingestion Service, Profiler, ViewModels, Benchmarks, Docs   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Mathematical & Physical Validation Framework

E2E tests must verify that algorithmic outputs match exact physical laws and statistical formulas:

### 3.1. Magnus-Tetens Saturation Vapor Pressure and Dew Point
For temperature $T \in [-40, +60]^\circ\text{C}$ and relative humidity $RH \in [0, 100]\%$, the saturation vapor pressure $E_s(T)$ and actual vapor pressure $E(T, RH)$ are given by:
$$E_s(T) = 6.112 \cdot \exp\left( \frac{17.67 \cdot T}{T + 243.5} \right) \quad [\text{hPa}]$$
$$E(T, RH) = E_s(T) \cdot \frac{RH}{100}$$
The dew point temperature $T_d$ is:
$$T_d = \frac{243.5 \cdot \ln(E / 6.112)}{17.67 - \ln(E / 6.112)}$$
**Validation Rule in Tests**: Under physical consistency, $T_d \le T + 0.5^\circ\text{C}$. Any observation where $T_d > T + 0.5^\circ\text{C}$ violates thermodynamics and must be flagged as a multivariate inconsistency.

### 3.2. Mahalanobis Distance Across Multivariate Distributions
Given mean vector $\boldsymbol{\mu} = [\mu_T, \mu_P, \mu_{RH}]^T$ and covariance matrix $\boldsymbol{\Sigma} \in \mathbb{R}^{3 \times 3}$, the squared Mahalanobis distance is:
$$D_M^2 = (\mathbf{x} - \boldsymbol{\mu})^T \boldsymbol{\Sigma}^{-1} (\mathbf{x} - \boldsymbol{\mu})$$
Under the null hypothesis of multivariate normality, $D_M^2 \sim \chi^2(3)$. The cumulative probability is:
$$p = F_{\chi^2(3)}(D_M^2)$$
**Validation Rule in Tests**: When $p > 0.999$, Tier 3 must flag a significant multivariate anomaly.

### 3.3. Sensor Health Index (SHI) EMA Smoothing
The dynamic health index $\text{SHI}_t \in [0, 100]$ is updated at step $t$ using exponential moving average (EMA) with smoothing factor $\alpha = 0.10$:
$$\text{SHI}_t = \alpha \cdot \text{RawHealth}_t + (1 - \alpha) \cdot \text{SHI}_{t-1}$$
Where $\text{RawHealth}_t = 100 \cdot (1 - \text{Penalty}_t)$, and penalty aggregates anomaly severity, persistence, and drift.
**Validation Rule in Tests**: Health scores must be strictly bounded $\in [0, 100]$, exhibit continuous decay upon repeated faults, and recover smoothly upon return to clean observations.

### 3.4. Multi-Tier Fusion Formulation
The final anomaly score $S \in [0, 1]$ is computed as:
$$S = \begin{cases} 
1.0 & \text{if Tier 1 Hard Physics QC triggers} \\ 
w_2 S_{\text{temporal}} + w_3 S_{\text{point}} + w_4 S_{\text{multivariate}} & \text{otherwise}
\end{cases}$$
where $\sum w_i = 1.0$. Confidence $C \in [0, 1]$ measures model consensus variance.
Severity is mapped as:
- $S < 0.30 \implies \text{LOW}$
- $0.30 \le S < 0.60 \implies \text{MEDIUM}$
- $0.60 \le S < 0.85 \implies \text{HIGH}$
- $S \ge 0.85 \lor \text{Tier 1 Violation} \implies \text{CRITICAL}$

---

## 4. Deep Dive: 4-Tier Test Specifications

### 4.1. Tier 1: Feature Coverage Specifications ($\ge 5$ tests per feature group)

1. **Simulator Engine (`test_simulator_features.py`)**:
   - `test_diurnal_generator_shape_and_columns`: Verifies generated DataFrame has timestamp, temperature, pressure, humidity with positive monotonic timestamps.
   - `test_diurnal_generator_physics_ranges`: Confirms sinusoidal $T, P, RH$ stay within realistic meteorological bounds ($10 \le T \le 35^\circ\text{C}$, $990 \le P \le 1025\text{ hPa}$, $30 \le RH \le 90\%$).
   - `test_diurnal_generator_inverse_correlation`: Asserts Pearson correlation between $T$ and $RH$ is significantly negative ($r < -0.60$).
   - `test_spike_injector_magnitude_and_labels`: Asserts injected spike modifies values by requested $\Delta T$ and sets ground-truth label `SPIKE`.
   - `test_drift_injector_linear_ramp`: Asserts drift linearly offsets values across specified time window.
   - `test_frozen_injector_zero_variance`: Asserts injected frozen window exhibits exact zero variance ($\sigma^2 = 0$).
   - `test_dropout_injector_null_values`: Asserts dropouts inject null/zero with correct label `DROPOUT`.
   - `test_noise_burst_injector_variance_increase`: Asserts injected noise window has variance $\ge 5\times$ baseline noise.
   - `test_multivariate_injector_breaks_correlation`: Asserts multivariate injection raises $T$ and $RH$ simultaneously to 100% saturation.
   - `test_scenarios_runner_generates_datasets`: Asserts pre-built scenarios (clean, mixed, extreme) generate valid datasets.
   - `test_dataset_exporter_cli_exports_csv`: Asserts CLI exports train/val/test splits to disk with valid header and row counts.

2. **Quality Control & Physics Rules (`test_qc_features.py`)**:
   - `test_wmo_temperature_limits_nominal`: Validates $T = 25.0^\circ\text{C}$ passes QC.
   - `test_wmo_temperature_limits_exceeded`: Validates $T = 65.0^\circ\text{C}$ and $T = -45.0^\circ\text{C}$ fail Tier 1 QC.
   - `test_wmo_pressure_limits`: Validates $P = 250\text{ hPa}$ and $P = 1150\text{ hPa}$ fail Tier 1 QC.
   - `test_wmo_humidity_limits`: Validates $RH = -5\%$ and $RH = 110\%$ fail Tier 1 QC.
   - `test_rate_of_change_temperature_exceeded`: Validates $\Delta T > 5.0^\circ\text{C}/5\text{min}$ triggers step-limit flag.
   - `test_rate_of_change_pressure_exceeded`: Validates $\Delta P > 4.0\text{ hPa}/5\text{min}$ triggers step-limit flag.
   - `test_persistence_frozen_sensor_detected`: Validates $K \ge 6$ identical consecutive readings triggers persistence flag.

3. **Machine Learning Models (`test_ml_point_temporal_features.py`)**:
   - `test_isolation_forest_inference_shape`: Asserts Isolation Forest returns score $\in [0, 1]$ for standard scaled feature vectors.
   - `test_isolation_forest_detects_outliers`: Asserts extreme feature vector produces anomaly score $> 0.70$.
   - `test_autoencoder_reconstruction_error_clean`: Asserts clean sliding window ($W=30$) has MSE reconstruction error $< \text{threshold}$.
   - `test_autoencoder_reconstruction_error_anomalous`: Asserts distorted sequence produces high MSE reconstruction error.
   - `test_ml_model_artifacts_loading`: Asserts model weights and scalers load cleanly from disk without memory leaks.

4. **Multivariate & Thermodynamic Consistency (`test_multivariate_physics_features.py`)**:
   - `test_dew_point_calculation_accuracy`: Asserts calculated $T_d$ matches Magnus-Tetens analytical reference within $\pm 0.05^\circ\text{C}$.
   - `test_dew_point_consistency_valid`: Validates $T_d \le T$ passes thermodynamic check.
   - `test_dew_point_supersaturation_violation`: Validates $T_d > T + 0.5^\circ\text{C}$ triggers thermodynamic inconsistency flag.
   - `test_mahalanobis_distance_clean_sample`: Asserts nominal $(T, P, RH)$ produces $p$-value $< 0.95$.
   - `test_mahalanobis_distance_anomalous_coupling`: Asserts unphysical $(T=50^\circ\text{C}, P=1030\text{ hPa}, RH=99\%)$ produces $p$-value $> 0.999$.

5. **Fusion & Fault Classification (`test_fusion_classifier_features.py`)**:
   - `test_fusion_tier1_override`: Asserts that when Tier 1 flags a hard violation, final anomaly score is immediately $1.0$ and severity is `CRITICAL`.
   - `test_fusion_weighted_combination_normal`: Asserts nominal tier scores combine into low score $< 0.20$ with `LOW` severity.
   - `test_fusion_confidence_scoring`: Asserts confidence reflects cross-model agreement.
   - `test_classifier_spike`: Asserts high $\Delta T$ with short duration classifies as `SPIKE`.
   - `test_classifier_drift`: Asserts steady linear increase over multiple windows classifies as `DRIFT`.
   - `test_classifier_frozen`: Asserts zero variance over $K \ge 6$ steps classifies as `FROZEN`.
   - `test_classifier_dropout`: Asserts abrupt drop to zero/null classifies as `DROPOUT`.
   - `test_classifier_meteorological_extreme`: Asserts simultaneous physically correlated shifts classify as `METEOROLOGICAL_EXTREME`.

6. **Sensor Health & Explainability (`test_health_explainability_features.py`)**:
   - `test_health_index_initial_score_100`: Asserts new station starts with health score $100.0$.
   - `test_health_index_ema_decay_on_fault`: Asserts consecutive anomalies decrease health score monotonically.
   - `test_health_index_recovery_on_clean`: Asserts subsequent clean observations restore health score gradually.
   - `test_shap_explanation_structure`: Asserts explanation contains summary string and non-empty contributing feature attributions.
   - `test_shap_attribution_sum_and_ranking`: Asserts feature with largest deviation receives highest attribution score.

7. **Database & API Layer (`test_db_repository_features.py`, `test_api_rest_features.py`, `test_websocket_streaming_features.py`)**:
   - `test_db_station_crud`: Creates, reads, updates station in SQLite.
   - `test_db_observation_persistence`: Inserts observation and retrieves with indexed timestamp search.
   - `test_db_anomaly_event_foreign_key`: Inserts anomaly event linked to observation record.
   - `test_api_get_stations`: Validates `GET /api/stations` returns 200 and station list schema.
   - `test_api_post_observation_sync`: Validates `POST /api/observations` processes record and returns `InferenceResult`.
   - `test_api_get_station_health`: Validates `GET /api/health/{station_id}` returns health index and trend.
   - `test_api_upload_csv_dataset`: Validates `POST /api/data/upload` parses multi-row CSV, runs pipeline, and returns summary stats.
   - `test_websocket_live_connection_and_broadcast`: Connects to `/ws/live`, injects observation via ingestion service, and asserts broadcast JSON matches schema.

---

### 4.2. Tier 2: Boundary & Corner Case Specifications

1. **Physics Boundary Limits (`test_boundary_physics_limits.py`)**:
   - `test_boundary_temperature_exact_limits`: $T = -40.0^\circ\text{C}$ (valid), $T = -40.01^\circ\text{C}$ (invalid), $T = +60.0^\circ\text{C}$ (valid), $T = +60.01^\circ\text{C}$ (invalid).
   - `test_boundary_pressure_exact_limits`: $P = 300.0\text{ hPa}$ (valid), $P = 299.9\text{ hPa}$ (invalid), $P = 1100.0\text{ hPa}$ (valid), $P = 1100.1\text{ hPa}$ (invalid).
   - `test_boundary_humidity_exact_limits`: $RH = 0.0\%$ (valid), $RH = -0.1\%$ (invalid), $RH = 104.0\%$ (valid), $RH = 104.1\%$ (invalid).
   - `test_boundary_temperature_absolute_zero`: Validates $T = -273.15^\circ\text{C}$ is rejected immediately.
   - `test_boundary_extreme_plausible_death_valley`: $T = 56.7^\circ\text{C}$ passes Tier 1 QC boundary check.

2. **Derivative Rate-of-Change Boundaries (`test_boundary_rate_of_change.py`)**:
   - `test_boundary_rate_of_change_exact_threshold`: $\Delta T = 5.00^\circ\text{C}$ (valid), $\Delta T = 5.01^\circ\text{C}$ (flagged).
   - `test_boundary_rate_of_change_zero_delta`: $\Delta T = 0.0^\circ\text{C}$ between two steps (valid, does not trigger ROC flag).
   - `test_boundary_rate_of_change_irregular_timestamp`: Time step $\Delta t = 10\text{ minutes}$ scales rate threshold accordingly.
   - `test_boundary_rate_of_change_micro_fluctuations`: Noise of $10^{-6\circ}\text{C}$ handled stably without numerical overflow.
   - `test_boundary_rate_of_change_negative_step`: $\Delta T = -5.01^\circ\text{C}$ triggers ROC drop flag.

3. **Persistence / Frozen Value Boundaries (`test_boundary_persistence_frozen.py`)**:
   - `test_boundary_persistence_k_equals_5`: Exactly 5 identical consecutive readings (valid, normal).
   - `test_boundary_persistence_k_equals_6`: Exactly 6 identical consecutive readings (flagged as `FROZEN`).
   - `test_boundary_persistence_floating_point_epsilon`: Values varying by $\le 10^{-5}$ treated as identical for frozen detection.
   - `test_boundary_persistence_alternating_values`: Values oscillating between $20.0$ and $20.001$ not falsely flagged as frozen.
   - `test_boundary_persistence_reset_on_change`: 5 identical readings followed by 1 different reading resets counter to 1.

4. **Malformed, Empty & Schema Violations (`test_boundary_malformed_empty.py`)**:
   - `test_boundary_empty_payload`: Empty JSON `{}` returns 422 Unprocessable Entity.
   - `test_boundary_missing_mandatory_field`: Payload missing `temperature` returns 422 with clear error detail.
   - `test_boundary_string_in_numeric_field`: `{"temperature": "twenty-five"}` returns 422.
   - `test_boundary_nan_and_infinity_rejection`: Payload with `NaN` or `Infinity` rejected gracefully with validation error.
   - `test_boundary_invalid_timestamp_format`: Malformed timestamp string `"2026-99-99T99:99:99"` rejected with 422.
   - `test_boundary_empty_csv_upload`: Uploading 0-byte CSV returns 400 Bad Request.

5. **Sensor Health Saturation Boundaries (`test_boundary_health_saturation.py`)**:
   - `test_boundary_health_upper_clamp`: 10,000 clean readings cannot push health score $> 100.0$.
   - `test_boundary_health_lower_clamp`: 10,000 continuous critical anomalies cannot push health score $< 0.0$.
   - `test_boundary_health_recovery_rate`: Recovery from health score 0.0 to 90.0 requires sustained clean observations governed by EMA $\alpha=0.10$.
   - `test_boundary_health_single_spike_penalty`: Single isolated spike decreases health score by $\le 15$ points, allowing swift recovery.
   - `test_boundary_health_floating_point_precision`: Health score rounded cleanly to 1 decimal place.

6. **Latency & High-Frequency Throughput (`test_boundary_latency_throughput.py`)**:
   - `test_boundary_inference_latency_under_500ms`: 100 single-observation inference calls average $< 50\text{ ms}$, max $< 500\text{ ms}$.
   - `test_boundary_batch_upload_throughput`: Batch of 1,000 observations processed in $< 3.0\text{ seconds}$.
   - `test_boundary_concurrent_stream_ingestion`: 10 simultaneous simulated stations streaming at 10 Hz handled without dropped records or database locks.
   - `test_boundary_memory_footprint_stability`: Processing 10,000 sequential records maintains constant RSS memory ($\Delta \text{RAM} < 20\text{ MB}$).

---

### 4.3. Tier 3: Cross-Feature Combination Specifications

1. **Ingest $\rightarrow$ QC $\rightarrow$ 5-Tier ML $\rightarrow$ Persistence (`test_combo_ingest_pipeline_db.py`)**:
   - Sends raw observation to ingestion service $\rightarrow$ verifies data flows through Tier 1 QC, Tier 2 ML, Tier 3 Thermodynamics, Tier 4 Classifier, Tier 5 Health $\rightarrow$ asserts database records created in `observations`, `anomaly_events`, and `sensor_health` with consistent foreign keys.
2. **Simulator $\rightarrow$ Live Buffer $\rightarrow$ Real-Time Inference $\rightarrow$ WebSocket (`test_combo_simulator_realtime_ws.py`)**:
   - Runs simulator stream $\rightarrow$ buffers last $W=30$ observations in memory $\rightarrow$ triggers real-time inference on new arrival $\rightarrow$ pushes JSON event over WebSocket `/ws/live` $\rightarrow$ verifies client receives complete `InferenceResult` payload with latency $< 200\text{ ms}$.
3. **Continuous Anomaly Injection $\rightarrow$ Health Decay $\rightarrow$ Alert Center (`test_combo_anomaly_health_alerts.py`)**:
   - Injects progressive drift over 50 steps $\rightarrow$ monitors health score decay from $100 \rightarrow 85 \rightarrow 60 \rightarrow 40$ $\rightarrow$ verifies alert escalation from `LOW` to `HIGH` to `CRITICAL` with recommendation updating to `"Calibrate sensor"`.
4. **CSV Bulk Upload $\rightarrow$ Batch Processing $\rightarrow$ Data Explorer Filter $\rightarrow$ Metrics (`test_combo_rest_filtering_export.py`)**:
   - Uploads 288-row CSV via `POST /api/data/upload` $\rightarrow$ queries `GET /api/observations?station_id=AWS-001&start_time=...` $\rightarrow$ queries `GET /api/metrics` $\rightarrow$ asserts processed observation count, anomaly count, and aggregate health metrics match batch summary.
5. **Meteorological Front vs Sensor Fault Discrimination (`test_combo_front_vs_fault_discrimination.py`)**:
   - Case A: Sudden sharp temperature spike (+25°C in 5 min) with constant pressure and RH $\rightarrow$ classified as `SPIKE` (Sensor Fault), severity `HIGH`.
   - Case B: Sudden sharp temperature drop (-10°C in 5 min) accompanied by pressure drop (-8 hPa) and RH surge (+35%) $\rightarrow$ classified as `METEOROLOGICAL_EXTREME` (Genuine Weather Event), severity `MEDIUM`/`LOW`, no false fault penalty on sensor health.

---

### 4.4. Tier 4: Real-World Application Scenario Specifications

1. **Scenario 1: 72-Hour Clean Diurnal Baseline (`test_scenario_diurnal_clean_baseline.py`)**:
   - Generates 72 hours of clean synthetic AWS observations (864 steps at 5-min intervals) with realistic day/night sinusoidal cycles and random atmospheric turbulence ($\sigma_T = 0.2^\circ\text{C}$).
   - Feeds all 864 observations sequentially through the real-time pipeline.
   - **Assertions**:
     - False Positive Rate $\le 2.0\%$ across all 864 steps.
     - Final Sensor Health Score $\ge 95.0$.
     - Zero `CRITICAL` severity alerts.
     - Maximum inference latency per step $< 100\text{ ms}$.

2. **Scenario 2: 48-Hour Progressive Sensor Drift & Degradation (`test_scenario_sensor_progressive_drift.py`)**:
   - Generates 48 hours of observations (576 steps): Hours 0–12 clean baseline, Hours 12–36 linear calibration drift $+0.2^\circ\text{C}/\text{hour}$ (reaching $+4.8^\circ\text{C}$ offset), Hours 36–48 sustained biased state.
   - Feeds observations sequentially.
   - **Assertions**:
     - Hours 0–12: Health score $100.0$, zero alerts.
     - Hours 20–36: Anomaly score rises $> 0.60$, classification identifies `DRIFT`.
     - Hours 36–48: Health score decays below $50.0$ (`Degraded`), recommended action triggers `"Inspect/calibrate temperature sensor"`.

3. **Scenario 3: Severe Thunderstorm / Cold Front Passage (`test_scenario_microburst_thunderstorm.py`)**:
   - Simulates a sudden squall line passage: Temperature drops from $32^\circ\text{C}$ to $18^\circ\text{C}$ in 15 minutes, Pressure drops 12 hPa and recovers, Humidity surges from $45\%$ to $98\%$.
   - **Assertions**:
     - Tier 3 thermodynamic check verifies $T_d \le T + 0.5^\circ\text{C}$ remains physically consistent.
     - Tier 4 classifier categorizes event as `METEOROLOGICAL_EXTREME` rather than sensor fault.
     - Sensor Health Index does not suffer penalization ($\text{SHI} \ge 90.0$).
     - Confidence score $> 0.85$.

4. **Scenario 4: Subzero Winter Night Freezing (`test_scenario_stuck_frozen_probe.py`)**:
   - Simulates AWS station operating at $-15^\circ\text{C}$ in freezing fog. At step 100, temperature sensor probe freezes and reports exact constant value $-15.000^\circ\text{C}$ for 4 hours (48 steps), while ambient pressure and humidity continue diurnal fluctuations.
   - **Assertions**:
     - At step 105 ($K=6$), Tier 1 persistence check triggers.
     - Tier 4 classifies observation as `FROZEN`.
     - Severity escalates to `HIGH`.
     - Sensor health score decays steadily to $< 40.0$ (`Poor`).
     - Explanation explicitly notes: `"Temperature sensor exhibiting zero variance over consecutive readings"`.

5. **Scenario 5: Multi-Station Network Ingestion (`test_scenario_multi_station_network.py`)**:
   - Simulates 5 distinct AWS stations streaming simultaneously:
     - `AWS-001` (Alpine Station): Clean, low temperature range.
     - `AWS-002` (Coastal Station): High humidity, clean.
     - `AWS-003` (Desert Station): High temperature, injected random spikes.
     - `AWS-004` (Urban Station): Injected progressive drift.
     - `AWS-005` (Island Station): Injected intermittent dropouts.
   - Streams 288 steps per station (1,440 total observations).
   - **Assertions**:
     - Database correctly isolates state, buffers, and health per `station_id`.
     - Station health ratings reflect respective injected fault profiles (`AWS-001`=Excellent, `AWS-003`=Degraded, `AWS-004`=Poor).
     - Overview API endpoint `GET /api/stations` returns correct aggregated network counts (2 Healthy, 1 Degraded, 2 Poor/Critical).

6. **Scenario 6: Full 7-Step Operator Demo Story (`test_scenario_end_to_end_demo_story.py`)**:
   - Programmatically executes the full 7-step demo story from GOAL.md Section 7:
     1. **Step 1**: Ingest clean normal AWS data $\rightarrow$ assert health=100%, alerts=0.
     2. **Step 2**: Trigger on-the-fly anomaly injection ($T=55^\circ\text{C}$ spike) via simulation API.
     3. **Step 3**: Real-time pipeline processes observation in $< 500\text{ ms}$.
     4. **Step 4**: System generates `ALERT` event with severity `HIGH`/`CRITICAL`.
     5. **Step 5**: Assert API returns complete explanation, SHAP attributions, confidence $> 90\%$, and classification `SPIKE`.
     6. **Step 6**: Fetch historical sensor health trend $\rightarrow$ verify observable degradation trajectory.
     7. **Step 7**: Verify recommendation string: `"Inspect/calibrate temperature sensor"`.

7. **Scenario 7: Evaluation Benchmark Verification ($F_1 \ge 0.80$) (`test_scenario_benchmark_f1.py`)**:
   - Executes `scripts/test_anomaly_detection.py` workflow against a standardized benchmark test dataset containing labeled ground-truth for `SPIKE`, `FROZEN`, `DRIFT`, and `MULTIVARIATE_INCONSISTENCY`.
   - Calculates Precision, Recall, $F_1$, and False Positive Rate.
   - **Assertions**:
     - Overall Macro $F_1 \ge 0.80$.
     - Precision $\ge 0.80$ per fault class.
     - Recall $\ge 0.80$ per fault class.
     - False Alarm Rate on baseline $< 5\%$.

---

## 5. Test Harness & Fixture Architecture

All E2E test files will inherit from centralized fixtures in `tests/e2e/conftest.py`:

```python
# Conceptual Fixture Architecture
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.main import app
from backend.app.db.database import Base, get_db
from backend.simulator.diurnal_generator import DiurnalGenerator
from backend.simulator.anomaly_injector import AnomalyInjector

@pytest.fixture(scope="session")
def engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

@pytest.fixture(scope="function")
def db_session(engine):
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
def diurnal_gen():
    return DiurnalGenerator(base_temp=22.0, base_pressure=1013.25, base_humidity=65.0)

@pytest.fixture
def injector():
    return AnomalyInjector()
```

---

## 6. Implementation Instructions for E2E Test Writer (Milestone E2E)

The E2E Test Writer agent should implement the test suite adhering strictly to these guidelines:

1. **File Placement**: Create all test files under `tests/e2e/` matching the directory layout specified in `TEST_INFRA.md`.
2. **Deterministic Reproducibility**: Set random seeds (`np.random.seed(42)`, `torch.manual_seed(42)`) in test fixtures to guarantee zero test flakiness.
3. **No Mocks on Core Algorithms**: Never mock the calculations of `tier1_qc.py`, `tier3_multivariate.py`, `fusion.py`, or `tier5_health.py`. Every test must execute the actual mathematical formulas and production functions.
4. **Execution Speed**: Use fast in-memory SQLite (`sqlite:///:memory:`) and vectorized numpy/pandas operations so that the entire $\ge 120$ test suite executes in $< 60\text{ seconds}$.
5. **Clear Assertion Failure Messages**: Write descriptive assertion messages explaining why a test failed (e.g., `assert res.status_code == 200, f"Expected 200 OK, got {res.status_code}: {res.text}"`).
6. **Publish Readiness**: Upon completion and verification of all tests passing, create `.agents/e2e_writer_1/handoff.md` and confirm that `pytest tests/e2e/ -v` passes cleanly.

---

## 7. Verification Method

To verify the test architecture design and readiness:
1. Verify `TEST_INFRA.md` exists at project root with complete 4-tier blueprint.
2. Confirm all 35 features from `PROJECT.md` are accounted for in the test mapping matrix.
3. Validate that test execution commands and markers are configured properly for `pytest`.
4. Ensure physical formulas (Magnus-Tetens, Clausius-Clapeyron, Mahalanobis, EMA health) are documented with exact mathematical bounds.
