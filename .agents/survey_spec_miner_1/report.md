# SkyGuard AI — Comprehensive Specification Analysis Report

**Document Version:** 1.0.0  
**Mining Agent:** `survey_spec_miner_1`  
**Date:** 2026-08-24  
**Authoritative Sources:** `ORIGINAL_REQUEST.md`, `AGENTS.md`, `ARCHITECTURE.md`, `TODO.md`, `GOAL.md`

---

## 1. Executive Summary & Specification Scope

**SkyGuard AI** is a production-grade, deploy-ready, executable, and demonstrably verifiable AI/ML platform for Automatic Weather Stations (AWS). Its core mission is to answer a single operational question for every incoming meteorological observation:
> **"Is this a genuine atmospheric observation or is the sensor/data likely faulty?"**

Rather than relying on isolated threshold checks or opaque black-box machine learning, SkyGuard AI integrates:
- **Deterministic physical & rate-of-change boundary rules** (Tier 1)
- **Point & temporal ML anomaly detection** (Isolation Forest & GRU/LSTM Autoencoders) (Tier 2)
- **Thermodynamic & multivariate consistency analysis** (Clausius-Clapeyron, Mahalanobis distance) (Tier 3)
- **Taxonomic fault classification & genuine extreme vs. sensor fault discrimination** (Tier 4)
- **Calibrated confidence scoring, dynamic sensor health index (0–100), and explainable AI (SHAP / feature contributions)** (Tier 5)
- **Full-stack operational delivery** via a FastAPI backend (REST + WebSocket `/ws/live`), SQLite persistence, and a specialized React/TypeScript meteorological operations dashboard with interactive anomaly injection.

---

## 2. Strict Architectural & Behavioral Constraints

Per `AGENTS.md` and `ORIGINAL_REQUEST.md`, the following rules are non-negotiable and strictly enforced across all phases:

1. **Strict Core Input Constraints:**
   - The core ML system **must work with ONLY three primary meteorological variables**:
     1. **Temperature (°C)**
     2. **Atmospheric Pressure (hPa)**
     3. **Relative Humidity (%)**
   - Optional metadata: `timestamp`, `station_id`, `latitude`, `longitude`, `elevation`.
   - The system must not make external variables (wind, solar radiation, precipitation) mandatory.

2. **Absolute Prohibition of Fake/Mocked Functionality:**
   - **Zero Hardcoded Scores:** Never hardcode anomaly scores, confidence values, SHAP explanations, or sensor health scores.
   - **No Random Inference:** Never use random numbers or dummy heuristics in production inference paths.
   - **Real Model Training:** Never claim a model is trained or evaluated unless real weights and measured metrics exist.
   - **Verification:** Enforced via `grep -rn "hardcoded\|FAKE\|TODO.*mock\|random\.\|0\.95\|0\.87" backend/app/ml/`.

3. **Temporal Data Splitting & Leakage Prevention:**
   - All dataset partitioning must follow strict temporal ordering:
     - **Train:** Earliest time period (e.g., Days 1–60)
     - **Validation:** Intermediate time period (e.g., Days 61–75)
     - **Test:** Future unseen time period (e.g., Days 76–90)
   - **No random train_test_split** across time series data to prevent temporal data leakage.

4. **Raw Data Preservation:**
   - If optional value correction/imputation is implemented, raw observations must **never be overwritten or mutated**. Raw and corrected values are stored and exposed separately.

5. **Layered Progression & Modular Design:**
   - Complete phases sequentially per `TODO.md` (Phase 0 through Phase 22).
   - Establish deterministic baselines before ML models; establish simpler ML baselines (Isolation Forest) before deep temporal models (GRU/LSTM Autoencoders).
   - Decouple services from API routes and keep ML models swappable via standardized interfaces.

6. **Initial Persistence:**
   - SQLite initial implementation with structured repository abstractions to allow zero-friction migration to PostgreSQL.

---

## 3. Core Functional Requirements (R1 – R4)

### R1. Simulator and Synthetic AWS Data Generation Engine
- **Diurnal Generator (`backend/simulator/diurnal_generator.py`):**
  - Synthesizes realistic diurnal sinusoidal temperature curves ($T_{min}$ at dawn, $T_{max}$ in early afternoon).
  - Correlated inverse relative humidity cycle based on atmospheric moisture dynamics.
  - Realistic barometric pressure variations (semi-diurnal atmospheric tides $\pm 1$ to $2\text{ hPa}$ + synoptic pressure systems).
  - Configurable noise, base temperature, amplitude, phase shifts, and temporal resolutions (1-min, 5-min, 10-min intervals).
