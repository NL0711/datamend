# Original User Request

## Initial Request — 2026-08-24T00:30:10+05:30

Build **SkyGuard AI**: a production-grade, deploy-ready intelligent real-time anomaly detection, fault classification, and sensor health platform for Automatic Weather Stations (AWS). The system ingests Temperature (°C), Atmospheric Pressure (hPa), and Relative Humidity (%) observations, detects anomalies (spikes, dropouts, frozen sensors, drift, multivariate inconsistencies, data corruption), distinguishes genuine meteorological events from sensor faults using uncertainty-aware explainable AI, scores sensor health (0–100), predicts degradation, and presents everything through a professional operational dashboard with interactive anomaly injection. This is a single self-contained project; keep it small and focused.

Working directory: c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard
Integrity mode: demo

---

## Specification Files (Authoritative Reference)

The repository contains four specification files that define the system's behavioral rules, architecture, phased execution plan, and definition of success. **These files are the authoritative specification and must be followed closely:**

- **AGENTS.md** — Agent behavioral rules: no fake functionality, no hardcoded scores, phase-by-phase execution, definition of done
- **ARCHITECTURE.md** — Complete system architecture: 5-tier ML pipeline, data flow, database schema (SQLite), backend/frontend structure, API design, deployment model
- **TODO.md** — 23-phase sequential execution checklist (Phase 0–22) with granular tasks and exit criteria per phase
- **GOAL.md** — Definition of success, demo story (7 steps), example outputs, success criteria (13-point checklist), non-goals

**Critical rules from the spec (enforced):**
1. Work phase-by-phase per TODO.md — do NOT skip phases or implement everything at once
2. NEVER fake functionality: no hardcoded anomaly scores, no fake SHAP values, no mock data presented as real, no claimed accuracy without evaluation
3. Core ML must work with ONLY timestamp + temperature + pressure + humidity
4. Start with deterministic baselines before ML; start with simple ML before complex architectures
5. Every model must be evaluated with temporal train/val/test splits (no random splitting, no data leakage)
6. Update TODO.md after completing each phase
7. Never silently replace raw observations — always preserve raw data separately from corrections

---

## Reference Repositories (Pattern Extraction Only — Do NOT Copy Wholesale)

Extract concepts, mathematical patterns, and simulation logic from the following references. Do NOT blindly clone or merge these repositories. Use them as scientific/engineering references:

1. **expanso-io/log-simulators** (formerly acalhau-project/sensor-log-generator / logsim-iot):
   - Use for: simulator and anomaly injection logic
   - Extract: mathematical logic for realistic daily diurnal cycles (sinusoidal temperature/humidity relationships) and programmatic anomaly injection (spikes, linear calibration drift, frozen/stuck values, dropouts, noise)

2. **miksrv/arduino-weather-station**:
   - Use for: REST ingestion formats, payload schemas, time-series storage schema
   - Extract: reference for REST/MQTT ingestion patterns, baseline Level-1 rule checks (impossible physical boundaries)

3. **devajitdas35/HVAC-Maintenance-dataset**:
   - Use for: training datasets and health predictor validation
   - Extract: real-world DHT11/BMP280 sensor telemetry containing actual physical degradations to validate predictive maintenance algorithms

4. **cryologger/Automatic-Weather-Station**:
   - Use for: edge telemetry metadata modeling
   - Extract: payload formatting, battery/power constraints, low-power transmission formatting

5. **ITU TinyML Smart Weather Station Challenge**:
   - Use for: edge/esp32 quantization constraints
   - Extract: lightweight model constraints and TFLite Micro export compatibility patterns

---

## Requirements

### R1. Simulator and Data Generation Engine
Build a data simulation engine (ackend/simulator/) that generates realistic AWS telemetry:
- **Diurnal generator** (diurnal_generator.py): sinusoidal daily temperature/humidity cycles with configurable parameters (amplitude, phase, noise), realistic pressure variations
- **Anomaly injector** (nomaly_injector.py): programmatic injection of spikes (rapid single/multi-step transients), linear calibration drift (progressive offset), frozen/stuck values (zero variance over extended timestamps), dropouts (abrupt null/zero), noise bursts, and multivariate inconsistencies
- **Scenarios** (scenarios.py): pre-built test scenarios combining clean baselines with specific anomaly patterns for benchmarking
- The simulator must produce labeled datasets (ground truth anomaly labels) for training and evaluation

