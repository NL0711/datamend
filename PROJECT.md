# Project: SkyGuard AI — Intelligent Real-Time Anomaly Detection and Sensor Health System for AWS

## Architecture Overview
SkyGuard AI is a production-grade meteorological anomaly detection, fault classification, explainability, and sensor health platform.
The architecture comprises:
1. **Simulation & Injection Engine** (`backend/simulator/`): Synthetic diurnal generator adhering to Magnus-Tetens atmospheric physics, and programmatic injection for 6 anomaly classes (`SPIKE`, `DRIFT`, `FROZEN`, `DROPOUT`, `NOISE_BURST`, `MULTIVARIATE_INCONSISTENCY`).
2. **5-Tier ML Pipeline Engine** (`backend/app/ml/`):
   - **Tier 1 (Physics QC)**: WMO range checks ($-40^\circ\text{C} \le T \le 60^\circ\text{C}$, $300 \le P \le 1100\text{ hPa}$, $0 \le RH \le 104\%$), derivative step-limits ($\Delta T/\Delta t, \Delta P/\Delta t, \Delta RH/\Delta t$), persistence/frozen check ($K=6$).
   - **Tier 2 (Point & Temporal ML)**: Standard-scaled Isolation Forest baseline and PyTorch GRU/LSTM Autoencoder ($W=30$ window, reconstruction error MSE).
   - **Tier 3 (Multivariate Thermodynamic Consistency)**: Clausius-Clapeyron dew-point physical consistency ($T_d \le T + 0.5^\circ\text{C}$) and Mahalanobis distance distribution $F_{\chi^2(3)}(D_M^2)$.
   - **Tier 4 (Fault Classification)**: Hybrid deterministic + ML classifier for 8 fault types, distinguishing genuine extreme meteorological fronts from sensor faults.
   - **Tier 5 (Sensor Health & Explainability)**: Dynamic Sensor Health Index ($\text{SHI} \in [0, 100]$) across rolling 24h window ($W=288$ steps), filtered via EMA ($\alpha=0.10$), and TreeSHAP/feature contribution explanations.
   - **Multi-Tier Fusion**: Weighted convex combination with Tier 1 hard override and model agreement variance confidence scoring.
