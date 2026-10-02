# SkyGuard AI — Milestone 3 Technical Analysis Report: REST API & Ingestion Tests

**Agent**: `m3_explorer_3`  
**Milestone**: M3 — Database, Backend Services, REST API & Ingestion Tests (Phases 11, 13, 14, 15)  
**Date**: 2026-08-24  
**Target System**: SkyGuard AI Real-Time Anomaly Detection & Sensor Health Platform  

---

## 1. Executive Summary

Milestone 3 bridges the 5-Tier Machine Learning Engine (Milestone 2) and the Operational Frontend Dashboard (Milestone 4). It transforms the standalone Python ML inference pipeline into a production-grade, asynchronous, transactional backend system.

This report provides the comprehensive architecture, OpenAPI route contracts, Pydantic v2 schema definitions, CSV batch upload pipeline design, and an exhaustive pytest test suite specification for:
1. **REST API Routes** (`backend/app/api/routes.py` & `backend/app/main.py`)
2. **Pydantic Schemas** (`backend/app/schemas/schemas.py`)
3. **CSV Batch Upload Ingestion Service** (`backend/app/services/ingestion_service.py`)
4. **Test Suite Coverage** (`tests/test_api.py` and `tests/test_ingestion.py`)

---

## 2. REST API Endpoints Specification

All endpoints are prefixed with `/api` and adhere to RESTful conventions, JSON response structures, standard HTTP status codes, and FastAPI OpenAPI documentation tags.

```
                                  FASTAPI APPLICATION (/api)
                                              │
    ┌──────────────┬──────────────┬───────────┴───┬──────────────┬──────────────┬─────────────┐
    ▼              ▼              ▼               ▼              ▼              ▼             ▼
/stations    /observations    /anomalies       /health       /simulate       /upload       /metrics & /infer
```

### 2.1 Station Management Endpoints (`/api/stations`)

| Method | Path | Summary | Query / Body Params | Status Codes | Response Schema |
|---|---|---|---|---|---|
| `GET` | `/api/stations` | List all registered AWS stations with current health & metadata | `status: Optional[str]`, `limit: int = 100`, `offset: int = 0` | `200 OK` | `StationListResponse` |
| `POST` | `/api/stations` | Register a new AWS station | `StationCreate` JSON payload | `201 Created`, `400 Bad Request`, `422 Unprocessable` | `StationResponse` |
| `GET` | `/api/stations/{station_id}` | Retrieve station detail, active status, coordinates, latest health | `station_id: str` (path) | `200 OK`, `404 Not Found` | `StationDetailResponse` |
| `DELETE`| `/api/stations/{station_id}` | Deactivate/remove a station (optional) | `station_id: str` (path) | `200 OK`, `404 Not Found` | `Dict[str, str]` |

### 2.2 Observation Endpoints (`/api/observations`)

| Method | Path | Summary | Query / Body Params | Status Codes | Response Schema |
|---|---|---|---|---|---|
| `POST` | `/api/observations` | Ingest single real-time observation, run full 5-tier inference, persist observation & anomaly, broadcast to WebSocket | `ObservationCreate` JSON payload | `201 Created`, `422 Unprocessable` | `ObservationIngestResponse` |
| `GET` | `/api/observations` | Query historical time-series observations with range filters & pagination | `station_id: Optional[str]`, `start_time: Optional[datetime]`, `end_time: Optional[datetime]`, `limit: int = 100`, `offset: int = 0`, `order: str = "desc"` | `200 OK` | `ObservationListResponse` |

### 2.3 Anomaly Event Endpoints (`/api/anomalies`)

| Method | Path | Summary | Query / Body Params | Status Codes | Response Schema |
|---|---|---|---|---|---|
| `GET` | `/api/anomalies` | Query detected anomalies with operational filters (severity, fault class, weather extreme) | `station_id: Optional[str]`, `severity: Optional[str]`, `classification: Optional[str]`, `is_fault: Optional[bool]`, `start_time: Optional[datetime]`, `end_time: Optional[datetime]`, `min_score: float = 0.0`, `limit: int = 50`, `offset: int = 0` | `200 OK` | `AnomalyEventListResponse` |
| `GET` | `/api/anomalies/{anomaly_id}` | Retrieve comprehensive diagnostic explanation, TreeSHAP attributions, tier scores, and recommended operator action | `anomaly_id: int` (path) | `200 OK`, `404 Not Found` | `AnomalyEventDetailResponse` |

