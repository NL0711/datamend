# SKYGUARD AI — E2E TEST INFRASTRUCTURE & ARCHITECTURE SPECIFICATION

## 1. System Overview & Testing Philosophy

SkyGuard AI is a production-grade meteorological quality control, real-time anomaly detection, fault classification, explainability, and sensor health platform for Automatic Weather Stations (AWS).
The core system operates strictly on three primary thermodynamic variables:
- **Temperature ($T$)**: $-40^\circ\text{C} \le T \le +60^\circ\text{C}$
- **Atmospheric Pressure ($P$)**: $300\text{ hPa} \le P \le 1100\text{ hPa}$
- **Relative Humidity ($RH$)**: $0\% \le RH \le 104\%$ (allowing up to 104% for supersaturation)

Because SkyGuard AI combines deterministic physical limits, non-linear ML models (Isolation Forest, PyTorch GRU/LSTM Autoencoder), thermodynamic equations (Clausius-Clapeyron / Magnus-Tetens), multi-tier fusion, rolling sensor health estimation, and real-time streaming over WebSockets and REST, testing must guarantee both scientific correctness and operational robustness.

### Core Testing Mandates:
1. **Zero Hardcoded Fakes**: Tests must strictly assert that anomaly scores, SHAP explanations, health indices, and predictions derive dynamically from real models and physics calculations.
2. **Temporal Splitting Integrity**: Time-series tests must preserve temporal ordering without forward data leakage.
3. **Physical & Mathematical Rigor**: Tests must validate against physical atmospheric constraints and exact statistical formulas.
4. **4-Tier Testing Depth**: All features must pass feature-level, boundary-level, cross-combination, and end-to-end meteorological scenario tests.

---

## 2. 4-Tier E2E Testing Methodology

```
+-------------------------------------------------------------------------+
|                  TIER 4: REAL-WORLD APPLICATION SCENARIOS               |
|   (Diurnal Cycles, Microbursts, Cold Fronts, 72h Degradation, Multi-AWS)|
+-------------------------------------------------------------------------+
                                    ^
+-------------------------------------------------------------------------+
|                  TIER 3: CROSS-FEATURE COMBINATIONS                     |
|  (Ingest->ML->DB, Stream->WebSocket, Anomaly->Health->Alert, Front/Fault)
+-------------------------------------------------------------------------+
                                    ^
+-------------------------------------------------------------------------+
|                  TIER 2: BOUNDARY & CORNER CASES                        |
|  (WMO Extremes, Frozen Persistence K=6, Malformed JSON, NaN/Empty Data) |
+-------------------------------------------------------------------------+
                                    ^
+-------------------------------------------------------------------------+
|                  TIER 1: ISOLATED FEATURE COVERAGE                      |
| (>= 5 tests per feature group: Simulator, QC, ML, Physics, Fusion, etc.)|
+-------------------------------------------------------------------------+
```

### Tier 1: Feature Coverage (Isolated Happy Path Verification)
- Minimum $\ge 5$ deterministic test cases per feature module.
- Verifies nominal functional behavior, valid data transforms, schema adherence, and expected state outputs.

### Tier 2: Boundary & Corner Cases (Limits, Extremes & Malformed Data)
- Minimum $\ge 5$ test cases per boundary domain.
- Tests exact WMO physical boundaries ($-40^\circ\text{C}$, $+60^\circ\text{C}$, $300\text{ hPa}$, $1100\text{ hPa}$, $0\%$, $104\%$), rate-of-change thresholds ($\Delta T/\Delta t = 5^\circ\text{C}/5\text{min}$), persistence threshold ($K=6$ identical consecutive steps), floating-point epsilon sensitivity, empty payloads, missing keys, and invalid types.

### Tier 3: Cross-Feature Combinations (Pairwise & Pipeline Interactions)
- Tests multi-component workflows:
  - Ingestion $\rightarrow$ Validation $\rightarrow$ 5-Tier ML $\rightarrow$ SQLite Persistence.
  - Anomaly Detection $\rightarrow$ Severity Escalation $\rightarrow$ EMA Health Score Decay $\rightarrow$ Alert Generation.
  - Diurnal Simulator $\rightarrow$ Live Buffer $\rightarrow$ Real-Time Inference $\rightarrow$ WebSocket Broadcast.
  - CSV Bulk Upload $\rightarrow$ Batch Processing $\rightarrow$ Data Explorer Filtering $\rightarrow$ Aggregate Metrics.