- **Anomaly Injector (`backend/simulator/anomaly_injector.py`):**
  - **Spikes:** Single or multi-step instantaneous unrealistic jumps ($\Delta T > 15^\circ\text{C}$ in 5 min).
  - **Calibration Drift:** Progressive linear or exponential offset ($+0.05^\circ\text{C}/\text{hour}$) simulating uncalibrated sensor degradation.
  - **Frozen/Stuck Sensor:** Variance drops to exact zero ($\sigma^2 = 0$) over prolonged consecutive intervals.
  - **Dropouts / Missing Values:** Intermittent or burst dropouts to null/NaN or 0.0 readings.
  - **Noise Bursts:** High-frequency electrical or transmission noise degradation.
  - **Multivariate Inconsistency:** Breaking physical relationships (e.g., simultaneous spike in temperature and relative humidity exceeding saturated vapor limits).
- **Benchmark Scenarios (`backend/simulator/scenarios.py`):**
  - Standard test scenarios generating labeled ground-truth datasets for training, baseline comparison, and evaluation benchmarks.

### R2. Complete 5-Tier ML Anomaly Detection Pipeline
- **Tier 1 — Data Quality & Boundary Engine:**
  - Physical plausibility checks: Temperature ($-40^\circ\text{C}$ to $+60^\circ\text{C}$), Pressure ($300\text{ hPa}$ to $1100\text{ hPa}$), Humidity ($0\%$ to $100\%$).
  - Rate-of-change (RoC) limits: $|\Delta T/\Delta t|$, $|\Delta P/\Delta t|$, $|\Delta \text{RH}/\Delta t|$.
  - Completeness, missing value, duplicate timestamp, and frozen value ($\Delta = 0$ over $N$ steps) detection.
- **Tier 2 — Point & Temporal Anomaly Detection:**
  - **Point Anomaly:** Isolation Forest trained on scaled observations $[T, P, \text{RH}]$ and rolling statistical features.
  - **Temporal Sequence Anomaly:** PyTorch GRU/LSTM Autoencoder operating on sliding windows (e.g., sequence length $L = 30$ steps); flags unexpected transitions and trend violations via reconstruction error $\|X - \hat{X}\|_2$.
- **Tier 3 — Multivariate Consistency Engine:**
  - Thermodynamic cross-dependency analysis (Clausius-Clapeyron relation, dew point proxy, psychrometric bounds).
  - Mahalanobis distance & multivariate autoencoder reconstruction error capturing anomalous variable interactions.
- **Tier 4 — Fault Classification Engine:**
  - Classifies flagged events into definitive taxonomies:
    1. `SPIKE`
    2. `DROPOUT`
    3. `FROZEN`
    4. `DRIFT`
    5. `MULTIVARIATE_INCONSISTENCY`
    6. `DATA_CORRUPTION`
    7. `METEOROLOGICAL_EXTREME` (Genuine weather event with physically consistent multi-variable dynamics)
    8. `UNCERTAIN_EVENT`
  - Employs hybrid rule + ML classification to separate genuine meteorological extremes from sensor faults.
