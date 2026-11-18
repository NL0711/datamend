# DataMend web app: project overview

Written 2026-11-18. Scope: the web app around the ML work (backend, frontend, data sources, live path, Locations feature). The model side is in `docs/PROJECT_OVERVIEW_MODEL.md`; this file does not repeat it.

How to read this file: every claim has a path in parentheses. Where a doc and the code disagree, the code is trusted and the conflict is listed in section 10. The many audit and report files in `docs/` come from earlier agent runs. They are treated as claims, not facts. Nothing here was run or re-tested while writing it.

Terms used: **module** is a file or package with a purpose. **Interface** is what callers of a module must know. **Seam** is a place where one implementation can be swapped for another without editing the callers. **Adapter** is a module that fits an outside thing (a feed, a device) to an interface.

---

## 1. Goal

Two goals exist in the repo and they differ.

1. **The goal the app was built for** (`GOAL.md`, `AGENTS.md`, `ARCHITECTURE.md`): an operations dashboard for Automatic Weather Stations. Input is temperature, pressure and relative humidity (T/P/RH). For each observation it answers: is this a genuine atmospheric reading or a likely sensor or data fault? It gives an anomaly score, confidence, severity, a fault class, a text explanation, a sensor health score (0 to 100) and a recommended action.
2. **The direction the project has now** (`TODO.md`, last lines; `docs/LOCATIONS_MODEL_SCORES_PLAN.md`): rainfall only. The ERA5 temperature, humidity and pressure work was deleted on 2026-11-18. The research work is rainfall quality control on RF25 gridded daily rainfall (`ml-service/qc/`, see `CONTEXT.md`).

The web app was built for goal 1 and has only partly been moved towards goal 2. The owner has decided that the T/P/RH parts are to be removed. That removal is not started (current focus is ML training), so until then they are legacy, scheduled for removal. See section 8 and the removal scope in section 8a.

## 2. Impact (what the app shows, and what it does not prove)

What an operator can see today:
- A live stream of T/P/RH readings per station, each with an anomaly verdict, a fault class, an explanation and a station health score (`backend/app/services/ingestion_service.py`, `frontend/src/components/LiveMonitoringView.tsx`).
- A history of flagged events, per-station sensor health, a data explorer with CSV upload, and a lab to inject faults on purpose (`frontend/src/App.tsx`).
- A Locations view: for a place such as Mumbai, the recent weather from Open-Meteo, whether today is unusual for the day of the year, and rule-based data-QC flags (`backend/app/locations/service.py`).

What this does NOT prove:
- **The ML models behind the live T/P/RH path are trained on simulated data.** `models/model_metadata.json` records 5,760 training rows and 1,440 validation rows, trained 2026-08-24. `docs/SKYGUARD_FINAL_CURRENT_STATE_AND_REMAINING_WORK.md` (section 33) itself says the models are trained on "physics-informed synthetic baselines" and were not benchmarked on labelled real archives.
- **The "NOAA" data is not a network of real stations.** `scripts/build_noaa_network.py` takes one real Denver record file (`data/noaa_benchmark.csv`) and copies it to six station names with fixed offsets (for example temperature minus 2.5, pressure plus 38). The result (`data/noaa_aws_network.csv`) is labelled "NOAA NEXRAD AWS Open Data". Only the diurnal shape is real. The cross-station differences are made up by the script.
- **Open-Meteo values are model output at a grid point, not station observations.** The Locations code says so in its response (`backend/app/locations/service.py`, `source.kind`).
- The Locations data-QC flag is a set of simple rules, not a trained model. Its own method label says "rules+statistics v0" (`backend/app/locations/qc.py`).
- No label of real sensor faults exists anywhere in the repo. Any performance number in `docs/evaluation_report.md` is on faults injected by the project's own simulator. That file is a report from an earlier run, not something re-run for this overview.

So the honest reading: this is a working demonstration of a monitoring system and its plumbing. It is not evidence that the detection works on real stations or on rainfall.

---

## 3. Architecture

### 3.1 Whole-system flow

```
 SOURCES (adapters, one active at a time)          backend/app/sources/
   NOAA csv replay (default)   Historical csv replay   Open-Meteo REST
   [Simulated generator]       [Physical ESP32 over MQTT]   <- exist, see 3.3
                 |
                 v  CanonicalTelemetry (T, P, RH, station, source, provenance)
        DataSourceManager (manager.py)  -- applies any injected fault
                 |
                 v
        IngestionService (services/ingestion_service.py)
           per-station lock, validation, worker thread
                 |
                 v
        DataMendPipeline (ml/legacy_tiers/pipeline.py)   "legacy 5-tier path"
           tier 1 rules, tier 2 point + temporal ML, tier 3 multivariate,
           fusion, tier 4 classifier, tier 5 health + explanation,
           spatial buddy check
                 |
        +--------+---------+
        v                  v
   SQLite (skyguard.db)   WebSocket /ws/live (api/websocket.py)
   via db/repositories          |
        |                       v
        +--> REST /api/*  -->  React app (frontend/src), 9 tabs + Settings

 SECOND, SEPARATE PATH (not on the live stream)
   POST /api/telemetry/process -> services/phase3_service.py -> ml/stages/ (6 stages)
   nothing in the frontend calls it

 THIRD, SEPARATE FEATURE (not on the live stream, not station based)
   Locations tab -> /api/locations/* -> locations/ package -> Open-Meteo (cached in SQLite)
```