### Tier 4: Real-World Application Scenarios (Comprehensive End-to-End Workloads)
- Full lifecycle meteorological scenarios spanning hundreds/thousands of time steps:
  1. **Clean Diurnal Cycle (72h)**: Validates zero false alarms during normal daily solar heating / nocturnal cooling.
  2. **Sudden Severe Thunderstorm / Cold Front**: Distinguishes genuine meteorological extreme drops ($\Delta T = -12^\circ\text{C}, \Delta P = -15\text{ hPa}, \Delta RH = +40\%$) from sensor faults (`METEOROLOGICAL_EXTREME` vs `SPIKE`).
  3. **Progressive Sensor Drift (48h)**: Gradual calibration bias injection causing progressive Health Score degradation ($100 \rightarrow <50$) and maintenance recommendations.
  4. **Subzero Winter Night Freezing**: Sensor freezing at $-15^\circ\text{C}$ with constant output while pressure/humidity vary (`FROZEN` fault).
  5. **Multi-Station Network Operation**: Concurrent ingestion across 5 AWS stations with heterogeneous health statuses.
  6. **Full End-to-End Demo Lifecycle (GOAL.md Section 7)**: Complete 7-step operator workflow.

---

## 3. Feature Inventory & Test Mapping Matrix

| Feature ID | Feature Name | Tier 1 Tests | Tier 2 Tests | Tier 3 Tests | Tier 4 Scenarios | Target File |
|---|---|---|---|---|---|---|
| **F01** | Diurnal Cycle Generator | 5 | 5 | 2 | 2 | `tests/e2e/tier1_features/test_simulator_features.py` |
| **F02** | Spike Injector | 5 | 5 | 2 | 2 | `tests/e2e/tier1_features/test_simulator_features.py` |
| **F03** | Drift Injector | 5 | 5 | 2 | 2 | `tests/e2e/tier1_features/test_simulator_features.py` |
| **F04** | Frozen Value Injector | 5 | 5 | 2 | 2 | `tests/e2e/tier1_features/test_simulator_features.py` |
| **F05** | Dropout Injector | 5 | 5 | 2 | 1 | `tests/e2e/tier1_features/test_simulator_features.py` |
| **F06** | Noise Burst Injector | 5 | 5 | 2 | 1 | `tests/e2e/tier1_features/test_simulator_features.py` |
| **F07** | Multivariate Anomaly Injector | 5 | 5 | 2 | 2 | `tests/e2e/tier1_features/test_simulator_features.py` |
| **F08** | Benchmark Scenarios Runner | 5 | 3 | 2 | 2 | `tests/e2e/tier1_features/test_simulator_features.py` |
| **F09** | Dataset Exporter CLI | 5 | 4 | 2 | 1 | `tests/e2e/tier1_features/test_simulator_features.py` |
| **F10** | Tier 1 Physics QC Engine | 6 | 8 | 4 | 3 | `tests/e2e/tier1_features/test_qc_features.py` |
| **F11** | Tier 2 Isolation Forest Baseline | 5 | 5 | 3 | 2 | `tests/e2e/tier1_features/test_ml_point_temporal_features.py` |
| **F12** | Tier 2 GRU/LSTM Autoencoder | 5 | 5 | 3 | 2 | `tests/e2e/tier1_features/test_ml_point_temporal_features.py` |
| **F13** | Tier 3 Clausius-Clapeyron Dew Point | 5 | 6 | 3 | 2 | `tests/e2e/tier1_features/test_multivariate_physics_features.py` |
| **F14** | Tier 3 Mahalanobis Distance | 5 | 5 | 3 | 2 | `tests/e2e/tier1_features/test_multivariate_physics_features.py` |
| **F15** | Multi-Tier Fusion Engine | 6 | 6 | 4 | 3 | `tests/e2e/tier1_features/test_fusion_classifier_features.py` |
| **F16** | Tier 4 Fault Taxonomy Classifier | 8 | 6 | 4 | 3 | `tests/e2e/tier1_features/test_fusion_classifier_features.py` |
| **F17** | Tier 5 Sensor Health Index (EMA) | 6 | 6 | 4 | 3 | `tests/e2e/tier1_features/test_health_explainability_features.py` |
| **F18** | Tier 5 TreeSHAP & Reason Engine | 5 | 5 | 3 | 2 | `tests/e2e/tier1_features/test_health_explainability_features.py` |
| **F19** | SQLite Persistence & Repositories | 6 | 6 | 4 | 3 | `tests/e2e/tier1_features/test_db_repository_features.py` |
| **F20** | FastAPI REST Endpoints | 8 | 8 | 4 | 3 | `tests/e2e/tier1_features/test_api_rest_features.py` |
| **F21** | WebSocket `/ws/live` Streaming | 5 | 5 | 4 | 2 | `tests/e2e/tier1_features/test_websocket_streaming_features.py` |
| **F22** | Real-Time Ingestion Pipeline | 6 | 6 | 5 | 3 | `tests/e2e/tier3_combinations/test_combo_ingest_pipeline_db.py` |
| **F23** | Latency Profiler (<500ms) | 5 | 5 | 3 | 2 | `tests/e2e/tier2_boundaries/test_boundary_latency_throughput.py` |
| **F24-F31**| Frontend API & ViewModel Contracts | 8 | 6 | 4 | 2 | `tests/e2e/tier1_features/test_api_rest_features.py` |
| **F32** | E2E PyTest Execution Suite | - | - | - | - | Complete Suite Execution |
| **F33** | Benchmark Script ($F_1 \ge 0.80$) | 3 | 3 | 2 | 2 | `tests/e2e/tier4_scenarios/test_scenario_benchmark_f1.py` |
| **F34-F35**| Docker & Docs Verification | 4 | 2 | 2 | 1 | `tests/e2e/tier1_features/test_deployment_docs.py` |