### R2. Complete 5-Tier ML Anomaly Detection Pipeline
Build a layered anomaly detection system in ackend/app/ml/:

**Tier 1 — Data Quality & Boundary Engine:** Physics bounds validation (−40°C to +60°C, 300–1100 hPa, 0–100% RH), rate-of-change checks (ΔT/Δt, ΔP/Δt), completeness checks, duplicate detection, frozen-value detection

**Tier 2 — Anomaly Detection:** Isolation Forest / One-Class SVM on standard-scaled (T, P, RH) for point anomalies. PyTorch GRU/LSTM Autoencoder on sliding windows (e.g., 30 steps) for temporal consistency — detecting unexpected transitions and trend violations via reconstruction error

**Tier 3 — Multivariate Consistency:** Cross-variable dependency analysis (e.g., Clausius-Clapeyron: temperature rise typically correlates with humidity drops under constant moisture). Reconstruction error and Mahalanobis distance across multivariate distributions

**Tier 4 — Fault Classification:** Classify detected anomalies into: SPIKE, DRIFT, FROZEN, DROPOUT, MULTIVARIATE_INCONSISTENCY, DATA_CORRUPTION, METEOROLOGICAL_EXTREME (genuine weather event where multivariate dynamics remain physically plausible), UNCERTAIN_EVENT

**Tier 5 — Sensor Health, Degradation & Explainability:** Dynamic sensor health index (0–100) tracking long-term degradation and drift frequency. SHAP/feature contribution scoring explaining why a reading was flagged. Optional imputation/value reconstruction when a fault is flagged (always preserving raw data)

**Anomaly Fusion:** Combine all tier signals into unified output: anomaly_score (0–1), confidence (0–1), severity (LOW/MEDIUM/HIGH/CRITICAL)

### R3. Full-Stack Operational System with Real-Time Ingestion
**Backend (FastAPI):**
- Clean service architecture — business logic in services, not in route handlers
- SQLite database with tables: stations, observations, anomaly_events, sensor_health, model_runs
- REST API endpoints: upload, observations, stations, anomalies, health, metrics, inference, simulation triggers, explanations
- WebSocket endpoint (/ws/live) for real-time telemetry streaming
- Real-time observation ingestion → validation → feature generation → inference → alert → database → dashboard push
- Measure and report inference latency

**Frontend (React/TypeScript):**
- Professional meteorological operations dashboard (NOT a generic admin panel)
- Views: Overview (station status, active alerts, anomaly rate), Live Monitoring (real-time charts with anomaly highlight regions for T/P/RH), Alert Center (severity, classification, confidence, explanation), Sensor Health (score, trend, fault history, degradation indicators), Event Detail (raw values, expected values, anomaly score, contributing factors), Data Explorer (historical exploration), Model Performance metrics
- **Interactive Anomaly Injection UI** (AnomalyInjectorUI/): buttons to inject specific anomaly types on the fly and observe real-time system response
- **Explainability Viewer** (ExplainabilityViewer/): SHAP contribution breakdowns per alert
- Clean information hierarchy, cards, charts, status indicators, responsive layout

**Docker:**
- docker-compose.yml orchestrating backend and frontend services
- Dockerfiles for both backend and frontend

### R4. Evaluation, Testing, and Reproducibility
- **Anomaly injection framework** for systematic evaluation: inject spikes, dropouts, frozen values, drift, multivariate anomalies into clean baselines
- **Model evaluation** with temporal train/val/test splits: precision, recall, F1, false-positive rate, detection latency per anomaly type and per model tier
- **Test suite** (	ests/): unit tests (validation, preprocessing, feature engineering, scoring, health), ML tests (model loading, inference, schema, score ranges), integration tests (upload → processing → inference → database → API), edge cases (missing values, duplicates, extremes, frozen, empty dataset, malformed input)
- **Reproducibility**: equirements.txt, environment setup instructions, training instructions, sample dataset, demo instructions
- **Evaluation report** (docs/evaluation_report.md): models, parameters, dataset versions, per-model metrics, fusion performance, known limitations