### 3.2 Backend modules

Entry: `backend/app/main.py` builds the FastAPI app, creates tables, seeds the Mumbai preset, auto-starts the default data source, mounts three routers (REST, Locations, WebSocket), and enables CORS for local dev ports. Settings come from `backend/app/config.py` (env vars, `.env` not read here).

| Module | Purpose | Interface in short |
|---|---|---|
| `api/routes.py` (906 lines) | REST endpoints for stations, observations, anomalies, health, simulation control, CSV upload, ad-hoc inference, data sources, the 6-stage path, operator feedback. | FastAPI router under `/api`. Some endpoints carry two names (aliases) for older callers. |
| `api/websocket.py` | Keeps the list of browser connections and broadcasts results. | `ws_manager.broadcast_observation(...)`, `broadcast_alert(...)`; endpoint `/ws/live`. Clients can subscribe by station. |
| `api/locations.py` | REST for the Locations feature. | Six routes under `/api/locations`; builds a `LocationService`. |
| `sources/` | Adapters that turn a feed into `CanonicalTelemetry`. | Seam: `BaseDataSource` (`base.py`) with `start`, `stop`, `get_status`, `subscribe`. `DataSourceManager` picks the active one. |
| `schemas/canonical.py`, `schemas/schemas.py` | Pydantic contracts. | `CanonicalTelemetry.to_ml_input_dict()` turns a feed packet into pipeline input. |
| `services/ingestion_service.py` | The one place an observation goes through validation, inference, saving and broadcast. | `ingest_observation(obs_data, save_db, broadcast)`; also batch ingest for uploads. |
| `services/simulation_service.py` | Background loop that generates simulated stations, and the on-the-fly fault injector. | `start`, `stop`, `inject_anomaly`, `apply_injection(obs, station)`. |
| `services/analytics_service.py` | Fleet health summary, anomaly stats, latency percentiles. | Called from routes. |
| `services/phase2_service.py`, `phase3_service.py` | Orchestrators for the 6-stage path. | `phase3_pipeline_service.process_observation(...)`. `phase2` is not imported by any route (grep of `backend/app`). |
| `ml/legacy_tiers/` | The 5-tier pipeline that the live stream really uses. Loads trained files from `models/`. | `DataMendPipeline.process_observation(dict)`. Detail belongs to the model overview. |
| `ml/stages/` | The 6-stage pipeline (STL baseline, ensemble, physics, classifier, explanation, imputer). | Only reached through `phase3_service`. |
| `ml/screening/` | "Tier 0" deterministic screen, run inside the NOAA and replay adapters. | `tier0_screener`. |
| `ml/__init__.py` | Keeps old import paths alive with an alias table (for example `backend.app.ml.pipeline` maps to `legacy_tiers.pipeline`). | Import aliasing. Its docstring says "three modular layers". |
| `health/tracker.py` | Rolling station health and remaining-life estimate for the 6-stage path. | `predictive_health_tracker`; exposed at `GET /api/stations/{id}/health`. |
| `spatial/consensus.py` | Buddy check: does a station agree with neighbours within 50 km. Needs at least 2 neighbours. | `spatial_consensus_engine.evaluate_consensus(...)`; called from the legacy pipeline. |
| `db/` | Async SQLAlchemy engine, ORM models, repositories. | See section 6. |
| `locations/` | Locations feature. | See section 7. |
| `backend/simulator/` | Diurnal T/P/RH generator and fault injector (spike, drift, frozen, dropout, noise burst, multivariate, meteorological extreme, data corruption). | `DiurnalGenerator`, `AnomalyInjector`, CLI in `cli.py`. |

### 3.3 Seams, adapters and observations (not a redesign)