### 2.4 Sensor Health & Fleet Overview Endpoints (`/api/health`)

| Method | Path | Summary | Query / Body Params | Status Codes | Response Schema |
|---|---|---|---|---|---|
| `GET` | `/api/health` | System liveness & fleet health overview (healthy, degraded, critical station counts) | None | `200 OK` | `FleetHealthSummaryResponse` |
| `GET` | `/api/health/{station_id}` | Station-specific sensor health index (0–100), degradation risk, estimated hours to failure, historical trend | `station_id: str` (path), `limit: int = 100` | `200 OK`, `404 Not Found` | `StationHealthDetailResponse` |

### 2.5 Simulation Control Endpoints (`/api/simulate`)

| Method | Path | Summary | Query / Body Params | Status Codes | Response Schema |
|---|---|---|---|---|---|
| `POST` | `/api/simulate/start` | Launch synthetic diurnal AWS stream in background asyncio task | `SimulationStartRequest` (`station_id`, `interval_seconds`, `noise_level`, `scenario`) | `200 OK`, `400 Bad Request` | `SimulationStatusResponse` |
| `POST` | `/api/simulate/stop` | Stop active simulation stream | None | `200 OK` | `SimulationStatusResponse` |
| `POST` | `/api/simulate/inject` | Trigger dynamic on-the-fly anomaly injection into live simulation | `AnomalyInjectRequest` (`anomaly_type`, `magnitude`, `duration_steps`, `parameter`) | `200 OK`, `400 Bad Request`, `422 Unprocessable` | `AnomalyInjectResponse` |
| `GET` | `/api/simulate/status` | Query current simulation engine status | None | `200 OK` | `SimulationStatusResponse` |

### 2.6 Batch CSV Ingestion Endpoint (`/api/upload`)

| Method | Path | Summary | Query / Body Params | Status Codes | Response Schema |
|---|---|---|---|---|---|
| `POST` | `/api/upload` | Upload CSV dataset, validate headers/types, sort chronologically, run sequential 5-tier ML pipeline, persist records, update health, return execution summary | `file: UploadFile = File(...)`, `station_id: Optional[str] = Form(None)`, `reset_state: bool = Form(False)` | `200 OK`, `400 Bad Request`, `422 Unprocessable`, `500 Internal Error` | `UploadSummaryResponse` |

### 2.7 System & ML Analytics Metrics Endpoint (`/api/metrics`)

| Method | Path | Summary | Query / Body Params | Status Codes | Response Schema |
|---|---|---|---|---|---|
| `GET` | `/api/metrics` | Return aggregated ML performance metrics, anomaly distribution, inference latency percentiles (P50/P95/P99), station health breakdown | `station_id: Optional[str] = None`, `window_hours: int = 24` | `200 OK` | `MetricsResponse` |

### 2.8 Ad-Hoc Inference Endpoint (`/api/infer`)

| Method | Path | Summary | Query / Body Params | Status Codes | Response Schema |
|---|---|---|---|---|---|
| `POST` | `/api/infer` | Execute immediate 5-tier ML inference on raw observation payload without mandatory DB persistence | `InferenceRequest` (`timestamp`, `station_id`, `temperature`, `pressure`, `humidity`, `persist: bool = False`) | `200 OK`, `422 Unprocessable` | `InferenceResultSchema` |

---

## 3. Pydantic Request & Response Schemas Architecture

Schemas must be organized under `backend/app/schemas/schemas.py` using Pydantic v2 conventions (`model_config = ConfigDict(from_attributes=True)`).