---

## Acceptance Criteria

### Simulator
- [ ] Running python -m backend.simulator.scenarios generates at least 3 labeled datasets: one clean baseline and two with different injected anomaly combinations
- [ ] Generated data follows realistic diurnal patterns (sinusoidal temperature curves, correlated humidity, realistic pressure variation) — not random noise

### ML Pipeline
- [ ] A test script scripts/test_anomaly_detection.py exists that: loads simulated data, injects at least 4 anomaly types (spike, frozen, drift, multivariate), runs the full 5-tier pipeline, and prints precision/recall/F1 per anomaly type
- [ ] F1 score ≥ 0.80 on injected anomalies across all tested fault types (measured by the test script above)
- [ ] The temporal model (GRU/LSTM Autoencoder) is actually trained on generated data and produces reconstruction errors — not hardcoded
- [ ] SHAP explanations are generated from the actual trained models — verified by checking that explanation values change when input data changes
- [ ] No anomaly scores, confidence values, SHAP explanations, or sensor health scores are hardcoded constants — verified by grep -rn for suspicious hardcoded floats in ackend/app/ml/

### Backend
- [ ] python -m uvicorn backend.app.main:app starts without errors
- [ ] All REST API endpoints return valid JSON responses with correct schemas
- [ ] POST upload with a CSV containing timestamp/temperature/pressure/humidity returns processed results with real anomaly scores from the trained models
- [ ] GET /api/health/{station_id} returns a health score that changes based on actual anomaly history
- [ ] WebSocket /ws/live accepts connections and streams real-time inference results
- [ ] Inference latency is measured and reported (target: < 500ms per observation for the full pipeline)

### Frontend
- [ ] 
pm run build completes without errors
- [ ] Dashboard displays at least 7 distinct views: overview, live monitoring, alerts, sensor health, event details, data explorer, anomaly injection UI
- [ ] Charts render real data from the API (not hardcoded sample data)
- [ ] The Anomaly Injection UI triggers real anomaly injection and the dashboard updates with detected anomalies in response

### Tests
- [ ] pytest tests/ -v passes with ≥ 50 test cases covering: data validation, preprocessing, feature engineering, anomaly scoring (all 5 tiers), health calculation, fault classification, API endpoints, edge cases (missing values, duplicates, frozen values, malformed input)

### End-to-End Demo
- [ ] The full demo story from GOAL.md Section 7 works: load normal data → inject anomaly (via UI or script) → system detects it in real-time → dashboard shows alert with severity/confidence/explanation/classification/health score/recommended action
- [ ] docker-compose up brings up the entire system (backend + frontend) and the demo is functional
- [ ] A new developer can follow the README to: clone → install → start → run demo within 15 minutes

### Evaluation Report
- [ ] docs/evaluation_report.md documents: all models used, training/validation/test periods, per-model metrics (precision/recall/F1/FPR), fusion performance, inference latency, and known limitations
- [ ] Temporal data splits are used (no random splitting) — verified in the training code
- [ ] No model claims accuracy without corresponding measured evaluation data

---

## Verification Resources

The four specification files in the repository (AGENTS.md, ARCHITECTURE.md, TODO.md, GOAL.md) serve as the authoritative reference specification. Objective verification:

1. **Automated:** pytest tests/ -v — must pass ≥ 50 cases
2. **ML benchmark:** python scripts/test_anomaly_detection.py — must show F1 ≥ 0.80 per fault type
3. **No-fake check:** grep -rn hardcoded\|FAKE\|TODO.*mock\|random\.\|0\.95\|0\.87\|0\.94 backend/app/ml/ backend/app/services/ — should return nothing suspicious
4. **Docker:** docker-compose up --build — should start cleanly
5. **Frontend build:** 
pm run build in rontend/ — should succeed
6. **End-to-end:** Start system → upload sample data → inject anomaly → verify alert appears in dashboard with real scores