- **Tier 5 — Sensor Health, Degradation & Explainability:**
  - **Sensor Health Index (0–100):** Weighted multi-factor metric factoring anomaly frequency, persistent faults, drift score, and data completeness over rolling windows.
    - $90\text{--}100$: Excellent | $75\text{--}89$: Good | $50\text{--}74$: Degraded | $25\text{--}49$: Poor | $0\text{--}24$: Critical.
  - **Degradation Prediction:** Trend analysis of sensor health decay, alerting when maintenance is required (`stable`, `degrading`, `high_risk`, `maintenance_recommended`).
  - **Explainability Engine:** SHAP (Kernel/Tree SHAP) and feature attribution breakdowns explaining exactly why an observation was flagged in plain human-readable language.
  - **Anomaly Fusion:** Combines Tier 1–4 signals into unified triplet: `anomaly_score` ($0\text{--}1$), `confidence` ($0\text{--}1$), and `severity` (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`).

### R3. Full-Stack Operational System & Real-Time Ingestion
- **FastAPI Backend (`backend/app/`):**
  - Layered service architecture (`api/`, `services/`, `models/`, `schemas/`, `db/`, `core/`).
  - SQLite database schemas: `stations`, `observations`, `anomaly_events`, `sensor_health`, `model_runs`.
  - Comprehensive REST endpoints: dataset upload, observation querying, station management, anomaly retrieval, sensor health status, model evaluation metrics, single/batch inference, simulation triggers.
  - WebSocket streaming endpoint (`/ws/live`) for real-time telemetry streaming and push alerts.
  - Real-time observation processing buffer and measured inference latency ($< 500\text{ ms}$ target).
- **React / TypeScript Frontend (`frontend/src/`):**
  - Meteorological operational command center.
  - **7 Core Operational Views:**
    1. **Overview:** System status, active stations, health breakdown, active alerts, real-time anomaly rates.
    2. **Live Monitoring:** Real-time multi-series time-series charts for T/P/RH with highlighted anomaly regions.
    3. **Alert Center:** Filterable alert feed with severity tags, fault classification, confidence, and timestamps.
    4. **Sensor Health:** Health score gauges, historical trendlines, component degradation indicators (drift, anomaly rate, quality).
    5. **Event Details / Explainability Viewer:** Deep-dive modal/page showing raw vs expected values, SHAP feature attributions, contributing rules, and recommended operator action.
    6. **Data Explorer:** Historical telemetry exploration, filtering, and validation status inspection.
    7. **Interactive Anomaly Injection UI:** Live controls to inject spikes, drift, frozen values, and multivariate faults on the fly to observe real-time system response.
- **Containerization:**
  - Root `docker-compose.yml` orchestrating FastAPI backend and React frontend services.
  - Optimized multi-stage `Dockerfile` for backend and frontend.

### R4. Evaluation, Testing, and Reproducibility
- **Evaluation Framework (`scripts/test_anomaly_detection.py`):**
  - Automated benchmark evaluating Precision, Recall, F1-Score, False Positive Rate (FPR), and Detection Latency across all injected anomaly types.
  - Target benchmark: $\text{F1} \ge 0.80$ across all fault classes.
- **Comprehensive Test Suite (`tests/`):**
  - Unit tests: Data validation, preprocessing, feature generation, anomaly scoring, health index calculation.
  - ML tests: Model loading, inference schema compliance, score range validation ($0 \le \text{score} \le 1$).
  - Integration tests: End-to-end flow from upload/ingestion $\to$ processing $\to$ ML inference $\to$ DB persistence $\to$ API response.
  - Edge-case tests: Missing data, out-of-order timestamps, duplicates, extreme physical values, empty payloads, malformed CSV/JSON.
  - Target: $\ge 50$ test cases passing via `pytest tests/ -v`.
- **Reproducibility & Documentation:**
  - `requirements.txt`, clean setup instructions, sample dataset generator, and `docs/evaluation_report.md`.

---

## 4. 23-Phase Implementation Breakdown (Phase 0 to Phase 22)

The 23 phases defined in `TODO.md` constitute the complete sequential implementation roadmap:

| Phase # | Phase Name | Primary Objective | Granular Tasks & Deliverables | Exit Criteria |
|:---|:---|:---|:---|:---|
| **Phase 0** | **Project Initialization** | Establish reproducible foundation | Create folder structure, Python virtual environment, dependencies (`requirements.txt`), `.gitignore`, `.env.example`, `README.md`, verify backend/frontend start, configure test framework (`pytest`). | Backend starts, frontend builds/starts, test runner succeeds, repository layout verified. |
| **Phase 1** | **Data Ingestion** | Build robust data loaders & validators | Define observation schema, implement CSV/JSON/Parquet loaders, validate mandatory columns (`timestamp`, `temperature`, `pressure`, `humidity`), type checking, timestamp parsing, duplicate/missing detection, malformed record handling, generate validation report. | Clean and malformed datasets can be ingested and validated with explicit error reporting. |
| **Phase 2** | **Data Preprocessing** | Standardize data transformations | Handle missing values, normalize timestamps (regular time intervals), temporal sorting, deduplication, outlier-safe scaling/normalization, sliding window generation, strict temporal train/val/test splits, verify no data leakage. | Dataset transformed into model-ready format reproducibly with zero future-data leakage. |
| **Phase 3** | **Rule-Based Baseline** | Implement Tier 1 Deterministic QC | Physical bounds checks (T: $-40$ to $+60^\circ\text{C}$, P: $300$ to $1100\text{ hPa}$, RH: $0$ to $100\%$), rate-of-change ($\Delta T/\Delta t$, etc.), persistence/frozen checks, missing value flags, rolling statistical QC, baseline anomaly scoring & benchmark evaluation. | Tier 1 QC rules operational and baseline evaluation metrics documented. |
| **Phase 4** | **Isolation Forest** | Implement point anomaly detection | Feature engineering (scaled features + rolling mean/std + RoC), train Isolation Forest on clean temporal split, serialize model artifact, implement inference service, threshold calibration, evaluate Precision, Recall, F1, FPR. | ML model outperforms or complements Tier 1 rules; metrics logged. |
| **Phase 5** | **Temporal Model** | Implement sequence reconstruction model | Sequence windowing (e.g. 30 steps), build PyTorch Autoencoder (or GRU/LSTM Autoencoder), train on temporal baseline, calculate reconstruction error distribution, set anomaly threshold, serialize model, create inference service, test against temporal anomalies. | Temporal model produces real reconstruction errors and detects sequence violations. |
| **Phase 6** | **Multivariate Consistency** | Detect inter-sensor relationship violations | Engineer thermodynamic & cross-variable features (Clausius-Clapeyron proxy, T vs RH inverse relationship, Mahalanobis distance), train multivariate model, benchmark against synthetic multivariate anomalies. | Detects subtle compound anomalies missed by individual single-variable checks. |
| **Phase 7** | **Anomaly Fusion** | Fuse multi-tier evidence into unified score | Define scoring interfaces, normalize outputs from Tier 1–4, build weighted fusion engine, output unified `anomaly_score` ($0\text{--}1$), `confidence` ($0\text{--}1$), and `severity` (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`), calibrate thresholds to minimize false alarms. | Single unified inference output generated per observation with calibrated confidence. |
| **Phase 8** | **Fault Classification** | Classify anomaly types & distinguish genuine events | Define fault taxonomy (`SPIKE`, `DRIFT`, `FROZEN`, `DROPOUT`, `MULTIVARIATE_INCONSISTENCY`, `DATA_CORRUPTION`, `METEOROLOGICAL_EXTREME`, `UNCERTAIN_EVENT`), generate labeled injected dataset, build hybrid rule + ML classifier, evaluate classification matrix. | Accurate classification of sensor fault types vs plausible meteorological extremes. |
| **Phase 9** | **Explainability** | Generate human-interpretable reasoning | Implement SHAP (Kernel/Tree SHAP) on trained models, feature contribution scoring, rule trigger explanations, combine evidence into human-readable narrative text for operators. | Every high-severity alert includes a clear, factual explanation of contributing factors. |
| **Phase 10** | **Sensor Health** | Build continuous health scoring | Formulate multi-factor health index ($0\text{--}100$), compute rolling anomaly rate, data quality score, and drift magnitude; define status tiers (Excellent, Good, Degraded, Poor, Critical); track historical health trend. | Dynamic sensor health score updates reliably based on historical telemetry & faults. |
| **Phase 11** | **Degradation Prediction** | Forecast sensor deterioration | Analyze health trend slopes, extract degradation features, build baseline trend forecaster, generate maintenance recommendations (`stable`, `degrading`, `high_risk`, `maintenance_recommended`), document simulation assumptions. | System outputs evaluated degradation warnings prior to complete sensor failure. |
| **Phase 12** | **Correction / Imputation (Optional)** | Context-aware value estimation | Implement context window estimator for anomalous points, estimate expected value with confidence, preserve raw observation untouched, store corrected values separately. | Raw data preserved intact; valid estimated replacements generated when requested. |
| **Phase 13** | **Database** | Implement persistent relational storage | Create SQLite database schemas (`stations`, `observations`, `anomaly_events`, `sensor_health`, `model_runs`), implement repository layer with SQLAlchemy/SQLModel, write DB unit tests. | Persistent storage layer fully functional with schema migration readiness. |
| **Phase 14** | **FastAPI** | Build comprehensive REST API | Create FastAPI app, Pydantic schemas, service layer, routes for upload, observations, stations, anomalies, sensor health, model metrics, inference, and simulation triggers; add API tests. | All REST endpoints respond with correct schemas, status codes, and real ML inference. |
| **Phase 15** | **Real-Time Processing** | Streaming ingestion & live inference | Observation streaming endpoint, rolling feature buffer, real-time pipeline execution, alert triggering, DB persistence, WebSocket `/ws/live` streaming, measure inference latency ($<500\text{ ms}$). | Real-time observation ingestion streams live alerts to WebSocket clients within latency bounds. |
| **Phase 16** | **Frontend Foundation** | Set up modern React/TypeScript UI | Initialize React + TypeScript + Vite project, configure styling (Tailwind CSS), set up routing, build shared layout, API client, reusable UI components (cards, badges, charts, modal). | Clean, responsive operational dashboard shell running and communicating with backend. |
| **Phase 17** | **Dashboard** | Implement 7+ operational views | Build Overview, Live Monitoring, Alert Center, Sensor Health, Event Details, Data Explorer, Model Metrics, Interactive Anomaly Injector UI, and Explainability Viewer. | All views render real data from API with interactive anomaly injection and explanation modals. |
| **Phase 18** | **Integration** | End-to-end full-stack wiring | Connect frontend to live FastAPI endpoints and WebSocket, eliminate all mocks, verify end-to-end alert pipeline, test real-time UI updates on anomaly injection. | End-to-end flow verified: injection $\to$ real-time detection $\to$ WebSocket push $\to$ UI alert. |
| **Phase 19** | **Evaluation** | Systematic ML evaluation benchmark | Build evaluation runner `scripts/test_anomaly_detection.py`, benchmark against injected test suites (spike, drift, frozen, dropout, multivariate), measure Precision, Recall, F1 ($\ge 0.80$), FPR, latency. | Evaluation script verifies $\text{F1} \ge 0.80$ per fault class and logs complete metrics table. |
| **Phase 20** | **Edge Optimization (Optional)** | Evaluate lightweight edge execution | Profile model memory/compute footprint, evaluate quantization (TFLite/ONNX), analyze ESP32 / low-power edge computer feasibility, define edge/cloud split. | Model footprint and feasibility for low-power edge deployment documented. |
| **Phase 21** | **Final QA** | Comprehensive test execution & hardening | Run entire test suite ($\ge 50$ tests), verify clean clone setup, test edge cases (malformed input, missing fields, network blips), inspect logs and error handlers. | 100% test pass rate with $\ge 50$ tests; robust error handling on invalid inputs. |
| **Phase 22** | **Documentation** | Finalize technical documentation & release | Complete `README.md`, `ARCHITECTURE.md`, dataset guides, model training guides, API documentation, `docs/evaluation_report.md`, demo walkthrough, limitations & future work. | Complete, polished documentation enabling any developer to run the demo in $<15$ minutes. |