```python
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

# --- Core Telemetry Schemas ---

class ObservationBase(BaseModel):
    timestamp: Union[datetime, str] = Field(..., description="Observation timestamp (ISO 8601 or string)")
    station_id: str = Field(..., min_length=1, max_length=64, description="AWS Station identifier")
    temperature: float = Field(..., ge=-100.0, le=100.0, description="Temperature in Celsius")
    pressure: float = Field(..., ge=100.0, le=1500.0, description="Atmospheric pressure in hPa")
    humidity: float = Field(..., ge=-20.0, le=150.0, description="Relative humidity in %")
    latitude: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Station latitude")
    longitude: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Station longitude")
    elevation: Optional[float] = Field(None, ge=-500.0, le=9000.0, description="Station elevation in meters")

class ObservationCreate(ObservationBase):
    pass

class ObservationResponse(BaseModel):
    id: int
    station_id: str
    timestamp: datetime
    temperature: float
    pressure: float
    humidity: float
    validation_status: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ObservationListResponse(BaseModel):
    items: List[ObservationResponse]
    total: int
    limit: int
    offset: int

# --- ML & Explainability Schemas ---

class FeatureAttributionSchema(BaseModel):
    feature: str = Field(..., description="Feature name (e.g. temperature_delta)")
    attribution: float = Field(..., description="TreeSHAP attribution weight")
    raw_value: Optional[float] = Field(None, description="Observed feature value")
    description: Optional[str] = Field(None, description="Operator-friendly feature description")

class ExplanationResultSchema(BaseModel):
    summary: str = Field(..., description="Human-readable root cause explanation")
    contributing_features: List[FeatureAttributionSchema] = Field(default_factory=list)
    method: str = Field("TreeSHAP", description="Explainability method")

class TierScoresSchema(BaseModel):
    tier1_qc_flag: bool = Field(..., description="Tier 1 deterministic QC violation flag")
    tier2_point_score: float = Field(..., description="Tier 2 Isolation Forest score [0, 1]")
    tier2_temporal_score: float = Field(..., description="Tier 2 GRU Autoencoder score [0, 1]")
    tier3_multivariate_score: float = Field(..., description="Tier 3 Mahalanobis/Thermo score [0, 1]")
    tier1_hard: Optional[float] = Field(0.0, description="Tier 1 hard override score")
    tier1_soft: Optional[float] = Field(0.0, description="Tier 1 soft continuous score")

class InferenceResultSchema(BaseModel):
    timestamp: str
    station_id: str
    is_anomaly: bool
    anomaly_score: float
    confidence: float
    severity: str
    classification: str
    is_fault: bool
    reason: str
    explanation: ExplanationResultSchema
    tier_scores: TierScoresSchema
    sensor_health: float
    sensor_status: str
    recommended_action: str
    degradation_risk: str = "STABLE"
    estimated_hours_to_failure: Optional[float] = None
    multivariate_diagnostics: Optional[Dict[str, Any]] = Field(default_factory=dict)
    raw_values: Optional[Dict[str, float]] = Field(default_factory=dict)
    model_config = ConfigDict(from_attributes=True)

class ObservationIngestResponse(BaseModel):
    observation: ObservationResponse
    inference: InferenceResultSchema
    persisted: bool = True
    execution_time_ms: float

# --- Anomaly Event Schemas ---

class AnomalyEventResponse(BaseModel):
    id: int
    observation_id: int
    station_id: str
    timestamp: datetime
    anomaly_score: float
    confidence: float
    severity: str
    anomaly_type: str
    classification: str
    is_fault: bool
    explanation: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class AnomalyEventDetailResponse(AnomalyEventResponse):
    details: Optional[Dict[str, Any]] = None
    observation: Optional[ObservationResponse] = None

class AnomalyEventListResponse(BaseModel):
    items: List[AnomalyEventResponse]
    total: int
    limit: int
    offset: int

# --- Station Schemas ---

class StationCreate(BaseModel):
    station_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    elevation: Optional[float] = None
    status: str = Field("ACTIVE", max_length=32)

class StationResponse(BaseModel):
    id: int
    station_id: str
    name: str
    latitude: Optional[float]
    longitude: Optional[float]
    elevation: Optional[float]
    status: str
    health_score: Optional[float] = None
    health_status: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class StationListResponse(BaseModel):
    items: List[StationResponse]
    total: int

# --- Health Schemas ---

class SensorHealthRecord(BaseModel):
    timestamp: datetime
    health_score: float
    health_status: str
    anomaly_rate: float
    drift_score: float
    data_quality_score: float
    model_config = ConfigDict(from_attributes=True)

class StationHealthDetailResponse(BaseModel):
    station_id: str
    current_health: float
    health_status: str
    degradation_risk: str
    estimated_hours_to_failure: Optional[float]
    recommended_action: str
    recent_history: List[SensorHealthRecord]

class FleetHealthSummaryResponse(BaseModel):
    total_stations: int
    active_stations: int
    healthy_stations: int
    degraded_stations: int
    critical_stations: int
    average_health_score: float
    overall_status: str

# --- Simulation Schemas ---

class SimulationStartRequest(BaseModel):
    station_id: str = Field("AWS-SIM-001", min_length=1)
    interval_seconds: float = Field(1.0, gt=0.05, le=60.0)
    noise_level: float = Field(0.05, ge=0.0, le=1.0)
    scenario: str = Field("diurnal", description="Simulation scenario name")

class AnomalyInjectRequest(BaseModel):
    station_id: Optional[str] = None
    anomaly_type: str = Field(..., description="SPIKE, DRIFT, FROZEN, DROPOUT, NOISE_BURST, MULTIVARIATE_INCONSISTENCY")
    magnitude: Optional[float] = None
    duration_steps: int = Field(1, ge=1, le=100)
    parameter: str = Field("temperature", description="Target parameter: temperature, pressure, humidity")

class SimulationStatusResponse(BaseModel):
    running: bool
    station_id: Optional[str] = None
    interval_seconds: Optional[float] = None
    message: str

class AnomalyInjectResponse(BaseModel):
    success: bool
    anomaly_type: str
    parameter: str
    magnitude: Optional[float]
    duration_steps: int
    message: str

# --- CSV Upload Schemas ---

class UploadRowError(BaseModel):
    row: int
    error: str
    raw_data: Optional[Dict[str, Any]] = None

class UploadSummaryResponse(BaseModel):
    total_rows: int
    valid_rows: int
    anomalies_detected: int
    faults_detected: int
    stations_updated: List[str]
    execution_time_ms: float
    anomalies_summary: Dict[str, int] = Field(default_factory=dict)
    sample_anomalies: List[InferenceResultSchema] = Field(default_factory=list)
    errors: List[UploadRowError] = Field(default_factory=list)

# --- Analytics & Metrics Schemas ---

class MetricsResponse(BaseModel):
    total_observations: int
    total_anomalies: int
    anomaly_rate_pct: float
    anomaly_by_type: Dict[str, int]
    anomaly_by_severity: Dict[str, int]
    average_inference_latency_ms: float
    p95_inference_latency_ms: float
    p99_inference_latency_ms: float
    fleet_health_summary: Dict[str, int]
    system_status: str

# --- Ad-Hoc Inference Request Schema ---

class InferenceRequest(BaseModel):
    timestamp: Optional[Union[datetime, str]] = None
    station_id: str = "AWS-001"
    temperature: float
    pressure: float
    humidity: float
    persist: bool = False
```