- **Data-source seam.** `BaseDataSource` is a real seam. Five adapters exist: NOAA csv replay, historical csv replay, Open-Meteo, simulated, physical MQTT. The `DataSourceManager` holds a map from `DataSourceType` to adapter.
- **Score-provider seam (Locations).** `ScoreProvider` is a `Protocol` with one method `get(row, col, day)`; `FileScoreProvider` reads `data/location_scores/<row>_<col>.json` (`backend/app/locations/scores.py`). The folder does not exist yet, so every response says "not available". This seam is built and empty.
- **Open-Meteo client seam (Locations).** `LocationService` takes the client and the score provider as constructor arguments, which is how the tests swap in a mock transport (`tests/test_locations.py`).
- **Observation 1: two of five adapters are not registered.** `DataSourceManager.initialize()` registers only NOAA, historical replay and Open-Meteo (`backend/app/sources/manager.py`). `SimulatedDataSource` and `PhysicalAWSDataSource` are imported but never put in the map. Consequences: `POST /api/data-sources/select` with `SIMULATED` or `PHYSICAL_AWS` raises "Unknown data source type" (HTTP 400); `POST /api/data-sources/physical/virtual-packet` returns 404 ("Physical AWS adapter not found"). The frontend has buttons for both (`frontend/src/components/DataSourceControl.tsx`).
- **Observation 2: duplicated simulation paths.** Simulated data can come from `SimulationService` (started by `/api/simulate/start`, pushes straight into ingestion) and from `SimulatedDataSource` (a second wrapper around the same generator). Only the first is reachable.
- **Observation 3: duplicated ML paths.** The live stream uses the legacy 5-tier pipeline. The newer 6-stage pipeline is a separate path with its own health tracker, reachable only by one REST route, and no frontend code calls it (`processTelemetryReading` in `frontend/src/services/api.ts` has no caller).
- **Observation 4: shallow pass-through.** `ml/__init__.py` alias table, `sources/__init__.py` re-exports, and `Station`-level routes that only forward to a repository add no behaviour. They exist for backward compatibility (`docs/DATAMEND_COMPAT_ALLOWLIST.md` explains the `skyguard` names that remain).
- **Observation 5: docstrings use stale paths.** `ml/legacy_tiers/pipeline.py` names itself `backend/app/ml/pipeline.py`; `health/tracker.py` cites files from other repositories. Docs and docstrings mention `backend/app/qc/`, which does not exist.
- **Observation 6: a module-level singleton pattern.** `data_source_manager`, `ingestion_service`, `simulation_service`, `predictive_health_tracker` and the WebSocket manager are global objects created at import time. This makes the app one process, one active source, and makes tests build their own instances.

---

## 4. Frontend

React + TypeScript + Vite + Tailwind + recharts + lucide; a Three.js globe (`frontend/package.json`, `frontend/src/design-system/components/StationGlobe3D.tsx`). Dev server port 5199 with a proxy of `/api` and `/ws` to `localhost:8000` (`frontend/vite.config.ts`). Live data arrives over `/ws/live` through `TelemetryStreamClient` (reconnects with backoff); the app keeps the last 200 results in memory (`App.tsx`). Keys 1 to 9 switch tabs, `s` opens Settings.

| # | Tab (label in UI) | What it shows | Real or placeholder (by code) | Rainfall relevant? |
|---|---|---|---|---|
| 1 | Command Center (`OverviewView`) | Station list, recent alerts, fleet KPIs, globe/map. | Real: reads `/api/stations`, `/api/anomalies`, `/api/observations`. | No, T/P/RH |
| 2 | Live Telemetry (`LiveMonitoringView`) | T, P, RH charts with anomaly verdict from the WebSocket. | Real: WebSocket plus `/api/observations`. | No |
| 3 | Alert Center (`AlertCenterView`) | Filterable list of anomaly events, detail drawer with explanation and spatial check, triage buttons. | Real: `/api/anomalies`, `/api/feedback`. | No |
| 4 | Sensor Health (`SensorHealthView`) | Health score and trend per station. | Real: `/api/health/{station}` (5-tier health). The newer `/api/stations/{id}/health` is not used. | No |
| 5 | Event Forensics (`EventDetailView`) | Per-event tier scores, raw values. | Real: `/api/anomalies`. | No |
| 6 | Data Explorer (`DataExplorerView`) | Paged observation history and CSV upload. | Real: `/api/observations`, `/api/upload`. | No |
| 7 | Anomaly Lab (`AnomalyInjectorUI`) | Buttons that inject a fault into the live stream. | Real. Works by changing the next observation of the active source. It is a test tool, not a detector. | No |
| 8 | XAI Reasoner (`ExplainabilityViewer`) | Feature contributions of stored anomalies. | Real: reads stored explanation JSON via `/api/anomalies`. | No |
| 9 | Locations (`LocationsView`) | Places, cells, current values, weather anomaly, QC flags, 7-day charts. | Real data from Open-Meteo. The "Trained model" line always reads "not available" until score files exist. | Partly (see section 7) |

Also: a Settings drawer (`settings/SettingsCenter.tsx`) with source selection, city presets, display preferences stored in browser localStorage, and a simulation on/off switch. A one-line status strip (`ContextualStatusStrip.tsx`) shows the active source.

Frontend calls that do not match the backend (checked by comparing `frontend/src/services/api.ts` with `backend/app/api/routes.py`):
- Settings simulation switch calls `/api/simulation/start|stop|status`. The backend has `/api/simulate/start|stop|status` (only `inject` has an alias). The call is wrapped in a silent `catch`, so the switch does nothing visible.
- `fetchFleetHealth` calls `/api/health/fleet` (not used by any view). Backend `/api/health` is the fleet summary; `/api/health/fleet` would match `/health/{station_id}` with id "fleet".
- `fetchHealth` calls `/api/health` expecting `{status, service, version}`; the backend returns the fleet summary. The result is discarded.
- `runInference` calls `/api/inference`; the backend route is `/api/infer`. Not used by any view.