3. **Backend & Real-Time Ingestion** (`backend/app/`): FastAPI REST API, SQLite database (`stations`, `observations`, `anomaly_events`, `sensor_health`, `model_runs`), WebSocket `/ws/live` streaming, and service layer architecture.
4. **Operational Frontend** (`frontend/`): React + TypeScript + Vite + Tailwind CSS + Lucide icons + Recharts, featuring 7 operational views (Overview, Live Monitoring, Alert Center, Sensor Health, Event Detail, Data Explorer, Interactive Anomaly Injector UI, Explainability Viewer).
5. **Testing & Benchmark Suite** (`tests/`, `scripts/`): $\ge 50$ pytest cases across all modules and `scripts/test_anomaly_detection.py` evaluating F1 $\ge 0.80$.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Diurnal Cycle Generator | Sinusoidal T, P, RH time-series generator with Magnus-Tetens thermodynamic coupling | M1 | TODO Phase 1 |
| 2 | Spike Injector | Programmatic transient multi-step spikes | M1 | TODO Phase 2 |
| 3 | Drift Injector | Programmatic linear calibration offset drift | M1 | TODO Phase 2 |
| 4 | Frozen Value Injector | Extended repeat values with zero variance | M1 | TODO Phase 2 |
| 5 | Dropout Injector | Abrupt null/zero value injection | M1 | TODO Phase 2 |
| 6 | Noise Burst Injector | High-frequency variance noise injection | M1 | TODO Phase 2 |
| 7 | Multivariate Anomaly Injector | Violates T vs RH inverse relationship | M1 | TODO Phase 2 |
| 8 | Benchmark Scenarios | Pre-configured clean and anomaly scenario runner | M1 | TODO Phase 3 |
| 9 | Dataset Exporter CLI | CLI exporting labeled train/val/test datasets | M1 | TODO Phase 4 |
| 10 | Tier 1 Physics QC | WMO physical boundaries, rate-of-change, persistence | M2 | TODO Phase 5 |
| 11 | Tier 2 Isolation Forest | Point anomaly detection on scaled features | M2 | TODO Phase 6 |
| 12 | Tier 2 GRU/LSTM Autoencoder | PyTorch temporal reconstruction error on 30-step window | M2 | TODO Phase 6 |
| 13 | Tier 3 Clausius-Clapeyron Check | Thermodynamic dew-point consistency check | M2 | TODO Phase 7 |
| 14 | Tier 3 Mahalanobis Distance | Multivariate covariance distance calculation | M2 | TODO Phase 7 |
| 15 | Multi-Tier Fusion Engine | Weighted score, confidence, severity (LOW/MED/HIGH/CRIT) | M2 | TODO Phase 8 |
| 16 | Tier 4 Fault Classifier | Classifies SPIKE, DRIFT, FROZEN, DROPOUT, MET_EXTREME, etc. | M2 | TODO Phase 9 |
| 17 | Tier 5 Sensor Health Index | 0-100 health scoring with 24h rolling EMA | M2 | TODO Phase 10 |
| 18 | Tier 5 SHAP Explainability | TreeSHAP feature contribution and human-readable reasons | M2 | TODO Phase 10 |
| 19 | SQLite Data Layer | Schema for stations, observations, anomalies, health, runs | M3 | TODO Phase 11 |
| 20 | FastAPI REST API | Endpoints for stations, observations, anomalies, health | M3 | TODO Phase 13 |
| 21 | WebSocket Streaming | Real-time `/ws/live` telemetry & inference push | M3 | TODO Phase 13 |
| 22 | Real-Time Ingestion Pipeline | End-to-end ingestion, validation, inference, persistence | M3 | TODO Phase 14 |
| 23 | Latency Profiler | Sub-500ms inference latency monitoring | M3 | TODO Phase 14 |
| 24 | Dashboard Overview View | Active stations, health status, active alerts, anomaly rate | M4 | TODO Phase 15 |
| 25 | Live Monitoring View | Multi-line charts for T, P, RH with anomaly highlight bands | M4 | TODO Phase 15 |
| 26 | Alert Center View | Filterable alert list with severity, type, confidence | M4 | TODO Phase 15 |
| 27 | Sensor Health View | 0-100 gauge, degradation trends, historical faults | M4 | TODO Phase 15 |
| 28 | Event Detail View | Raw vs expected values, SHAP explanation breakdown | M4 | TODO Phase 15 |
| 29 | Data Explorer View | Historical time-series table and export | M4 | TODO Phase 15 |
| 30 | Interactive Anomaly Injector UI | Real-time on-the-fly anomaly injection buttons | M4 | TODO Phase 16 |
| 31 | Explainability Viewer | Interactive feature contribution breakdown | M4 | TODO Phase 17 |
| 32 | Unit & Integration Test Suite | >= 50 pytest tests across all tiers, API, edge cases | M5 | TODO Phase 19 |
| 33 | Evaluation Benchmark Script | scripts/test_anomaly_detection.py achieving F1 >= 0.80 | M5 | TODO Phase 21 |
| 34 | Docker Setup & Deployment | Dockerfile.backend, Dockerfile.frontend, docker-compose | M5 | TODO Phase 22 |
| 35 | Documentation & Evaluation Report | README.md and docs/evaluation_report.md | M5 | TODO Phase 22 |

---

## Milestones
| # | Name | Scope (TODO.md Phases) | Dependencies | Status |
|---|------|------------------------|--------------|--------|
| M0 | Project Scaffolding & Config | Phase 0: Directories, dependencies, configs, test baseline | none | DONE |
| M1 | Simulator & Anomaly Injector | Phases 1–4: Diurnal generator, 6 injectors, scenarios, CLI | M0 | DONE |
| M2 | 5-Tier ML Pipeline Engine | Phases 5–10: Tier 1 QC, Tier 2 ML, Tier 3 Physics, Tier 4 Classifier, Tier 5 Health & SHAP, Fusion | M1 | DONE |
| M3 | Database & Backend Services | Phases 11, 13, 14: SQLite, FastAPI REST, WebSocket, Real-time ingestion | M2 | DONE |
| M4 | Frontend Operational Dashboard | Phases 15–18: 7 views, Recharts, Anomaly UI, Explainability UI | M3 | DONE |
| M5 | Comprehensive Testing & Docs | Phases 19, 21, 22: Tests (>=50), Benchmark (F1>=0.80), Docker, Docs | M4 | IN_PROGRESS |
| E2E | E2E Testing Track | Test harness, Tiers 1-4 test suite, publishes TEST_READY.md | M0 | DONE |

---