---

## 4. CSV Upload Endpoint & Batch Ingestion Pipeline

### 4.1 Ingestion Flow Architecture

```text
Uploaded CSV File (UploadFile)
             │
             ▼
      Header & Column Normalization
      (timestamp, temperature, pressure, humidity)
             │
             ▼
      Row-by-Row Format & Range Validation
      (Capture row-level errors into summary list)
             │
             ▼
      Chronological Sort by Station & Timestamp
      (Guarantees temporal sliding buffer validity)
             │
             ▼
      Sequential Pipeline Inference (SkyGuardPipeline)
      (Tier 1 -> Tier 2 -> Tier 3 -> Fusion -> Tier 4 -> Tier 5)
             │
             ▼
      Async DB Bulk Chunk Insertion (aiosqlite)
      (Chunk size: 500 records to prevent variable limit errors)
             │
             ▼
      Transaction Commit / Rollback Safety
             │
             ▼
      UploadSummaryResponse JSON Return
```

### 4.2 Critical Reliability & Transaction Requirements

1. **Header Flexibility**: Accept case-insensitive variations (`Timestamp`, `TIMESTAMP`, `Temp`, `temperature`, `Pressure`, `Press`, `Humidity`, `RH`, `station_id`, `station`).
2. **Missing Columns Handling**: If any of `timestamp`, `temperature`, `pressure`, or `humidity` cannot be found after column normalization, return `400 Bad Request` with an explicit list of missing fields.
3. **Temporal Sorting**: Real-time feature calculation (rolling variance, rate-of-change, persistence check) requires observations to arrive in temporal order. If an uploaded CSV is disordered, sort by `pd.to_datetime(df['timestamp'])` before passing to `pipeline.process_batch()`.
4. **Station Auto-Creation**: If an uploaded observation contains a new `station_id`, auto-create the station entry in the database with status `ACTIVE` to maintain foreign key integrity.
5. **Chunked Transactional Commits**: SQLite imposes limits on SQL statement parameter count (`SQLITE_MAX_VARIABLE_NUMBER = 999` or `32766`). Using chunk sizes of 500 rows avoids parameter limit overflow.
6. **Detailed Summary Response**: Include total rows, valid rows, anomaly counts grouped by fault taxonomy (`SPIKE`, `DRIFT`, `FROZEN`, `METEOROLOGICAL_EXTREME`), sample anomaly explanations, and execution latency.

