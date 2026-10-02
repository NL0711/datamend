# SkyGuard AI — Workspace & Repository Baseline Survey Report

**Author**: `survey_explorer_1` (Teamwork Explorer / Investigator)  
**Date**: 2026-08-24  
**Workspace Root**: `c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard`  
**Agent Working Directory**: `c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\.agents\survey_explorer_1`

---

## 1. Executive Summary

A comprehensive investigation of the workspace `c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard` was conducted.

### Core Survey Result
- **Current State**: The repository is in a **pure specification baseline** state (Phase 0 not yet started).
- **Existing Files**: 5 authoritative specification markdown files exist at the workspace root, along with the `.agents/` directory containing agent metadata and coordination logs.
- **Code / Implementation**: **0% implementation code exists**. There are currently no Python scripts, backend code, ML models, React/Node frontend code, test suites, configuration files, virtual environments, or data assets.
- **Immediate Requirement**: Full implementation must be scaffolded and built from scratch following the 23 sequential phases defined in `TODO.md` and governed by `AGENTS.md`, `ARCHITECTURE.md`, `GOAL.md`, and `ORIGINAL_REQUEST.md`.

---

## 2. Inventory of Existing Files

| File Path | Size (Bytes) | Category | Description & Purpose |
|:---|:---|:---|:---|
| `AGENTS.md` | 12,985 | Governance / Rules | Behavioral rules for software engineering agents; strict "NO fake functionality" policy; constraints on core inputs (T, P, RH only), evaluation criteria, temporal splitting, and phase discipline. |
| `ARCHITECTURE.md` | 11,242 | Architecture | Full system architecture specification; 5-tier ML pipeline; SQLite database schema (5 tables); FastAPI backend structure; React/TypeScript frontend architecture; deployment and edge considerations. |
| `GOAL.md` | 5,634 | Objectives & Success Criteria | Defines core product questions, 7-step demo story, 13-point success criteria checklist, operational vision, and non-goals. |
| `ORIGINAL_REQUEST.md` | 13,268 | Requirements & References | High-level system requirements (R1–R4), reference repositories (expanso-io, miksrv, HVAC-Maintenance, cryologger, ITU TinyML), acceptance criteria, and verification methods. |
| `TODO.md` | 9,482 | Execution Roadmap | 23-phase sequential implementation roadmap (Phase 0 to Phase 22) with granular tasks and explicit exit criteria for each phase. |
| `.agents/` | Directory | Coordination Metadata | Multi-agent coordination directory containing metadata, briefings, dispatches, and progress logs for orchestrator and surveyor subagents. |

*Note: No other files or directories exist in the workspace.*

---

## 3. Detailed Gap Analysis: Existing vs. Required Structure

The entire production system needs to be created from scratch. Below is the comprehensive gap analysis mapping required directories and modules against current presence:

```
skyguard/ (Workspace Root)
├── .agents/                          [EXISTS - metadata only]
├── AGENTS.md                         [EXISTS]
├── ARCHITECTURE.md                   [EXISTS]
├── GOAL.md                           [EXISTS]
├── ORIGINAL_REQUEST.md               [EXISTS]
├── TODO.md                           [EXISTS]
├── README.md                         [MISSING - To create in Phase 0/22]
├── .gitignore                        [MISSING - To create in Phase 0]
├── .env.example                      [MISSING - To create in Phase 0]
├── requirements.txt                  [MISSING - To create in Phase 0]
├── docker-compose.yml                [MISSING - To create in Phase 0/22]
│
├── backend/                          [MISSING - Entire backend tree to create]
│   ├── Dockerfile                    [MISSING]
│   ├── app/
│   │   ├── __init__.py               [MISSING]
│   │   ├── main.py                   [MISSING - FastAPI entrypoint & WebSocket /ws/live]
│   │   ├── core/                     [MISSING - Config, logging, constants]
│   │   ├── db/                       [MISSING - SQLite engine, session, Base]
│   │   ├── models/                   [MISSING - SQLAlchemy/SQLModel database entities]
│   │   │   ├── station.py
│   │   │   ├── observation.py
│   │   │   ├── anomaly_event.py
│   │   │   ├── sensor_health.py
│   │   │   └── model_run.py
│   │   ├── schemas/                  [MISSING - Pydantic DTO schemas]
│   │   │   ├── observation.py
│   │   │   ├── anomaly.py
│   │   │   ├── health.py
│   │   │   └── station.py
│   │   ├── api/                      [MISSING - REST API Route Handlers]
│   │   │   ├── routes_upload.py
│   │   │   ├── routes_observations.py
│   │   │   ├── routes_stations.py
│   │   │   ├── routes_anomalies.py
│   │   │   ├── routes_health.py
│   │   │   ├── routes_metrics.py
│   │   │   └── routes_inference.py
│   │   └── services/                 [MISSING - Core business logic services]
│   │       ├── ingestion_service.py
│   │       ├── validation_service.py
│   │       ├── pipeline_service.py
│   │       ├── health_service.py
│   │       └── websocket_service.py
│   │
│   ├── ml/                           [MISSING - 5-Tier ML Engine]
│   │   ├── __init__.py
│   │   ├── preprocessing/            [MISSING - Scaling, missing handling, temporal splitting]
│   │   ├── features/                 [MISSING - Diurnal, rolling stats, physical delta]
│   │   ├── baselines/                [MISSING - Tier 1 Physical Bounds, Persistence, Rate of Change]
│   │   ├── models/                   [MISSING - Tier 2 Isolation Forest, Autoencoder/GRU]
│   │   ├── multivariate/             [MISSING - Tier 3 Cross-variable consistency, Mahalanobis]
│   │   ├── classification/           [MISSING - Tier 4 8-Class Fault Classifier]
│   │   ├── fusion/                   [MISSING - Multi-tier score fusion engine]
│   │   ├── explainability/           [MISSING - Tier 5 SHAP & Feature Contribution breakdown]
│   │   └── health/                   [MISSING - Sensor health index & degradation predictor]
│   │
│   ├── simulator/                    [MISSING - Data Generator & Anomaly Injector]
│   │   ├── __init__.py
│   │   ├── diurnal_generator.py      [MISSING - Diurnal cycle physics generator]
│   │   ├── anomaly_injector.py       [MISSING - Spike, Drift, Frozen, Dropout, Corruption injection]
│   │   └── scenarios.py              [MISSING - Benchmark & demo test scenarios]
│   │
│   ├── data/                         [MISSING - Datasets storage]
│   │   ├── raw/
│   │   ├── synthetic/
│   │   └── processed/
│   │
│   └── saved_models/                 [MISSING - Model artifacts, scalers, weights, metadata]
│
├── frontend/                         [MISSING - Entire React/TypeScript tree to create]
│   ├── Dockerfile                    [MISSING]
│   ├── package.json                  [MISSING]
│   ├── tsconfig.json                 [MISSING]
│   ├── vite.config.ts                [MISSING]
│   ├── index.html                    [MISSING]
│   └── src/
│       ├── api/                      [MISSING - Axios/Fetch REST & WebSocket client]
│       ├── components/               [MISSING - Header, Sidebar, AlertBadge, MetricCard]
│       ├── charts/                   [MISSING - Recharts / Chart.js real-time sensor graphs]
│       ├── pages/                    [MISSING - 7 Core Operational Views]
│       │   ├── Overview.tsx
│       │   ├── LiveMonitoring.tsx
│       │   ├── AlertCenter.tsx
│       │   ├── SensorHealth.tsx
│       │   ├── EventDetail.tsx
│       │   ├── DataExplorer.tsx
│       │   └── ModelPerformance.tsx
│       ├── AnomalyInjectorUI/        [MISSING - Interactive on-the-fly anomaly trigger panel]
│       ├── ExplainabilityViewer/     [MISSING - Visual SHAP / feature contribution cards]
│       ├── types/                    [MISSING - TypeScript data interfaces]
│       └── utils/                    [MISSING - Formatting, time helpers]
│
├── tests/                            [MISSING - Test Suite (Target: >= 50 tests)]
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/                         [MISSING - Validation, preprocessing, feature engine, health]
│   ├── ml/                           [MISSING - Model loading, score bounds, SHAP consistency]
│   ├── integration/                  [MISSING - Ingestion -> DB -> ML -> API -> WebSocket]
│   └── edge_cases/                   [MISSING - Corrupted CSV, nulls, frozen values, extremes]
│
├── scripts/                          [MISSING - Executable utility scripts]
│   ├── test_anomaly_detection.py     [MISSING - Benchmark script verifying F1 >= 0.80]
│   ├── train_models.py               [MISSING - End-to-end model training script]
│   ├── generate_datasets.py          [MISSING - Dataset generation script]
│   └── run_demo.py                   [MISSING - Automated demo verification script]
│
└── docs/                             [MISSING - Technical documentation]
    ├── evaluation_report.md          [MISSING - Model metrics, F1, latency, limitations]
    ├── architecture_overview.md      [MISSING]
    └── api_reference.md              [MISSING]
```

---

## 4. Key Constraints & Non-Negotiable Specifications

From inspection of `AGENTS.md`, `ARCHITECTURE.md`, `GOAL.md`, `ORIGINAL_REQUEST.md`, and `TODO.md`:

1. **Input Variable Constraint**:
   - The core anomaly detection system **must only depend on 3 primary variables**:
     1. Temperature (°C)
     2. Atmospheric Pressure (hPa)
     3. Relative Humidity (%)
   - Optional metadata: `timestamp`, `station_id`, `latitude`, `longitude`, `elevation`.
   - Never make additional external sensor channels mandatory.

2. **No-Fake Functionality Mandate**:
   - Never hardcode anomaly scores (e.g. `0.94`, `0.87`), confidence numbers, or sensor health scores.
   - Never return fake SHAP values — SHAP values must be computed dynamically using real trained models and change when input data changes.
   - Never mock APIs or claim real-time streaming when data is static.
   - Never claim model accuracy without reproducible empirical evaluation.