---

## 5. Data sources and the real-time path

Default source: `NOAA_ISD` (`backend/app/config.py`, `DEFAULT_DATA_SOURCE`); the frontend context also defaults to `NOAA_ISD` (`frontend/src/context/SystemConfigurationContext.tsx`). `docker-compose.yml` overrides it to `SIMULATED`, which the manager cannot start (observation 1).

| Source | Where | How it works | State in code |
|---|---|---|---|
| NOAA csv replay | `sources/noaa_source.py`, `data/noaa_aws_network.csv` (3,000 data rows) | Replays rows in time order, all stations per timestamp, one tick per 1.5 s, with the tier-0 screen. Not live. | Registered, default. Data is derived from one Denver file (section 2). |
| Historical replay | `sources/replay_source.py`, `data/historical_benchmark_30d.csv` | Same idea, speed set by `HISTORICAL_REPLAY_SPEED` (1x, 10x, burst). | Registered. |
| Open-Meteo "current" | `sources/external_source.py` | Polls the forecast API for T, P, RH every 60 s for one lat/lon (default Pune); handles timeout and back-off. | Registered. Real network feed, but model output at a point. Can be re-pointed with `POST /api/data-sources/external/configure`. |
| Simulated | `sources/simulated_source.py`, `backend/simulator/` | Diurnal generator with injectable faults. | Written, not registered in the manager. Reachable through `/api/simulate/*` instead. |
| Physical ESP32 | `sources/physical_source.py`, `hardware/esp32/skyguard_aws/` | MQTT subscriber (paho) for `skyguard/aws/+/telemetry` and heartbeat. Stale after 30 s. | Written, not registered in the manager. No hardware has been run: `docs/SKYGUARD_FINAL_CURRENT_STATE_AND_REMAINING_WORK.md` says power-on was deferred. |

The real-time path, step by step: an adapter makes a `CanonicalTelemetry` packet, the manager drops packets from inactive sources, applies any active injected fault (`simulation_service.apply_injection`), and calls `ingestion_service.ingest_observation(save_db=True, broadcast=True)`. Inference runs in a worker thread. The result is saved (observation, anomaly event if flagged, health row) and broadcast over WebSocket with source provenance (`manager.py`, `ingestion_service.py`, `docs/DATA_LINEAGE.md`).

What is "real-time" here: the transport is live (poll, MQTT, WebSocket). Whether the data is live depends on the source. Replay and simulation are not live weather. Only Open-Meteo (and a physical node, if one were attached) is live.

Rainfall: no source in this list streams rainfall into the live path. Open-Meteo precipitation is used only by the Locations feature.

---

## 6. Database

SQLite file `skyguard.db` by default (`DATABASE_URL`), async SQLAlchemy 2, WAL mode and a retry helper for lock errors (`backend/app/db/database.py`). The file name still says "skyguard" on purpose (`docs/DATAMEND_COMPAT_ALLOWLIST.md`). Tables are created with `create_all`; later columns are added by a list of `ALTER TABLE` statements run at startup. There is no migration tool.

| Table | Used for | Defined in |
|---|---|---|
| `stations` | Station list; seeded at startup (includes `KTLX` and other NOAA radar-site names). | `db/models.py`, seed in `db/database.py` |
| `observations` | Every ingested reading, with source columns. | `db/models.py` |
| `anomaly_events` | Flagged readings with scores, class, explanation JSON. | `db/models.py` |
| `sensor_health` | Per-observation health row. | `db/models.py` |
| `model_runs` | Model metadata table. Nothing in `backend/app` was seen writing to it other than the repository layer. | `db/models.py` |
| `operator_feedback` | Triage answers from the Alert Center. | `db/models.py` |
| `locations`, `location_cells`, `cell_normals`, `location_series_cache` | Locations feature. | `locations/models.py` |

There is no `alerts` table, although `AGENTS.md` lists one. The 6-stage health tracker (`health/tracker.py`) keeps its state in memory only. PostgreSQL/TimescaleDB is an opt-in path through `docker-compose.yml` and `scripts/init_timescaledb.sql`; the default path and the tests use SQLite.

---

## 7. Locations feature

Design: `docs/LOCATIONS_DESIGN.md`. Status: built (v1), tests in `tests/test_locations.py` (21 test functions, mocked Open-Meteo). I did not run them.