## Code Layout
```
c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI entrypoint
│   │   ├── config.py                   # Application settings
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes.py               # REST API endpoints
│   │   │   └── websocket.py            # WebSocket /ws/live endpoint
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── database.py             # SQLite engine & session
│   │   │   ├── models.py               # SQLAlchemy ORM models
│   │   │   └── repositories.py         # Data access layer
│   │   ├── ml/
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py             # 5-Tier ML orchestrator
│   │   │   ├── tier1_qc.py             # Deterministic quality control
│   │   │   ├── tier2_point_ml.py       # Isolation Forest point model
│   │   │   ├── tier2_temporal_ml.py    # PyTorch GRU/LSTM Autoencoder
│   │   │   ├── tier3_multivariate.py   # Thermodynamic & Mahalanobis
│   │   │   ├── tier4_classifier.py     # Fault taxonomy classifier
│   │   │   ├── tier5_health.py         # Sensor Health Index (0-100)
│   │   │   ├── tier5_explain.py        # SHAP explainability
│   │   │   ├── fusion.py               # Multi-tier score fusion
│   │   │   └── preprocessor.py         # Feature engineering & scaling
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── ingestion_service.py    # Real-time ingestion engine
│   │       ├── simulation_service.py   # Live simulation controller
│   │       └── analytics_service.py    # Aggregation & metrics service
│   └── simulator/
│       ├── __init__.py
│       ├── diurnal_generator.py        # Sinusoidal diurnal cycles
│       ├── anomaly_injector.py         # 6 anomaly injection functions
│       ├── scenarios.py                # Pre-built benchmark scenarios
│       └── cli.py                      # Dataset generator CLI
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── types/
│       │   └── index.ts                # TypeScript data interfaces
│       ├── services/
│       │   ├── api.ts                  # REST API client
│       │   └── websocket.ts            # WebSocket streaming client
│       └── components/
│           ├── OverviewView.tsx
│           ├── LiveMonitoringView.tsx
│           ├── AlertCenterView.tsx
│           ├── SensorHealthView.tsx
│           ├── EventDetailView.tsx
│           ├── DataExplorerView.tsx
│           ├── AnomalyInjectorUI.tsx
│           └── ExplainabilityViewer.tsx
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_simulator.py
│   ├── test_tier1_qc.py
│   ├── test_tier2_ml.py
│   ├── test_tier3_multivariate.py
│   ├── test_tier4_classifier.py
│   ├── test_tier5_health_explain.py
│   ├── test_fusion.py
│   ├── test_api.py
│   ├── test_ingestion.py
│   └── test_edge_cases.py
├── scripts/
│   ├── generate_datasets.py            # Generates train/val/test datasets
│   ├── train_models.py                 # Trains IForest & Autoencoder
│   └── test_anomaly_detection.py       # Benchmark script (F1 >= 0.80)
├── data/
│   ├── baseline_clean.csv
│   ├── train_clean.csv
│   ├── val_mixed.csv
│   └── test_anomalies.csv
├── docs/
│   └── evaluation_report.md
├── requirements.txt
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
└── README.md
```

---

## Interface Contracts

### Ingestion Observation Schema (JSON / DB)
```json
{
  "timestamp": "2026-08-24T10:00:00Z",
  "station_id": "AWS-001",
  "temperature": 24.5,
  "pressure": 1013.25,
  "humidity": 65.0,
  "latitude": 28.6139,
  "longitude": 77.2090,
  "elevation": 216.0
}
```

### Pipeline Inference Output Contract (`InferenceResult`)
```json
{
  "timestamp": "2026-08-24T10:00:00Z",
  "station_id": "AWS-001",
  "is_anomaly": true,
  "anomaly_score": 0.88,
  "confidence": 0.92,
  "severity": "HIGH",
  "classification": "SPIKE",
  "explanation": {
    "summary": "Sudden unrealistic temperature increase of 28.5°C within 5 minutes.",
    "contributing_features": [
      {"feature": "temperature_delta", "attribution": 0.65},
      {"feature": "temperature", "attribution": 0.25},
      {"feature": "relative_humidity", "attribution": 0.10}
    ]
  },
  "tier_scores": {
    "tier1_qc_flag": true,
    "tier2_point_score": 0.85,
    "tier2_temporal_score": 0.91,
    "tier3_multivariate_score": 0.78
  },
  "sensor_health": 45.0,
  "recommended_action": "Inspect temperature sensor probe for loose wiring or power glitch."
}
```