3. **Data Splitting & Leakage Prevention**:
   - Temporal train/validation/test splits (earlier time -> train, intermediate -> val, future -> test).
   - Strict prohibition on random `train_test_split` to avoid temporal data leakage.

4. **Raw vs. Corrected Data Invariance**:
   - Never overwrite or mutate raw incoming observations in the database.
   - Corrected/imputed values must be stored alongside raw values with imputation confidence and method.

5. **Layered 5-Tier ML Hierarchy**:
   - **Tier 1**: Deterministic quality control (physical bounds, rate-of-change, persistence/frozen checks).
   - **Tier 2**: Statistical & Point/Temporal ML (Isolation Forest, Autoencoder/GRU).
   - **Tier 3**: Multivariate Consistency (cross-variable physics, Mahalanobis distance).
   - **Tier 4**: Fault Classification (8 classes: SPIKE, DROPOUT, FROZEN, DRIFT, MULTIVARIATE_INCONSISTENCY, DATA_CORRUPTION, METEOROLOGICAL_EXTREME, UNCERTAIN_EVENT).
   - **Tier 5**: Sensor Health (0–100 index), Degradation Prediction & Explainability (SHAP / feature contribution).

6. **Target Verification Metrics**:
   - Automated test suite: `pytest tests/ -v` passing with **≥ 50 test cases**.
   - ML benchmark: `python scripts/test_anomaly_detection.py` achieving **F1 score ≥ 0.80** across fault types.
   - Full pipeline inference latency: **< 500ms** per observation.
   - Frontend: `npm run build` passing cleanly with 7 distinct operational views.

---

## 5. Technical Stack Plan & Dependencies

To execute Phase 0 and establish the foundation, the following technical dependencies are identified:

### Backend & ML Stack (Python)
- **Framework**: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`
- **Database / ORM**: `sqlite3` (built-in), `sqlalchemy`, `alembic` (optional)
- **Data & Numerical Processing**: `numpy`, `pandas`, `scipy`
- **Machine Learning & Stats**: `scikit-learn`, `torch` (lightweight CPU build for temporal autoencoder / GRU), `shap`
- **Real-Time / Networking**: `websockets`, `httpx`
- **Testing & Quality**: `pytest`, `pytest-asyncio`, `pytest-cov`, `flake8`

### Frontend Stack (Node / TypeScript)
- **Framework / Bundler**: `react` (v18+), `react-dom`, `vite`, `typescript`
- **Routing**: `react-router-dom`
- **UI / Styling**: `tailwindcss` / `lucide-react` / modern CSS modules
- **Charts / Visualizations**: `recharts` or `chart.js` + `react-chartjs-2`
- **HTTP & WebSocket**: `axios` + native browser WebSocket API

---

## 6. Recommended Execution Strategy for Orchestrator

To fulfill the 23 phases of `TODO.md` cleanly without risking complexity explosion:

1. **Phase 0 — Project Initialization (Immediate Next Step)**:
   - Scaffold workspace directories (`backend/`, `frontend/`, `tests/`, `scripts/`, `docs/`, `data/`).
   - Create root configuration files: `requirements.txt`, `.gitignore`, `.env.example`, `README.md`.
   - Set up test scaffolding (`conftest.py`, basic sanity tests) and verify `pytest` execution.
2. **Phase 1 to 4 — Ingestion, Preprocessing & Baselines**:
   - Implement `backend/simulator/` (diurnal physics generator + anomaly injector).
   - Implement data validation engine (Tier 1 deterministic quality control).
   - Implement Tier 2 Isolation Forest baseline with temporal data splitting.
3. **Phase 5 to 10 — Advanced ML Pipeline, Classification, Explainability & Health**:
   - Train Temporal Autoencoder & Multivariate consistency modules.
   - Implement Anomaly Fusion engine combining all tiers into `(anomaly_score, confidence, severity)`.
   - Implement Fault Classifier (8 fault types) + SHAP explainability generator + Sensor Health Index (0-100).
4. **Phase 11 to 15 — SQLite Database, FastAPI Backend & Real-Time Engine**:
   - Create SQLite models, repositories, and migration/initialization scripts.
   - Build REST API endpoints and WebSocket `/ws/live` streaming pipeline.
5. **Phase 16 to 18 — Operational React Dashboard**:
   - Build 7 operational dashboard views + Anomaly Injector UI + Explainability Viewer.
   - Connect frontend directly to FastAPI WebSocket and REST APIs.
6. **Phase 19 to 22 — Evaluation, QA & Documentation**:
   - Run `scripts/test_anomaly_detection.py` to benchmark F1 ≥ 0.80.
   - Run full pytest test suite (≥ 50 test cases).
   - Generate `docs/evaluation_report.md`, Docker setup, and developer quickstart docs.