What it does (code in `backend/app/locations/`):
1. A user adds a place by name or lat/lon (`POST /api/locations`). Names are geocoded with Open-Meteo (`openmeteo.py`). Mumbai is seeded at startup if there are no locations (`service.ensure_presets`).
2. `grid.py` maps the place and a radius to cells of the 0.25 degree RF25 grid (rows 0..128, cols 0..134, row 0 southernmost) and marks each cell as land or sea and by client region, using `ml-service/qc/assets/client_map.json`. Held-out regions are 3 and 6 in code.
3. `service.status()` fetches 7 days of hourly values for all cells in one Open-Meteo call (cached 10 minutes in `location_series_cache`; stale data is returned with a flag if the refresh fails).
4. `normals.py` builds day-of-year normals (mean and sd, 15-day smoothing) from 1991-2020 Open-Meteo archive data, once per cell, stored in `cell_normals`.
5. `anomaly.py`: for T, RH, P a z-score against the normal; for rain a class (dry, normal, heavy, very heavy) from wet-day percentiles.
6. `qc.py`: rule checks per variable (range, hourly step, stuck run, missing share) and a buddy check across the cells of the location; `classify` returns `consistent`, `genuine_event_likely`, `possible_data_fault` or `uncertain`. Rain gets no QC rule checks because zeros are normal.
7. `scores.py`: the empty plug-in for trained-model scores (section 3.3).

Rainfall relevance: the cell grid, the held-out regions and the rain percentile class tie it to the rainfall project. The weather anomaly, the QC rules and the status output are still mostly T/RH/P. The design doc (`LOCATIONS_DESIGN.md`) was written before the rainfall-only decision and still lists T/RH/P as the goal.

Not built (`docs/LOCATIONS_MODEL_SCORES_PLAN.md`, rewritten 2026-11-18 for rainfall only):
- Trained-model scores per cell. **PLANNED, NOT BUILT.** Plan: an export command in `ml-service` writes per-cell score files (schema 1 with provenance and thresholds); the backend reads them; a new endpoint and a "Trained model" panel show them. The plan keeps one rule: RF25-trained models are never fed Open-Meteo values, because they are different products. It also says "yesterday in Mumbai" will usually have no model score, since RF25 comes as yearly historical files.
- Websocket or alert integration for cells, scheduled batch fetch, comparison with real station data (`LOCATIONS_DESIGN.md` D7 and section 10). **NOT IMPLEMENTED.**

---

## 8. Status

| Part | Status | Basis |
|---|---|---|
| FastAPI backend, REST, WebSocket, SQLite persistence | Built, and covered by tests in `tests/` | Test files exist (`tests/test_api.py`, `test_ingestion.py`, `test_phase4_api_websocket.py` and others). Pass/fail not re-run. |
| Live stream through the legacy 5-tier path (T/P/RH) | Built but legacy, scheduled for removal | Used by `ingestion_service`; models in `models/` trained on simulated rows. |
| 6-stage path via `/api/telemetry/process` | Built but legacy, scheduled for removal, unused by the UI | `routes.py`, no frontend caller. |
| Data sources: NOAA replay, historical replay, Open-Meteo current | Built; replay data is derived (section 2) | `manager.py` |
| Data sources: simulated adapter, physical ESP32 adapter | Written but not wired into the manager | `manager.py`; hardware never run per `docs/SKYGUARD_FINAL_CURRENT_STATE_AND_REMAINING_WORK.md` |
| Simulation start/stop and Anomaly Lab | Backend built; Settings switch calls wrong URLs | section 4 |
| 9 dashboard tabs | 8 are T/P/RH legacy; Locations is partly rainfall related | `frontend/src/App.tsx` |
| Locations v1 (cells, Open-Meteo values, normals, QC flags, tab, REST) | Built, with tests (mocked) | `tests/test_locations.py` |
| Trained-model scores in Locations | Planned, not built | `LOCATIONS_MODEL_SCORES_PLAN.md` |
| Live rainfall source | Not chosen, not built | section 9 |
| Regional multi-resolution view | Proposed, not built | section 9 |
| Correction / imputation stored beside raw data | Code exists in `ml/stages/stage6_imputer.py`; `TODO.md` Phase 12 is unchecked; no UI | `TODO.md` |
| Alerts as a stored object, push notifications | Not built (alerts are queries on `anomaly_events`) | `routes.py` |
| Auth, TLS, multi-user | Not built | no code found in `backend/app` |
| Removal of the T/P/RH parts | Decided by the owner, not started | session decision; scope in section 8a |

Benchmark reports in the repo (claims, not re-run): `docs/evaluation_report.md` (injected-fault test set), `reports/noaa_benchmark.md` (500 Denver records, 0 detections). See `PROJECT_OVERVIEW_MODEL.md` for model-side numbers and their limits.

---

## 8a. Removal scope (decided, not started)

The owner has decided to remove the T/P/RH parts of the app. Nothing has been deleted. The list below is from reading imports and routes. Check it again with a fresh import search before deleting, because it was not verified by running anything.

**T/P/RH-only, to be removed**