**Total Target E2E Test Cases: $\ge 120$ tests.**

---

## 4. Test Directory Layout

```
tests/
├── __init__.py
├── conftest.py                             # Root fixtures: FastAPI TestClient, in-memory SQLite, mock models
└── e2e/
    ├── __init__.py
    ├── conftest.py                         # E2E fixtures: synthetic diurnal streams, injected anomaly datasets, WS clients
    │
    ├── tier1_features/
    │   ├── __init__.py
    │   ├── test_simulator_features.py      # F01-F09: Diurnal, injectors, scenarios, CLI
    │   ├── test_qc_features.py             # F10: Physics limits, derivatives, persistence
    │   ├── test_ml_point_temporal_features.py # F11-F12: Isolation Forest & GRU/LSTM Autoencoder
    │   ├── test_multivariate_physics_features.py # F13-F14: Clausius-Clapeyron, Mahalanobis
    │   ├── test_fusion_classifier_features.py # F15-F16: Fusion engine, Fault classifier
    │   ├── test_health_explainability_features.py # F17-F18: Sensor Health Index EMA, SHAP
    │   ├── test_db_repository_features.py  # F19: SQLite schema, ORM, repositories
    │   ├── test_api_rest_features.py       # F20: All REST routes and JSON schema adherence
    │   ├── test_websocket_streaming_features.py # F21: Live streaming, client connections
    │   └── test_deployment_docs.py         # F34-F35: Docker configs, docs validation
    │
    ├── tier2_boundaries/
    │   ├── __init__.py
    │   ├── test_boundary_physics_limits.py # -40°C, +60°C, 300hPa, 1100hPa, 0%, 104%
    │   ├── test_boundary_rate_of_change.py # Delta limits, single-step transitions, micro-noise
    │   ├── test_boundary_persistence_frozen.py # Exact K=6 boundary, K=5 normal, float precision
    │   ├── test_boundary_malformed_empty.py# Empty CSV/JSON, NaN, nulls, missing keys, invalid types
    │   ├── test_boundary_health_saturation.py # Health clamped [0, 100], 0-recovery, rapid spikes
    │   └── test_boundary_latency_throughput.py# Burst ingestion, buffer overrun, latency < 500ms
    │
    ├── tier3_combinations/
    │   ├── __init__.py
    │   ├── test_combo_ingest_pipeline_db.py # End-to-end ingestion -> ML -> DB persistence
    │   ├── test_combo_simulator_realtime_ws.py # Simulator -> Realtime Buffer -> Inference -> WS
    │   ├── test_combo_anomaly_health_alerts.py # Anomaly injection -> Health decay -> Alert trigger
    │   ├── test_combo_rest_filtering_export.py # Upload CSV -> Filter -> Export -> Aggregations
    │   └── test_combo_front_vs_fault_discrimination.py # Meteorological front vs sensor spike
    │
    └── tier4_scenarios/
        ├── __init__.py
        ├── test_scenario_diurnal_clean_baseline.py # 72h clean diurnal cycle (0 false alarms)
        ├── test_scenario_sensor_progressive_drift.py # 48h calibration drift -> Health < 50 -> Alert
        ├── test_scenario_microburst_thunderstorm.py # Severe weather front -> MET_EXTREME
        ├── test_scenario_stuck_frozen_probe.py # Winter freezing stuck value -> FROZEN fault
        ├── test_scenario_multi_station_network.py # 5 concurrent AWS stations with mixed health
        ├── test_scenario_benchmark_f1.py   # Benchmark script verification ($F_1 \ge 0.80$)
        └── test_scenario_end_to_end_demo_story.py # Full 7-step operator demo workflow (GOAL.md)
```