---

## 5. Test Suite Architecture for `tests/test_api.py` and `tests/test_ingestion.py`

### 5.1 Test Client & Async Session Setup (`conftest.py`)

Using `httpx.AsyncClient` with `ASGITransport(app=app)` and SQLite in-memory / temporary database session overrides ensures that all tests run with high speed, zero cross-test pollution, and complete isolation.

### 5.2 API Test Coverage Matrix (`tests/test_api.py`)

| Test Function | Target Endpoint | Scope / Scenarios Covered | Expected Status / Result |
|---|---|---|---|
| `test_root_endpoint` | `GET /` | Root service health & metadata | `200 OK`, `status == "online"` |
| `test_system_health` | `GET /api/health` | Backend service health & fleet health overview | `200 OK`, `status == "healthy"` |
| `test_create_and_get_station` | `POST /api/stations`, `GET /api/stations/{id}` | Happy path: create station and fetch details | `201 Created`, `200 OK` |
| `test_create_duplicate_station` | `POST /api/stations` | Edge case: duplicate station ID | `400 Bad Request` |
| `test_get_nonexistent_station` | `GET /api/stations/UNKNOWN` | Edge case: unknown station ID | `404 Not Found` |
| `test_ingest_nominal_observation` | `POST /api/observations` | Ingest nominal observation, verify pipeline outputs | `201 Created`, `is_anomaly == False`, `classification == "NORMAL"` |
| `test_ingest_spike_observation` | `POST /api/observations` | Ingest transient spike (+25°C), verify detection | `201 Created`, `is_anomaly == True`, `classification in ["SPIKE", "DATA_CORRUPTION"]` |
| `test_ingest_wmo_range_violation` | `POST /api/observations` | Ingest extreme physics violation (85°C) | `201 Created`, `is_anomaly == True`, `anomaly_score == 1.0` |
| `test_ingest_malformed_observation` | `POST /api/observations` | Edge case: missing temperature / string value | `422 Unprocessable Entity` |
| `test_query_observations_filtered` | `GET /api/observations` | Filter by `station_id`, date range, pagination | `200 OK`, `items` match filters |
| `test_query_anomalies_filtered` | `GET /api/anomalies` | Filter by `severity="HIGH"`, `classification="SPIKE"` | `200 OK`, all items have matching severity/type |
| `test_get_anomaly_detail` | `GET /api/anomalies/{id}` | Retrieve full TreeSHAP explanation & tier scores | `200 OK`, explanation & contributing features present |
| `test_get_nonexistent_anomaly` | `GET /api/anomalies/999999` | Edge case: query missing anomaly | `404 Not Found` |
| `test_station_health_trend` | `GET /api/health/{station_id}` | Fetch 0–100 health score, trend & degradation risk | `200 OK`, `health_score` in [0, 100] |
| `test_simulation_lifecycle` | `POST /api/simulate/*` | Start simulator, query status, stop simulator | `200 OK` across all transitions |
| `test_simulation_inject_anomaly` | `POST /api/simulate/inject` | On-the-fly anomaly injection trigger | `200 OK`, `success == True` |
| `test_system_metrics_endpoint` | `GET /api/metrics` | Aggregated metrics, latency percentiles, fleet health | `200 OK`, all expected metric keys present |
| `test_adhoc_infer_endpoint` | `POST /api/infer` | Ad-hoc observation inference without database write | `200 OK`, full `InferenceResultSchema` returned |