---

## 5. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|---|---|---|---|---|---|---|
| 1 | Simulator | Diurnal Cycle Generator | Simulates realistic 24-hour sinusoidal daily temperature and humidity curves with atmospheric tidal pressure variations | Time range, step interval, baseline $T/P/\text{RH}$, noise amplitude | Labeled continuous time-series dataframe $(t, T, P, \text{RH})$ | Raises ValueError on invalid interval or negative noise | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 2 | Simulator | Programmatic Anomaly Injection | Injects spikes, linear/exponential drift, frozen/stuck values, dropouts, noise bursts, and multivariate inconsistencies | Clean time-series, anomaly type, start/end index, magnitude | Labeled anomaly dataset with ground-truth boolean/class flags | Raises ValueError on unknown anomaly type or invalid range | `ORIGINAL_REQUEST.md`, `TODO.md` |
| 3 | Simulator | Pre-built Benchmark Scenarios | Bundles standard benchmark scenarios (Clean baseline, Single fault suites, Compound multivariate suites) | Scenario identifier, duration | Ready-to-evaluate benchmark dataset | Returns error if scenario definition not found | `ORIGINAL_REQUEST.md`, `TODO.md` |
| 4 | Ingestion | Multi-format File Ingestion | Ingests AWS observation files in CSV, JSON, and Parquet formats | File buffer / path, format type | Standardized raw observation records | Returns 400 Bad Request with detailed parsing error on malformed data | `ARCHITECTURE.md`, `TODO.md`, `AGENTS.md` |
| 5 | Ingestion | Schema & Data Validation | Validates presence of $T, P, \text{RH}$, checks data types, parses ISO-8601 timestamps, detects duplicates and missing fields | Raw observation record / batch | Validation status report (`VALID`, `INVALID`, `MALFORMED`) | Records rejection reasons in validation report | `AGENTS.md`, `TODO.md` |
| 6 | Preprocessing | Temporal Sequence Windowing | Transforms sequential tabular data into fixed sliding windows $(L=30)$ for sequence models | Clean time-series array, window size $L$, step size | 3D Tensor $(\text{samples}, L, \text{features})$ | Raises ValueError if series length $< L$ | `ARCHITECTURE.md`, `TODO.md` |
| 7 | Preprocessing | Leakage-Free Temporal Splitting | Partitions datasets chronologically into Train (early), Validation (mid), and Test (late) splits | Time-indexed dataframe, split ratios | (Train, Val, Test) datasets | Asserts strict monotonicity of timestamp indices | `AGENTS.md`, `TODO.md` |
| 8 | Tier 1 QC | Physical Plausibility Bounds | Checks if $T \in [-40, 60]^\circ\text{C}$, $P \in [300, 1100]\text{ hPa}$, $\text{RH} \in [0, 100]\%$ | Observation $(T, P, \text{RH})$ | Pass/Fail flags per variable + violation delta | Flags violation with severity `HIGH` or `CRITICAL` | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 9 | Tier 1 QC | Rate-of-Change (RoC) Check | Computes $|\Delta x/\Delta t|$ and flags unrealistic temporal jumps between consecutive readings | Current observation, previous observation, $\Delta t$ | RoC violation flags and calculated gradients | Handles variable $\Delta t$ or flags gap if $\Delta t > \text{threshold}$ | `AGENTS.md`, `ARCHITECTURE.md` |
| 10 | Tier 1 QC | Frozen/Persistence Detection | Detects stuck sensors by verifying variance over rolling $N$ steps ($\sigma^2 < \epsilon$) | Rolling window of observations | Boolean frozen flag per sensor | Requires minimum history $N$; returns uncertain if buffer unfilled | `AGENTS.md`, `TODO.md` |
| 11 | Tier 2 ML | Isolation Forest Point Anomaly | Evaluates tree isolation depth on scaled features $[T, P, \text{RH}, \text{RoC}, \text{rolling statistics}]$ | Scaled feature vector | Isolation anomaly score $\in [0, 1]$ | Handles missing features with imputation or safe fallback | `ARCHITECTURE.md`, `TODO.md` |
| 12 | Tier 2 ML | GRU/LSTM Autoencoder Temporal QC | Computes sequence reconstruction error on sliding window via trained recurrent autoencoder | Windowed sequence $(L, 3)$ | Temporal reconstruction error and anomaly score $\in [0, 1]$ | Falls back to baseline statistical score if sequence incomplete | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 13 | Tier 3 ML | Multivariate Thermodynamic Consistency | Evaluates thermodynamic cross-variable relations (Clausius-Clapeyron, Mahalanobis distance) | Multi-parameter vector $(T, P, \text{RH})$ | Multivariate inconsistency score $\in [0, 1]$ | Tolerates minor natural deviations; triggers on impossible co-occurrences | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 14 | Tier 4 ML | Fault Classifier & Extreme Discriminator | Classifies anomaly into 8 taxonomies (Spike, Drift, Frozen, Dropout, Multivariate, Corruption, Genuine Extreme, Uncertain) | Tier 1–3 feature outputs, observation context | Classification label + class probability distribution | Returns `UNCERTAIN_EVENT` when evidence is ambiguous | `AGENTS.md`, `ORIGINAL_REQUEST.md` |
| 15 | Tier 5 ML | Multi-Tier Anomaly Fusion | Combines deterministic, temporal, Isolation Forest, and multivariate evidence into unified result | Tier 1–4 output scores, weights, thresholds | Triplet: `anomaly_score` $(0\text{--}1)$, `confidence` $(0\text{--}1)$, `severity` | Employs calibrated non-linear fusion; avoids naive unweighted averaging | `ARCHITECTURE.md`, `TODO.md` |
| 16 | Tier 5 ML | SHAP & Feature Explainability | Generates feature attributions and human-readable explanation sentences justifying alert | Trained ML models, flagged observation feature vector | Attribution dict per feature + plain text explanation | Explains fallback reasons if SHAP computation times out | `GOAL.md`, `ARCHITECTURE.md` |
| 17 | Tier 5 ML | Dynamic Sensor Health Index | Computes rolling health score $(0\text{--}100)$ based on anomaly rate, fault persistence, drift, and quality | Station fault history, rolling window duration | Health score $(0\text{--}100)$, status tier, sub-scores | Defaults to 100 for brand new stations with clean data | `AGENTS.md`, `ARCHITECTURE.md` |
| 18 | Tier 5 ML | Sensor Degradation Predictor | Forecasts health trajectory and issues predictive maintenance alerts (`stable`, `degrading`, `high_risk`, `maintenance_recommended`) | Historical health timeseries | Degradation category + estimated slope + maintenance recommendation | Labels synthetic degradation predictions as simulated if synthetic | `AGENTS.md`, `TODO.md` |
| 19 | Tier 5 ML | Optional Value Reconstruction / Imputation | Reconstructs estimated true value for flagged anomalous points while preserving raw data | Historical context window, anomalous reading | Estimated $(T, P, \text{RH})$ + estimation confidence | Stores raw and corrected values in separate fields | `AGENTS.md`, `ARCHITECTURE.md` |
| 20 | Backend | Relational Persistence (SQLite) | Manages SQLite storage for stations, observations, anomaly events, sensor health, and model runs | Ingested data, inference results, metadata | Persisted relational records | Enforces unique station IDs, foreign keys, and indexes | `ARCHITECTURE.md`, `TODO.md` |
| 21 | Backend | RESTful API Layer | Exposes endpoints for data upload, observations, stations, anomalies, health, metrics, inference, and simulation | HTTP Requests (GET, POST) | JSON responses with Pydantic schema validation | Returns standardized HTTP error codes (400, 404, 422, 500) | `ARCHITECTURE.md`, `TODO.md` |
| 22 | Backend | Real-Time WebSocket Streaming | Streams live observation telemetry, anomaly events, and alert pushes to connected clients | WebSocket connection at `/ws/live` | Real-time JSON telemetry and alert frames | Handles client disconnection and reconnects gracefully | `ARCHITECTURE.md`, `TODO.md` |
| 23 | Backend | Real-Time Ingestion & Feature Buffer | Maintains rolling memory buffer per active station to enable real-time feature computation and low latency | Incoming single observation JSON | Real-time inference result | Automatically initializes buffer on first observation of station | `ARCHITECTURE.md`, `TODO.md` |
| 24 | Frontend | Overview Command Center | Displays operational summary: active stations, healthy/degraded/critical counts, active alerts, anomaly rate | API polling / WebSocket feeds | Interactive summary cards, status badges, alert counters | Shows disconnected state if backend unreachable | `ARCHITECTURE.md`, `GOAL.md` |
| 25 | Frontend | Live Multi-parameter Telemetry Monitor | Renders real-time synced charts for T, P, RH with highlighted anomaly bands and live status | Live WebSocket observation stream | Multi-axis responsive time-series charts | Buffers points smoothly without UI lag or memory leak | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 26 | Frontend | Alert Center | Searchable and filterable alert log showing severity, timestamp, station, fault classification, confidence | API alert queries | Paginated/scrollable alert table with action buttons | Displays empty state gracefully when no alerts exist | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 27 | Frontend | Sensor Health Dashboard | Visualizes station health gauge (0–100), health trend line, drift indicators, and fault breakdown | Station health API data | Gauge chart, trend graph, status badges | Highlights stations requiring maintenance | `ORIGINAL_REQUEST.md`, `ARCHITECTURE.md` |
| 28 | Frontend | Event Detail & Explainability Viewer | Modal/detail view displaying raw vs expected values, SHAP feature importance bars, and reasoning | Anomaly event ID | Visual bar chart of SHAP values, plain language summary | Handles missing explanation metadata gracefully | `ORIGINAL_REQUEST.md`, `GOAL.md` |
| 29 | Frontend | Historical Data Explorer | Allows operators to query and explore historical sensor observations and validation flags | Date range, station filter, status filter | Interactive data grid and historical chart overlay | Displays pagination controls and loading skeletons | `ARCHITECTURE.md`, `TODO.md` |
| 30 | Frontend | Interactive Anomaly Injection UI | Control panel allowing operators to inject anomalies (spike, drift, frozen, multivariate) into live stream | Anomaly type, parameter, duration, magnitude | Trigger command to simulator / backend | Displays confirmation toast and updates live chart | `ORIGINAL_REQUEST.md`, `GOAL.md` |
| 31 | Frontend | Model Performance & Metrics View | Displays model evaluation metrics (Precision, Recall, F1, FPR, latency) and confusion matrices | Evaluation metrics API | Performance tables, metric cards, confusion matrix chart | Displays timestamp and dataset version of model run | `ARCHITECTURE.md`, `TODO.md` |
| 32 | Evaluation | Systematic Anomaly Benchmark Runner | Automated benchmark script (`scripts/test_anomaly_detection.py`) testing pipeline against 5+ anomaly types | Test scenario datasets | Precision, Recall, F1, FPR, Detection Latency table | Asserts $\text{F1} \ge 0.80$; exits non-zero if target unmet | `ORIGINAL_REQUEST.md`, `TODO.md` |
| 33 | DevOps | Multi-Container Docker Orchestration | Orchestrates FastAPI backend and React frontend services in unified local environment | `docker-compose.yml`, Dockerfiles | Running backend on port 8000, frontend on port 3000/5173 | Graceful container restart and health check failure handling | `ORIGINAL_REQUEST.md`, `TODO.md` |

