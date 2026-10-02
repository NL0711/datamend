# Changes Implemented for Milestone 3 (Database, Backend Services & Real-time WebSocket)

**Agent**: `m3_worker_1`  
**Date**: 2026-08-24  
**Scope**: Database, Async Repositories, Pydantic Schemas, Real-time Ingestion, Simulator, Analytics, WebSocket live streaming, REST Routes, Lifespan Lifecycle, and Integration Tests.

---

## 1. Database Architecture & Lifecycle (`backend/app/db/`)
- **`backend/app/db/database.py`**:
  - Implemented async SQLite engine using `SQLAlchemy 2.0` and `aiosqlite`.
  - Configured high-concurrency PRAGMAs on connection: `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, `PRAGMA foreign_keys=ON;`, `PRAGMA busy_timeout=10000;`.
  - Configured `async_sessionmaker` with `autocommit=False, autoflush=False, expire_on_commit=False`.
  - Provided `get_db()` async generator dependency for FastAPI endpoints.
  - Provided `get_db_context()` async context manager for background workers and services.
  - Implemented `init_db()` creating all tables and automatically seeding 4 default regional AWS stations (`AWS-001` through `AWS-004`).
  - Implemented `close_db()` disposing engine connection pool gracefully.

- **`backend/app/db/models.py`**:
  - Implemented 5 declarative SQLAlchemy 2.0 ORM models:
    1. `Station`: AWS station metadata, status (`ACTIVE`, `DEGRADED`, `CRITICAL`, `OFFLINE`), relationships to observations, health, anomalies.
    2. `Observation`: Raw time-series telemetry (`station_id`, `timestamp`, `temperature`, `pressure`, `humidity`, `validation_status`), with composite index on `(station_id, timestamp)`.
    3. `AnomalyEvent`: AI-detected anomalies, fault classifications, `is_fault` boolean, `anomaly_score`, `confidence`, `severity`, native JSON `explanation` (TreeSHAP) and `tier_scores`, composite indexes on `(station_id, timestamp)` and `(station_id, severity)`.
    4. `SensorHealth`: Dynamic Sensor Health Index (0–100), degradation risk (`STABLE`, `DEGRADING`, `HIGH_RISK`, `MAINTENANCE_REQUIRED`), TTF, recommended action.
    5. `ModelRun`: Hyperparameters, evaluation metrics, and dataset versions.

- **`backend/app/db/repositories.py`**:
  - Implemented 5 async repositories:
    1. `StationRepository`: CRUD, `get_or_create`, `update_status`, `delete`, `get_fleet_summary`.
    2. `ObservationRepository`: `create`, `create_batch`, `get_latest`, `get_history`, `get_recent_window(window_size=30)`, `get_paginated`, `count`.
    3. `AnomalyRepository`: `create`, `create_batch`, `get_recent`, `get_paginated`, `get_active_alerts`, `get_stats` (severity, classification, hardware fault vs convective front breakdowns).
    4. `HealthRepository`: `create`, `get_latest`, `get_all_latest`, `get_history`, `get_fleet_health_summary`.
    5. `ModelRunRepository`: `create`, `get_latest`, `get_all`, `update_metrics`.

---

## 2. Pydantic v2 Schemas (`backend/app/schemas/`)
- **`backend/app/schemas/schemas.py` & `backend/app/schemas/__init__.py`**:
  - Telemetry: `ObservationBase`, `ObservationCreate`, `ObservationResponse`, `ObservationListResponse`.
  - ML & Explainability: `FeatureAttributionSchema`, `ExplanationResultSchema`, `TierScoresSchema`, `InferenceResultSchema`, `ObservationIngestResponse`.
  - Anomaly Events: `AnomalyEventResponse`, `AnomalyEventDetailResponse`, `AnomalyEventListResponse`, `AnomalyStatsResponse`.
  - Stations: `StationCreate`, `StationUpdate`, `StationResponse`, `StationDetailResponse`, `StationListResponse`.
  - Sensor Health: `SensorHealthRecord`, `StationHealthDetailResponse`, `FleetHealthSummaryResponse`.
  - Simulation: `SimulationStartRequest`, `AnomalyInjectRequest`, `SimulationStatusResponse`, `AnomalyInjectResponse`.
  - Batch CSV Upload: `UploadRowError`, `UploadSummaryResponse`.
  - Metrics: `MetricsResponse`, `InferenceRequest`.

---

## 3. Real-Time Ingestion, Simulation & Analytics Services (`backend/app/services/`)
- **`backend/app/services/ingestion_service.py`**:
  - Encapsulates `SkyGuardPipeline` 5-tier ML engine with per-station `asyncio.Lock` serialization to ensure time-series buffer continuity.
  - Offloads CPU-bound PyTorch and TreeSHAP inference to worker threads via `asyncio.to_thread`.
  - Persists observations, anomaly events, sensor health records, and station statuses asynchronously.
  - Broadcasts live observation telemetry and critical alerts via `ws_manager`.
  - Measures execution latency per observation and logs rolling percentiles.
  - Implemented `process_csv_upload` with header normalization, column validation, chronological sorting, and chunked database persistence.

- **`backend/app/services/simulation_service.py`**:
  - Multi-station background simulator powered by `DiurnalGenerator` with 4 microclimate presets (`subtropical_delhi`, `temperate_marine`, `high_altitude_plateau`, `arid_desert`).
  - Interactive on-the-fly anomaly injector supporting `SPIKE`, `DRIFT`, `FROZEN`, `DROPOUT`, `NOISE_BURST`, `MULTIVARIATE_INCONSISTENCY`, `METEOROLOGICAL_EXTREME`, `DATA_CORRUPTION`.
  - Background `asyncio.Task` generation loop with configurable interval, start, stop, and status querying.

- **`backend/app/services/analytics_service.py`**:
  - Rolling execution latency tracking (`deque` maxlen=1000) computing `avg`, `p50`, `p95`, `p99`, `max`.
  - Aggregates fleet status, station health summaries, and system operational metrics.

---

## 4. API & WebSocket Layer (`backend/app/api/`, `backend/app/main.py`)
- **`backend/app/api/websocket.py`**:
  - `ConnectionManager`: Active connection tracking with station-specific subscription filtering (`{"*"}`, `{"AWS-001"}`, etc.), heartbeat pong, safe concurrent broadcast with 1.5s timeout and dead-client cleanup.
  - `/ws/live` bi-directional WebSocket route handling client subscribe, unsubscribe, ping, and anomaly injection commands.

- **`backend/app/api/routes.py`**:
  - Implemented full REST endpoints:
    - `/api/stations` (`GET`, `POST`, `GET /{id}`, `DELETE /{id}`)
    - `/api/observations` (`POST`, `POST /batch`, `GET`)
    - `/api/anomalies` (`GET`, `GET /{id}`, `GET /alerts/active`, `GET /stats/summary`)
    - `/api/health` (`GET`, `GET /{station_id}`)
    - `/api/simulate` (`POST /start`, `POST /stop`, `POST /inject`, `GET /status`)
    - `/api/upload` (`POST`)
    - `/api/metrics` (`GET`)
    - `/api/infer` (`POST`)

- **`backend/app/main.py`**:
  - FastAPI lifespan startup initializing database schema and seeding default stations.
  - Shutdown cleanup stopping simulation tasks and disposing database pool.
  - Configured CORS middleware and mounted routers.

---

## 5. Test Suite (`tests/`)
- **`tests/conftest.py`**:
  - Added `initialize_test_database` autouse fixture ensuring clean tables and default stations.
- **`tests/test_api.py`**:
  - 18 comprehensive tests covering root metadata, stations CRUD/400/404, observation ingestion (nominal, spike, bounds violation, 422 malformed), pagination, anomaly filters, alert stats, health detail/404, simulation lifecycle (start, inject, stop), metrics, and ad-hoc inference.
- **`tests/test_ingestion.py`**:
  - 12 comprehensive tests covering clean CSV upload, injected anomaly CSV upload, empty CSV 400, missing column 400, non-CSV 400, corrupt data row error collection, timestamp sorting, frozen sensor decay, convective front disambiguation, 20 concurrent observation ingestions, latency profiling under 500ms budget, and WebSocket broadcast resilience.