### 5.3 Ingestion Test Coverage Matrix (`tests/test_ingestion.py`)

| Test Function | Target Feature | Scope / Scenarios Covered | Expected Result |
|---|---|---|---|
| `test_upload_clean_baseline_csv` | `POST /api/upload` | Upload standard clean CSV (`data/baseline_clean.csv`) | `200 OK`, `valid_rows > 0`, `anomalies_detected == 0` |
| `test_upload_injected_anomalies_csv` | `POST /api/upload` | Upload dataset with injected spikes, drift, frozen | `200 OK`, `anomalies_detected > 0`, breakdown by fault type |
| `test_upload_empty_csv` | `POST /api/upload` | Edge case: upload empty CSV file (0 bytes) | `400 Bad Request`, informative error message |
| `test_upload_missing_required_columns` | `POST /api/upload` | Edge case: CSV missing `humidity` column | `400 Bad Request`, lists missing column |
| `test_upload_corrupt_data_rows` | `POST /api/upload` | Edge case: CSV with partial corrupt numeric values | `200 OK`, valid rows ingested, corrupt rows in `errors` list |
| `test_upload_disordered_timestamps` | `POST /api/upload` | Edge case: CSV with shuffled timestamps | `200 OK`, rows sorted chronologically before inference |
| `test_frozen_sensor_stream_decay` | Sequential Ingestion | Ingest 8 identical readings to trigger persistence check | Transitions to `classification == "FROZEN"`, health decays |
| `test_convective_front_disambiguation` | Sequential Ingestion | Ingest squall front ($-\Delta T, +\Delta P, +\Delta RH$) | `classification == "METEOROLOGICAL_EXTREME"`, `is_fault == False` |
| `test_concurrent_observation_ingestion`| Concurrent Ingestion | Ingest 20 concurrent requests across multiple stations | `200/201 OK`, zero SQLite locking errors |
| `test_inference_latency_profiling` | Latency Profiling | Measure end-to-end ingestion latency per observation | Latency < 100ms (comfortably below 500ms target) |

---

## 6. Implementation Blueprint & Recommended Strategy

### Phase 1: Database Engine, Models & Repositories (`backend/app/db/`)
- `database.py`: Async SQLAlchemy engine (`sqlite+aiosqlite:///./data/skyguard.db`), WAL mode pragma, `get_db` dependency generator, `init_db()` lifecycle function.
- `models.py`: SQLAlchemy declarative models for `Station`, `Observation`, `AnomalyEvent`, `SensorHealth`, and `ModelRun`.
- `repositories.py`: Async CRUD and querying repositories (`StationRepository`, `ObservationRepository`, `AnomalyRepository`, `HealthRepository`, `MetricsRepository`).

### Phase 2: Pydantic Schemas (`backend/app/schemas/schemas.py`)
- Implement all schemas defined in Section 3 with strict validation constraints and comprehensive OpenAPI field descriptions.

### Phase 3: Services Layer (`backend/app/services/`)
- `ingestion_service.py`: Real-time and batch ingestion engine connecting database sessions and `SkyGuardPipeline`.
- `simulation_service.py`: Async background task generator and anomaly injection queue.
- `analytics_service.py`: Aggregation and metrics computation engine.

### Phase 4: API Routes & App Mounting (`backend/app/api/` & `backend/app/main.py`)
- `routes.py`: Mount all REST endpoints connecting to the services layer.
- `websocket.py`: Connection manager and `/ws/live` broadcasting.
- `main.py`: Lifespan event for DB startup and background simulation cleanup, CORS middleware, router inclusion.

### Phase 5: Test Suite Implementation & Verification (`tests/`)
- `test_api.py`: Comprehensive test suite covering all 18 test scenarios in Section 5.2.
- `test_ingestion.py`: Comprehensive test suite covering all 10 test scenarios in Section 5.3.
- Execute `python -m pytest tests/test_api.py tests/test_ingestion.py -v` to verify 100% pass rate.
