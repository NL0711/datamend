# Review & Adversarial Stress-Test Report — Milestone 3

**Reviewer Agent**: `m3_reviewer_2` (Reviewer / Adversarial Critic)  
**Parent Agent**: `parent` (`f3146a74-66da-4d87-b36b-f94588b42f0d`)  
**Working Directory**: `c:\Users\ARYAN - AYUSH\OneDrive\Desktop\skyguard\.agents\m3_reviewer_2\`  
**Milestone**: Milestone 3 — API, Services & Streaming Review  
**Date**: 2026-08-24  
**Verdict**: **REQUEST_CHANGES**

---

## 1. Executive Summary

A comprehensive quality review and adversarial stress-test was conducted on the Milestone 3 implementation covering FastAPI REST endpoints, WebSocket `/ws/live` streaming, database repositories, `IngestionService`, `SimulationService`, `AnalyticsService`, and Pydantic schemas.

The overall architecture, schema design, WebSocket connection lifecycle management, asynchronous SQLite WAL configuration, and ML pipeline threading are implemented to a very high standard with zero dummy or facade implementations. However, **1 Critical runtime bug** in `backend/app/api/routes.py` (awaiting a non-coroutine in `/api/infer`) and **1 Major performance bottleneck** in `backend/app/services/ingestion_service.py` (per-row database session commit in CSV upload) were identified.

---

## 2. Review Dimensions & Findings

### Critical Findings

#### [Critical] Finding 1: Runtime `TypeError` in `/api/infer` endpoint due to awaiting synchronous method
- **Location**: `backend/app/api/routes.py`, line 545
- **Code**:
  ```python
  544:         # Run inference in worker thread without saving to DB
  545:         inf_res = await ingestion_service.pipeline.process_observation(data)
  ```
- **Analysis**:
  In `backend/app/ml/pipeline.py` line 151, `process_observation` is defined as a standard synchronous method:
  ```python
  def process_observation(self, obs: Union[Dict[str, Any], Any]) -> InferenceResult:
  ```
  Calling `await ingestion_service.pipeline.process_observation(data)` executes `process_observation(data)` synchronously, which returns an instance of `InferenceResult` (a Pydantic `BaseModel`). Python then attempts to `await` the `InferenceResult` instance, which does not implement `__await__`. This immediately raises:
  ```
  TypeError: object InferenceResult can't be used in 'await' expression
  ```
  Whenever any client issues a request to `POST /api/infer` with `persist=False` (which is default `persist: bool = False`), the endpoint crashes with HTTP 500.
- **Required Fix**:
  Offload the synchronous call to a worker thread via `asyncio.to_thread` (matching the pattern used in `ingestion_service.py:87` and stated in the comment):
  ```python
  inf_res: InferenceResult = await asyncio.to_thread(
      ingestion_service.pipeline.process_observation, data
  )
  ```

---

### Major Findings

#### [Major] Finding 2: Per-Row Database Transaction Commits in `process_csv_upload`
- **Location**: `backend/app/services/ingestion_service.py`, lines 452–511
- **Code**:
  ```python
  451:             # Persist observation to database
  452:             async with get_db_context() as session:
  453:                 station_repo = StationRepository(session)
  454:                 obs_repo = ObservationRepository(session)
  ...
  507:                 await station_repo.update_status(...)
  ```
- **Analysis**:
  In `process_csv_upload`, the loop iterates over all parsed rows in the CSV file and enters `async with get_db_context() as session:` for **every single row**. `get_db_context()` creates a new session, acquires a transaction lock, and commits to SQLite upon context exit. For a typical AWS historical dataset (e.g. 5,000 to 50,000 rows), this triggers thousands of sequential disk commits and lock acquisitions, creating severe I/O thrashing and high latency.
- **Suggested Fix**:
  Collect parsed observations, anomaly events, and health records into batches (e.g., chunks of 250–500 rows) and commit them within a single `async with get_db_context() as session:` block using `add_all` / bulk repository methods.

---

### Minor / Observational Findings

#### [Minor] Finding 3: Memory Accumulation in Station Locks
- **Location**: `backend/app/services/ingestion_service.py`, lines 49–52
- **Code**:
  ```python
  self._station_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
  ```
- **Analysis**:
  `_station_locks` maintains an `asyncio.Lock` per station. For standard fleet deployments (tens of stations), memory usage is trivial. In an open API environment with unvalidated station IDs, arbitrary station strings could cause unbounded dict growth.
- **Suggested Fix**:
  Ensure station IDs are validated or bound to registered stations.

---

## 3. Detailed Component Verification

### A. REST API Endpoints & Status Codes
| Endpoint | Method | Expected Status Codes | Parameter Validation | Status |
|---|---|---|---|---|
| `/api/stations` | GET | 200 | `status`, `limit`, `offset` | PASS |
| `/api/stations` | POST | 201, 400 | `StationCreate` (length, ranges) | PASS |
| `/api/stations/{id}` | GET | 200, 404 | Path param string | PASS |
| `/api/stations/{id}` | DELETE | 200, 404 | Path param string | PASS |
| `/api/observations` | POST | 201, 422, 500 | `ObservationCreate` (T: -100..100, P: 100..1500, RH: -20..150) | PASS |
| `/api/observations/batch` | POST | 200, 500 | `List[ObservationCreate]` | PASS |
| `/api/observations` | GET | 200 | `station_id`, `start_time`, `end_time`, `page`, `page_size`, `order` | PASS |
| `/api/anomalies` | GET | 200 | `station_id`, `severity`, `classification`, `is_fault`, `min_score` | PASS |
| `/api/anomalies/alerts/active`| GET | 200 | `station_id`, `min_severity`, `limit` | PASS |
| `/api/anomalies/stats/summary`| GET | 200 | `station_id`, `hours` (1..720) | PASS |
| `/api/anomalies/{id}` | GET | 200, 404 | Integer `anomaly_id` | PASS |
| `/api/health` | GET | 200 | None | PASS |
| `/api/health/{station_id}` | GET | 200, 404 | `station_id`, `limit` | PASS |
| `/api/simulate/start` | POST | 200 | `interval_seconds` (0.05..60), `noise_level` | PASS |
| `/api/simulate/stop` | POST | 200 | None | PASS |
| `/api/simulate/inject` | POST | 200 | `anomaly_type`, `magnitude`, `duration_steps` | PASS |
| `/api/simulate/status` | GET | 200 | None | PASS |
| `/api/upload` | POST | 200, 400, 500 | File extension `.csv`, non-empty, required columns | PASS |
| `/api/metrics` | GET | 200 | `station_id`, `window_hours` | PASS |
| `/api/infer` | POST | 200, 500 | `InferenceRequest` (persist flag) | **FAIL** (Finding 1) |

### B. WebSocket `/ws/live` Endpoint
- **Subscription Management**: Verified. Supports `{"type": "subscribe", "stations": ["AWS-001", "AWS-002"]}` and wildcard `*`.
- **Station Filtering**: Verified. Broadcast targets are filtered against each client's subscription set.
- **Heartbeat (Ping/Pong)**: Verified. Handles `{"type": "ping", "client_time": "..."}` and replies with server timestamp.
- **Dropped Connection Handling**: Verified. Safe send with `asyncio.wait_for(timeout=1.5)` prunes dead sockets on failure without impacting healthy subscribers.
- **Lifespan Integration**: Verified. Simulation background task is cancelled cleanly on shutdown.

### C. Ingestion Service & ML Pipeline Integration
- **5-Tier ML Pipeline**: Verified. Invokes `SkyGuardPipeline.process_observation` running Tier 1 QC, Tier 2 Isolation Forest + GRU Autoencoder, Tier 3 Clausius-Clapeyron + Mahalanobis, Multi-tier Fusion, Tier 4 Fault Classifier, and Tier 5 Health + TreeSHAP.
- **Async Concurrency**: Verified. Uses per-station `asyncio.Lock` to guarantee time-series buffer sequentiality per station while allowing different stations to process concurrently.
- **Latency Monitoring**: Verified. Latencies recorded in `analytics_service` deque and percentiles calculated via numpy.
- **CSV Upload Normalization**: Verified. Flexible column aliasing (`temp` -> `temperature`, `press` -> `pressure`, `rh` -> `humidity`), chronological timestamp sorting, and error logging for corrupt rows.

---

## 4. Integrity & Anti-Cheat Verification

| Check | Result | Evidence |
|---|---|---|
| Hardcoded test results / model outputs | PASS | All scores generated via dynamic inference pipelines |
| Dummy or facade implementations | PASS | Full SQLAlchemy 2.0 ORM, aiosqlite WAL engine, real TreeSHAP explanations |
| Shortcuts bypassing intended task | PASS | All 8 required REST categories, WebSockets, simulation, and metrics fully coded |
| Fabricated verification logs | PASS | Real test suite covering edge cases and concurrency |

---

## 5. Logic Chain

1. **Observation**: `backend/app/api/routes.py:545` contains `inf_res = await ingestion_service.pipeline.process_observation(data)`.
2. **Observation**: `SkyGuardPipeline.process_observation` in `backend/app/ml/pipeline.py:151` is defined as `def process_observation(...)` and returns `InferenceResult`.
3. **Deduction**: In Python asyncio, awaiting a non-coroutine object raises `TypeError: object InferenceResult can't be used in 'await' expression`.
4. **Impact**: Calling `POST /api/infer` with `persist=False` immediately crashes with HTTP 500.
5. **Observation**: `backend/app/services/ingestion_service.py:452` opens a new `async with get_db_context() as session:` for every individual row during CSV upload.
6. **Deduction**: High-volume historical CSV ingestion will cause unnecessary transaction overhead and slow execution.
7. **Conclusion**: The codebase is architecturally solid and complete, but requires resolution of Finding 1 before approval.

---

## 6. Caveats

- Model artifacts in `models/` must be generated or initialized (handled automatically by test fixtures).
- Latency percentiles during cold start default to nominal baseline values until samples accumulate in the deque.

---

## 7. Actionable Next Steps for Implementer

1. In `backend/app/api/routes.py` line 545, change:
   ```python
   # Change from:
   inf_res = await ingestion_service.pipeline.process_observation(data)
   # To:
   inf_res: InferenceResult = await asyncio.to_thread(
       ingestion_service.pipeline.process_observation, data
   )
   ```
2. (Optional performance enhancement) In `backend/app/services/ingestion_service.py`, batch database insertions in `process_csv_upload` instead of opening a session per row.
3. Re-run test suite: `pytest tests/test_api.py tests/test_ingestion.py -v`.