---

## 6. Edge Cases & Stress Scenarios

| # | Feature | Input / Condition | Expected / Observed Behavior |
|---|---|---|---|
| 1 | Ingestion / Parser | Empty CSV or JSON file (0 bytes) | Ingestion rejects payload with 400 Bad Request; logs empty payload error; no crash. |
| 2 | Ingestion / Validation | Missing mandatory column (e.g. `pressure` column omitted) | Schema validator rejects file with 422 Unprocessable Entity; specifies exact missing column name. |
| 3 | Ingestion / Validation | Out-of-order timestamps in uploaded CSV | Ingestion preprocessor sorts records chronologically by timestamp before downstream processing. |
| 4 | Ingestion / Validation | Duplicate timestamps for same station (e.g., two readings at `12:00:00Z`) | Deduplicator identifies conflict; applies configured policy (retain latest / average) and logs warning. |
| 5 | Ingestion / Validation | Non-numeric or corrupted values (e.g., `temperature: "28.4C"` or `NaN`) | Validator flags malformed record; isolates record from clean training set; returns validation report. |
| 6 | Ingestion / Validation | Extreme physical values outside atmospheric bounds ($T = 150^\circ\text{C}$, $P = 50\text{ hPa}$) | Tier 1 QC immediately flags `CRITICAL` severity physical boundary violation; prevents corruption of rolling stats. |
| 7 | Tier 1 QC | Sensor values completely frozen ($\Delta T = 0.000$, $\sigma^2 = 0$) over 20 consecutive readings | Persistence detector flags `FROZEN` fault; lowers sensor health score; triggers alert. |
| 8 | Tier 1 QC / RoC | Massive single-step spike ($T$ jumps from $22^\circ\text{C}$ to $55^\circ\text{C}$ in 1 min, then back to $22^\circ\text{C}$) | RoC check + Isolation Forest flag `SPIKE` anomaly with `HIGH`/`CRITICAL` severity; high confidence. |
| 9 | Tier 2 ML / Windowing | Incoming sequence length less than required temporal window ($N < 30$) | Temporal Autoencoder defers inference until buffer filled; Tier 1 and Tier 2 Isolation Forest provide baseline coverage. |
| 10 | Tier 3 ML | Simultaneous temperature surge and humidity saturation spike ($T = 45^\circ\text{C}$, $\text{RH} = 99\%$ in arid region) | Multivariate consistency engine detects violation of Clausius-Clapeyron / thermodynamic relationship; flags `MULTIVARIATE_INCONSISTENCY`. |
| 11 | Tier 4 Classification | Rapid cold front passage (temperature drops $12^\circ\text{C}$ in 15 min, pressure rises $4\text{ hPa}$, humidity rises consistently) | Fault classifier evaluates multivariate consistency; labels event as `METEOROLOGICAL_EXTREME` rather than sensor fault. |
| 12 | Tier 5 Health Engine | Station experiences zero anomalies over 30 days of continuous operation | Health score remains at optimal 100; degradation status reported as `stable`. |
| 13 | Tier 5 Health Engine | Station exhibits slow linear drift ($+0.05^\circ\text{C}/\text{day}$) over extended timeline | Drift detector tracks cumulative baseline deviation; health score progressively degrades from 100 down to $<50$; warns `degrading`. |
| 14 | Explainability | Feature attribution computation requested on edge-case anomaly | System extracts exact contributions (e.g., Temperature $+78\%$, RoC $+15\%$) and generates readable sentence without crashing. |
| 15 | WebSocket Streaming | Client network disconnection during live anomaly streaming | Backend handles socket disconnect without leaking memory; resumes stream upon client reconnection. |
| 16 | Real-Time Ingestion | High frequency observation ingestion ($100\text{ observations/sec}$) | Backend processes stream within buffer limits; maintains inference latency $< 500\text{ ms}$ per observation. |