Backend (`backend/`):
- `app/ml/legacy_tiers/`, `app/ml/stages/`, `app/ml/screening/`, the alias table in `app/ml/__init__.py`.
- `app/services/ingestion_service.py`, `simulation_service.py`, `phase2_service.py`, `phase3_service.py`, `analytics_service.py`.
- `app/health/tracker.py`, `app/spatial/consensus.py`.
- `app/sources/` (all adapters, `manager.py`, `base.py`) and `app/schemas/canonical.py`. The Locations feature does not use them: it has its own Open-Meteo client in `app/locations/openmeteo.py`.
- `simulator/` (generator, injector, scenarios, CLI).
- In `app/api/routes.py`: all routes (stations, observations, anomalies, health, simulate, upload, infer, data-sources, telemetry/process, feedback). In `app/api/websocket.py`: the whole module (the Locations feature has no WebSocket).
- In `app/db/models.py`: all six tables (`stations`, `observations`, `anomaly_events`, `sensor_health`, `model_runs`, `operator_feedback`), plus `db/repositories.py` and the seed and `ALTER TABLE` lists in `db/database.py`.
- In `app/schemas/schemas.py`: the T/P/RH schemas (not read in full; confirm nothing in `locations/` imports it, which holds for the imports seen).
- Data and models: `models/*` (the 5-tier artifacts), `data/*.csv` (NOAA network, historical benchmark, train/val/test files), the 78 MB `.grib` file if no one else needs it.

Frontend (`frontend/src/`):
- Tabs and components: Command Center (`OverviewView`), Live Telemetry (`LiveMonitoringView`), Alert Center (`AlertCenterView`), Sensor Health (`SensorHealthView`), Event Forensics (`EventDetailView`), Data Explorer (`DataExplorerView`), Anomaly Lab (`AnomalyInjectorUI`), XAI Reasoner (`ExplainabilityViewer`), plus `DataSourceControl`, `ContextualStatusStrip`, `TriageActions`.
- `services/websocket.ts`, the non-Locations functions in `services/api.ts`, `context/SystemConfigurationContext.tsx` (source and station state), the source and simulation parts of `settings/SettingsCenter.tsx`, and the globe and map components (`StationGlobe3D`, `NetworkMap`) and `frontend/public/assets/earth`, which exist to show stations.

Tests (`tests/`): about 27 of the test files import or exercise the legacy path, by a keyword search for tier, legacy_tiers, simulat, ingestion_service or sources. These include `test_tier*.py`, `test_pipeline.py`, `test_fusion.py`, `test_simulator.py`, `test_ingestion.py`, `test_api.py`, `test_data_sources.py`, `test_phase*.py`, the `test_m*` stress files, `test_task4_*.py`, `test_spatial_consensus.py`, `test_noaa_*.py` and `test_scenario_stress_durations.py`. Match each file by hand before deleting; `test_api.py` and `conftest.py` may hold shared setup.

Scripts (`scripts/`): `train_models.py`, `generate_datasets.py`, `generate_replay_dataset.py`, `import_noaa_data.py`, `build_noaa_network.py`, `benchmark_noaa.py`, `benchmark_system.py`, `empirical_stress_test.py`, `stream_telemetry_feed.py`, `probe_api_concurrency.py`, `test_anomaly_detection.py`, `test_noaa_nexrad.py`, `verify_*.py`, `audit_tool.py`, `generate_earth_assets.py`, `init_timescaledb.sql`, `servers.json`. Also `hardware/esp32/` (the ESP32 firmware feeds only the physical T/P/RH source) and `reports/noaa_benchmark.*`.

Docs: `GOAL.md`, `ARCHITECTURE.md`, `PROJECT.md`, `TEST_INFRA.md`, `ORIGINAL_REQUEST.md` and, in `docs/`: `API_LIVE_DATA_AUDIT`, `CURRENT_STATE_VERIFICATION`, `DATAMEND_COMPAT_ALLOWLIST`, `DATA_FLOW_AND_LIVE_VERIFICATION`, `DATA_LINEAGE`, `DATA_SOURCE_*`, `DESIGN_*`, `EARTH_GLOBE_IMPLEMENTATION_REPORT`, `END_TO_END_TEST_REPORT`, `EXTERNAL_API_SETUP`, `FINAL_SYSTEM_VERIFICATION`, `LIVE_DATA_*`, `LIVE_SYSTEM_*`, `MQTT_PROTOCOL`, `NOAA_BENCHMARKING`, `PHASE4_RESIDUAL_ISOLATION_FOREST`, `PHYSICAL_AWS_SETUP`, `SETTINGS_*`, `SKYGUARD_*`, `SPATIAL_BUDDY_CHECK`, `THREE_SOURCE_*`, `UI_UX_*`, `evaluation_report`. `AGENTS.md` and `README.md` need rewriting, not deletion. `docker-compose.yml`, `Dockerfile.*` and `run.bat` need to be reduced to what remains.