---

## 5. Test Runner Commands & Configuration

### `pytest.ini` Configuration
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --strict-markers --durations=10
markers =
    e2e: End-to-end integration and system tests
    tier1: Tier 1 Feature Coverage tests
    tier2: Tier 2 Boundary & Corner Case tests
    tier3: Tier 3 Cross-Feature Combination tests
    tier4: Tier 4 Real-World Application Scenario tests
    simulator: Simulator and data generation tests
    qc: Quality control and physics checks
    ml: Machine learning model inference and training tests
    api: REST API and WebSocket tests
    slow: Tests running > 2 seconds
```

### Execution Commands:

1. **Run Entire E2E Suite**:
   ```bash
   pytest tests/e2e/ -v
   ```

2. **Run by Specific Tier**:
   ```bash
   pytest tests/e2e/tier1_features/ -v
   pytest tests/e2e/tier2_boundaries/ -v
   pytest tests/e2e/tier3_combinations/ -v
   pytest tests/e2e/tier4_scenarios/ -v
   ```

3. **Run by Marker**:
   ```bash
   pytest -m tier1 -v
   pytest -m tier2 -v
   pytest -m tier3 -v
   pytest -m tier4 -v
   pytest -m "not slow" -v
   ```

4. **Run Benchmark Script**:
   ```bash
   python scripts/test_anomaly_detection.py
   ```

5. **Coverage Measurement**:
   ```bash
   pytest --cov=backend/app --cov=backend/simulator tests/e2e/ --cov-report=term-missing --cov-report=html
   ```

---

## 6. Quality Gates & Coverage Thresholds

| Metric | Minimum Required Gate | Target Standard |
|---|---|---|
| **Total Test Count** | $\ge 50$ tests | $\ge 120$ tests |
| **Tier 1 Feature Coverage** | $\ge 5$ tests / feature domain | $\ge 50$ tests |
| **Tier 2 Boundary Coverage** | $\ge 5$ tests / boundary group | $\ge 35$ tests |
| **Tier 3 Combination Coverage**| $\ge 3$ tests / workflow | $\ge 20$ tests |
| **Tier 4 Scenario Coverage** | $\ge 6$ full scenarios | $\ge 15$ scenario steps |
| **Anomaly Detection $F_1$** | $F_1 \ge 0.80$ overall | $F_1 \ge 0.85$ per fault class |
| **False Positive Rate (FPR)** | $\le 5.0\%$ on clean diurnal | $\le 2.0\%$ on clean diurnal |
| **Inference Latency** | $< 500\text{ ms}$ per record | $< 50\text{ ms}$ per record |
| **Code Line Coverage** | $\ge 80\%$ | $\ge 90\%$ |
| **Zero Hardcoded Fakes** | $100\%$ compliance | No mock constants in inference |

---

## 7. Implementation Instructions for E2E Test Writer

When Milestone E2E executes:

1. **Use Pytest Fixtures**:
   - `test_client`: FastAPI `TestClient(app)` with an in-memory SQLite database (`sqlite:///:memory:`).
   - `clean_diurnal_df`: Pre-generated 24h/72h realistic diurnal pandas DataFrame.
   - `injected_anomaly_df`: DataFrame containing labeled anomalies for each of the 6 fault classes.
   - `ws_client`: Async/sync WebSocket test client for `/ws/live`.

2. **Strict Verification Rules**:
   - For Tier 1: Assert precise mathematical outputs (e.g., Magnus-Tetens dew point within $\pm 0.1^\circ\text{C}$).
   - For Tier 2: Check boundary edges $T = 60.0^\circ\text{C}$ (valid), $T = 60.01^\circ\text{C}$ (invalid).
   - For Tier 3: Verify that an injected spike increases the anomaly score, classifies as `SPIKE`, decrements `sensor_health`, and emits an alert with severity `HIGH`/`CRITICAL`.
   - For Tier 4: Execute multi-step scenarios, verifying that over 288 steps (24h) of clean data, the health score remains $\ge 95$, and upon 10 consecutive frozen readings, health degrades and recommended action changes to `"Inspect sensor"`.

3. **No Mocking of Core ML Logic**:
   - All tests must exercise real model inference or real mathematical rules. Do not mock return values of `tier1_qc.py`, `fusion.py`, or `tier5_health.py`.