---

## 7. Acceptance Criteria & Objective Verification Commands

| Verification Domain | Acceptance Criteria | Exact Verification Command | Target Result |
|:---|:---|:---|:---|
| **Test Suite** | $\ge 50$ unit, ML, and integration tests passing covering all 5 tiers, API, DB, and edge cases | `pytest tests/ -v` | All tests pass, $\ge 50$ passed, 0 failures |
| **ML Benchmark** | Precision, Recall, and F1 score $\ge 0.80$ across all fault classes (spike, frozen, drift, multivariate) | `python scripts/test_anomaly_detection.py` | $\text{F1} \ge 0.80$ printed for each fault type |
| **No-Fake Audit** | Zero hardcoded scores, mock predictions, dummy random inference, or fake SHAP values | `grep -rn "hardcoded\|FAKE\|TODO.*mock\|random\.\|0\.95\|0\.87\|0\.94" backend/app/ml/ backend/app/services/` | Returns 0 suspicious matches |
| **Backend Startup** | FastAPI application boots cleanly, mounts all routes and WebSocket endpoints | `python -m uvicorn backend.app.main:app --port 8000` | Application starts without error on `http://127.0.0.1:8000` |
| **Frontend Build** | React/TypeScript application compiles with zero TypeScript or bundling errors | `cd frontend && npm run build` | Build succeeds with 0 errors |
| **Simulator** | Generates $\ge 3$ labeled datasets (clean baseline + 2 anomaly combinations) | `python -m backend.simulator.scenarios` | Generates 3 CSV/Parquet files in `data/` |
| **Docker Orchestration**| Backend and frontend containers build and run harmoniously via Docker Compose | `docker-compose up --build -d` | Both containers healthy and accessible |
| **End-to-End Demo** | 7-step demo story executes: normal data $\to$ inject anomaly $\to$ detect $\to$ alert $\to$ explain $\to$ health score $\to$ action | Full stack execution + UI observation | Real alert with explanation and health score rendered in UI |
| **Evaluation Report** | Comprehensive report documenting models, temporal splits, metrics, and latency | Inspect `docs/evaluation_report.md` | Complete documentation matching actual run metrics |

---

## 8. Conclusion & Implementation Readiness

The specification for **SkyGuard AI** has been mined from all 5 authoritative root documents (`ORIGINAL_REQUEST.md`, `AGENTS.md`, `ARCHITECTURE.md`, `TODO.md`, `GOAL.md`). The project exhibits a crystal-clear, 23-phase sequential implementation roadmap, strict scientific constraints (only 3 core parameters, no fake functionality, temporal data splitting), a 5-tier anomaly detection hierarchy, and complete acceptance criteria.

The specifications are ready to guide architectural implementation across all phases.