**Shared with the Locations and rainfall path, must stay**
- `backend/app/main.py` (app, lifespan, CORS, Locations router; the data-source start and the stations seed are the parts to drop), `backend/app/config.py` (drop the source, MQTT and model settings; keep the database, CORS and API prefix), `backend/app/db/database.py` (engine, `Base`, `get_db`, `get_db_context`, `init_db` without the seeds).
- `backend/app/locations/` (all files), `backend/app/api/locations.py`, `tests/test_locations.py`. That test file imports `backend.app.main`, so `main.py` must keep importing cleanly after the router and lifespan edits.
- `ml-service/qc/assets/client_map.json` (read by `locations/grid.py`) and, later, `data/location_scores/`.
- Frontend: `App.tsx` (shell, cut down to one tab), `main.tsx`, `index.css`, `components/LocationsView.tsx`, the Locations functions in `services/api.ts`, `design-system/components/StatusBadge.tsx` and the other generic ones used by it (`EmptyState`, `MetricCard`, `SkeletonLoader` if still used), build config (`package.json`, `vite.config.ts`, `tailwind.config.js`, `nginx.conf`).
- `requirements.txt` stays but loses torch, shap, pyod, paho-mqtt, statsmodels if nothing else uses them.

**Not removal but needs rework after it:** the Locations code still treats temperature, humidity and pressure as its main variables (`locations/normals.py` `VARIABLES`, `qc.py` `PHYSICAL`, `anomaly.py`, the status payload and the view). Rainfall-only means those parts change too. That is a separate step from deleting the legacy path.

---

## 9. PROPOSED, NOT BUILT: regional multi-resolution view

Nothing in this section exists in the code. It is a proposal.

Idea: a regional map where models at several time scales (daily, monthly or seasonal, yearly, decadal) each produce a score for a cell or region, and one fused result is shown, with real-time anomaly detection.

Points to settle before any build:
- **Only the daily scale can be real-time.** Monthly, yearly and decadal scales change slowly and can be recomputed on a schedule.
- **A live rainfall source has not been chosen.** The models are trained on RF25 (IMD gauge-based grid, yearly files). Open-Meteo rainfall is a different product, so it cannot simply be fed to those models (`LOCATIONS_MODEL_SCORES_PLAN.md`, fact A and decision D1). A source with near-real-time gridded rainfall, or a calibration step between products, is an open choice.
- **Where it would plug in.** The existing seams would be reused: the Locations cell grid (`grid.py`), a score provider (`scores.py`), the data-source adapter seam (`sources/base.py`) and the WebSocket. A fused multi-scale result would need its own file format and endpoint; the schema-1 score file in the plan has components and thresholds but no time-scale field.
- **Evidence.** Each scale would carry its own validation status. All current validation is on synthetic faults, and the UI must say so (`LOCATIONS_MODEL_SCORES_PLAN.md`, decision D4).

---

## 10. Known gaps and conflicts between docs and code

Trust order used: code, then dated plan docs, then audit reports.

**A. Code versus the app's own wiring**
1. Data sources: `manager.py` registers 3 adapters (NOAA, replay, Open-Meteo). Docs and UI describe 3 sources as Simulated, Open-Meteo, Physical (`README.md`, `docs/DATA_SOURCE_ARCHITECTURE.md`, `docs/FINAL_SYSTEM_VERIFICATION.md`, `DataSourceControl.tsx`). Selecting Simulated or Physical fails. `docker-compose.yml` sets `DEFAULT_DATA_SOURCE=SIMULATED`, which cannot start.
2. `tests/test_data_sources.py::test_data_source_manager_switching` asserts 2 registered sources; the code registers 3. Not run here. Either the test or the code is out of date.
3. Frontend URLs that do not exist on the backend (section 4): `/api/simulation/start|stop|status`, `/api/health/fleet`, `/api/inference`; `fetchHealth` expects a different body than `/api/health` returns.
4. `docs/API_LIVE_DATA_AUDIT.md` and `docs/LIVE_DATA_MATRIX.md` list `/api/simulator/*` and `/api/health/fleet`, `/api/health/station/{id}` as "working". The code has `/api/simulate/*` and `/api/health/{id}`.
5. `docs/CURRENT_STATE_VERIFICATION.md` cites `POST /api/simulator/inject`; the code route is `/api/simulate/inject` (alias `/api/simulation/inject`).

**B. Docs versus each other**
6. Benchmark numbers: `docs/NOAA_BENCHMARKING.md` reports a nominal anomaly rate of 3.8% and health 94.2 ("sample excerpt"); `reports/noaa_benchmark.md` shows 0 detections and health 77.8 on 500 records. The doc's table does not match the report it points to.
7. MQTT topic names: `docs/MQTT_PROTOCOL.md` draws the tree as `datamend/aws/...` but specifies `skyguard/aws/...`; code and firmware use `skyguard/aws/...`.
8. Hardware path: `README.md`, `docs/PHYSICAL_AWS_SETUP.md` and the audit say `hardware/esp32/datamend_aws/datamend_aws.ino`; the folder is `hardware/esp32/skyguard_aws/skyguard_aws.ino`.
9. Ports: backend 8000 everywhere in code. `docs/API_LIVE_DATA_AUDIT.md` says 8899. Frontend dev port is 5199 (`vite.config.ts`, `run.bat`); `README.md` does not state it, the final audit says 5173, and Docker maps 5173 to nginx.
10. Tab count: `PROJECT.md` says 7 views; docs say 8; `App.tsx` has 9 tabs plus Settings.
11. `docs/SKYGUARD_FINAL_CURRENT_STATE_AND_REMAINING_WORK.md` calls itself the "single binding reference"; `docs/SKYGUARD_CURRENT_STATE_AND_REMAINING_WORK.md`, `FINAL_SYSTEM_VERIFICATION.md` and `LIVE_SYSTEM_FINAL_AUDIT.md` make the same kind of claim. It lists `backend/app/qc/` (absent) and only four tables (the code has six plus the Locations tables).
12. `docs/PHASE4_RESIDUAL_ISOLATION_FOREST.md` names `models/residual_iforest.joblib` as the canonical artifact; that file is not in `models/`. The live path loads the older `isolation_forest.joblib` (`ml/legacy_tiers/pipeline.py`). `TODO.md` marks Phase 4 done with the residual version as canonical.
13. `TODO.md` Phase 13 (Database) has unchecked boxes for the SQLite file and the stations, observations and anomaly-events tables, which exist; Phase 14 onward is checked. Phase 12 (imputation) is unchecked although `stage6_imputer.py` exists. The final checklist says "tests passing", but no test run is recorded in `TODO.md`.
14. `TEST_INFRA.md` maps features to `tests/e2e/tier1_features/...`; `tests/e2e/` does not exist (no tracked files). The tests live flat in `tests/`.
15. `PROJECT.md` code layout shows `ml/pipeline.py`, `ml/tier1_qc.py` and a Windows path from another machine; the real files are under `ml/legacy_tiers/`.
16. `docs/LOCATIONS_DESIGN.md` names the cache table `cell_series_cache`; the code table is `location_series_cache`. Its header says QC covers range, step and stuck; the code applies these to T/RH/P only. Its goal text still lists T/RH/P; the plan file is rainfall-only. `locations/scores.py` documents an old score file layout (temperature, humidity, pressure per day) that the plan replaces with schema 1; the code still has the old one.
17. Docs state "zero mock data" and "production-ready" (`docs/CURRENT_STATE_VERIFICATION.md`, `THREE_SOURCE_INTEGRATION_AUDIT.md` says "90% pilot / production ready"). The code shows: models trained on simulated data, a derived "NOAA network", unregistered adapters, wrong URLs, no auth. Treat those words as unproven.
18. `AGENTS.md` and `GOAL.md` still define the project as T/P/RH. The rainfall-only decision is only in `TODO.md`, `CONTEXT.md` and the plan docs.

**C. Gaps (not conflicts)**
19. No live rainfall source, no trained-model scores in the app, no regional view.
20. No authentication, no rate limiting on write endpoints; CORS is limited to local ports.
21. The 6-stage path and the health tracker have no UI and keep state in memory.
22. `docker-compose.yml` needs `POSTGRES_PASSWORD` and starts a pgAdmin container; the default path needs none of it. The frontend Dockerfile uses node 18 while `run.bat` asks for Node 18+; `docs/SKYGUARD_FINAL_CURRENT_STATE_AND_REMAINING_WORK.md` lists Python 3.14 and Node 20, `requirements.txt` says Python 3.10+.
23. Tracked files that look like runtime output: `skyguard.db` (+ `-shm`, `-wal`) in the repo root and a 78 MB `.grib` file in `data/`.
24. Frontend has no test suite in the tree (`frontend/test_sf.js` is a stray script).

---

## 11. How to run

Commands are taken from `README.md`, `run.bat` and `docker-compose.yml`. They were not run for this file.

Backend (Python 3.10+):
```
pip install -r requirements.txt
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```
(`run.bat` omits `--reload` on purpose; reload starts two processes on one SQLite file and causes "database is locked" on Windows. `README.md` shows `--reload`.)

Frontend:
```
cd frontend
npm install
npm run dev        # http://localhost:5199, proxies /api and /ws to port 8000
npm run build
```

Windows shortcut: `run.bat` checks Python and Node, installs dependencies, opens backend (8000) and frontend (5199) in two windows and opens the browser.

API docs once the backend is up: `http://localhost:8000/docs`.

Tests and benchmarks (as written in `README.md`): `python -m pytest tests/test_data_sources.py tests/test_sanity.py -v`; Locations tests: `python -m pytest tests/test_locations.py`; latency benchmark: `python -m scripts.benchmark_system`.

Retrain the T/P/RH models: `scripts/train_models.py` (writes to `models/`).

Optional Docker stack (TimescaleDB, backend, nginx frontend on 5173, pgAdmin): `docker compose up --build`. Requires `POSTGRES_PASSWORD` in the environment or `.env`. See the conflict about its default data source in section 10, item 1.

Locations needs internet access to Open-Meteo on first use of each place (30 years of daily history, then recent hours). Settings are in `.env` (template: `.env.example`).

Rainfall model training and scoring are in `ml-service/` and are described in `docs/PROJECT_OVERVIEW_MODEL.md`.
