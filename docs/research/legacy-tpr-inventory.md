# Legacy temperature/pressure/humidity (T/P/RH) inventory

Research ticket: `docs/wayfinder/rainfall-validation-platform/tickets/t08-legacy-inventory.md` (parent: MAP.md).
Read-only inventory, written 2026-11-19. Nothing in the repo was changed except this file.

## 0. How this was verified, and one caveat about the tree

- Import edges were found with grep over `backend/`, `scripts/`, `tests/`, `ml-service/` (lines starting `import`/`from`), not from file names.
  The `backend/app/ml` package has an import alias layer (`backend/app/ml/__init__.py`, `_MODULE_ALIASES`) so `backend.app.ml.pipeline`
  resolves to `backend.app.ml.legacy_tiers.pipeline`; imports below are given by the real location.
- **Caveat: `backend/app/rainfall` and `backend/app/api/rainfall.py` are not on `main`.** They exist only on branch `isd-rainfall-feed`
  (commit 594aada, one commit on top of e8ddfa8; `main` has two later commits, `ceiling`, which that branch lacks). The legacy inventory
  below was taken from the `main` tree; the rainfall files were read from the checked-out `isd-rainfall-feed` working tree. The diff between the
  two branches touches only `.env.example`, `.gitignore`, `TODO.md`, `backend/app/config.py`, `backend/app/main.py`, `ml-service/qc/__main__.py`,
  the ceiling files, and new rainfall files, so the legacy list holds for both. **The removal slice must start from a tree that has the rainfall
  feed (merge `isd-rainfall-feed` first).**
- Measurements (memory, size) were taken on this Windows machine, Python 3.13, not on the `python:3.11-slim` image Render would build. They are
  indicative, not deployment numbers. Marked "measured" vs "estimate" below.

## 1. What the rainfall path actually imports (the keep-set)

Read from imports on `isd-rainfall-feed`:

| File | Imports from the repo |
|---|---|
| `backend/app/api/rainfall.py` | `backend.app.config.settings`, `backend.app.rainfall.service`, `backend.app.rainfall.weather_union` |
| `backend/app/rainfall/service.py` | `rainfall.catalog`, `rainfall.daily`, `rainfall.scorer`, `rainfall.weather_union`, **`backend.app.spatial.consensus.haversine_distance_km`** |
| `backend/app/rainfall/catalog.py` | **`backend.app.spatial.consensus.haversine_distance_km`**; reads CSV **`backend/app/sources/data/weather_union_stations.csv`** (path built from `Path(__file__).parents[1] / "sources" / "data"`) |
| `backend/app/rainfall/{daily,scorer,weather_union}.py` | only each other, stdlib and `httpx` |
| `tests/test_rainfall_feed.py` (27 tests) | the `rainfall` modules, `api.rainfall`, `httpx`, `fastapi.testclient` |

The rainfall feed does **not** use the database, the ORM models, the ML packages, `schemas`, `services` or any data source class. Its only
entanglements with legacy code are two:

1. `haversine_distance_km` lives in `backend/app/spatial/consensus.py`, a module whose other ~200 lines (SpatialConsensusEngine) are T/P/RH.
2. The station catalogue CSV sits inside `backend/app/sources/`, a package that is otherwise entirely legacy.

Both must be moved before the legacy packages can be deleted (step 1 of the removal order).

## 2. Group A: shared, must stay

| Path | Why it stays (evidence) |
|---|---|
| `backend/app/rainfall/*` (6 files), `backend/app/api/rainfall.py`, `tests/test_rainfall_feed.py`, `docs/RAINFALL_LIVE_FEED.md`, `scripts/build_weather_union_catalog.py` (all on `isd-rainfall-feed` only) | The rainfall path. |
| `backend/app/sources/data/weather_union_stations.csv` (581 lines, branch only) | Read by `rainfall/catalog.py`; must be relocated out of `sources/` before `sources/` is deleted. |
| `backend/app/main.py` | FastAPI shell and lifespan. Mounts `api_router` (legacy), `locations_router`, `rainfall_router` (branch), `ws_router` (legacy). Needs editing, not deletion (see step 4). |
| `backend/app/config.py` | `settings` used by rainfall, `db.database`, `main`. Contains legacy-only settings (MQTT_*, EXTERNAL_WEATHER_*, NOAA_ISD_DATA_PATH, HISTORICAL_*, DEFAULT_DATA_SOURCE, INFERENCE_WINDOW_SIZE, HEALTH_*, ANOMALY_THRESHOLD, PHYSICAL_*) to trim. |
| `backend/app/db/database.py` | Engine, `Base`, `get_db`, `init_db`, `close_db`, `run_with_db_retry`; imported by `locations/models.py`, `api/locations.py`, `main.py`. Its `init_db` contains legacy code: ALTER TABLE migrations on `observations`/`anomaly_events`, Timescale hypertable creation on `observations`, and seeding of 6 NEXRAD `Station` rows. Trim, keep the file. |
| `backend/app/locations/*` (9 files: `anomaly, grid, models, normals, openmeteo, qc, scores, service, __init__`), `backend/app/api/locations.py`, `tests/test_locations.py` (21 tests) | The Locations feature. Imports only `db.database`, `config`, own modules. No import of ML, services, sources, schemas. **Note (decision for the spec): its weather half is itself T/P/RH.** `locations/normals.py:12 VARIABLES = ("temperature","humidity","pressure")`, `locations/qc.py` PHYSICAL ranges for the three, `locations/openmeteo.py` HOURLY/DAILY request all three plus precipitation, `locations/service.py` loops over them, `locations/scores.py` documents T/P/RH score files. Per MAP.md "Out of scope: temperature, pressure or humidity validation", the spec should say whether Locations is trimmed to precipitation or kept as-is as a context display. Kept in this inventory, as the ticket asks. |
| `backend/app/locations/models.py` tables: `locations`, `location_cells`, `cell_normals`, `location_series_cache` | Only FKs among themselves (`locations.id`); no FK into legacy tables. |
| `backend/app/spatial/consensus.py::haversine_distance_km` (function only) | Imported by `rainfall/service.py` and `rainfall/catalog.py`. Needs `numpy`/`math` only; the `sklearn` KDTree import is lazy (line 83, inside `SpatialIndex`) and not on the rainfall path. Move to e.g. `backend/app/spatial/geo.py`. |
| `ml-service/**` (230 tracked files: `qc`, `training`, `ensemble`, `detectors`, `evaluation`, `validation`, scripts, notebooks, configs) | No file under `ml-service` imports `backend.*` (grep: zero hits). Its `ensemble/` mentions "temperature" only as softmax temperature scaling (`ensemble/branches.py:27`). Has its own `pyproject.toml` and `requirements-train.txt`, so root `requirements.txt` removals do not affect it. |
| Deployment: `Dockerfile.backend`, `Dockerfile.frontend`, `frontend/nginx.conf`, `.env.example` (needs trimming), `.gitignore`, `docker-compose.yml` (see section 4, partly legacy) | No `render.yaml`, Procfile or CI workflow is tracked in the repo (`git ls-files` finds none), so the Render setup is configured outside the repo; whoever removes legacy code must check the Render service's start/build commands by hand. |
| Frontend shell: `frontend/index.html`, `package.json`, `vite.config.ts`, `tsconfig*.json`, `tailwind.config.js`, `postcss.config.js`, `src/main.tsx`, `src/index.css`, `src/App.tsx` (edit), `src/components/LocationsView.tsx`, `src/design-system/components/{StatusBadge,EmptyState,MetricCard,SkeletonLoader}.tsx`, `src/design-system/tokens.ts` (12 T/P/RH mentions, check), `src/services/api.ts` (location calls at lines ~285-318 stay; rest legacy), `src/types/index.ts` (Location types at ~407 stay; 20 T/P/RH mentions elsewhere) | `LocationsView` imports only `StatusBadge`, lucide-react and api.ts. There is **no rainfall view in the frontend yet** (no import of `/api/rainfall` anywhere in `frontend/src`). |
| Docs about rainfall/QC: `CONTEXT.md`, `docs/qc-*.md` (4), `docs/mlops-feedback-loop-spec.md`, `docs/LOCATIONS_DESIGN.md`, `docs/LOCATIONS_MODEL_SCORES_PLAN.md`, `docs/PROJECT_OVERVIEW_MODEL.md`, `docs/research/*` (15), `docs/wayfinder/**`, `docs/RAINFALL_LIVE_FEED.md` | Rainfall-focused by content (keyword counts: rain high, T/P/RH ~0). `docs/PROJECT_OVERVIEW_MODEL.md` has 77 rainfall hits. |

## 3. Group B: exists only for T/P/RH (candidate for removal)

"How I know" is given per group. Line counts are from `wc -l`.

### B1. Backend ML packages (21 files, ~all of `backend/app/ml/`)

- `backend/app/ml/__init__.py` (alias finder), `backend/app/ml/legacy_tiers/` (12 files: `fusion, pipeline, preprocessor, tier1_qc, tier2_point_ml, tier2_temporal_ml, tier3_multivariate, tier4_classifier, tier5_explain, tier5_health, __init__`), `backend/app/ml/screening/` (2), `backend/app/ml/stages/` (7: `stage1_stl ... stage6_imputer, __init__`).
- Evidence: importers outside `backend/app/ml` are only `api/routes.py`, `services/{ingestion,phase2,phase3}_service.py`, `sources/{noaa,replay}_source.py`, `scripts/*`, `tests/*`; all legacy. Contents are T/P/RH specific (`CHANNELS`, `calculate_dew_point` in `tier3_multivariate`, physics rules in `stage3_physics`). No rainfall or locations file imports them.
- Heavy deps used only here: `torch` (`tier2_temporal_ml`, `stage2_ensemble`), `shap` (`tier5_explain`, `stage5_explain`), `pyod` (`stage2_ensemble`), `statsmodels` (`stage1_stl`), `joblib`, `scipy` (`tier3_multivariate`), `sklearn`.
- Trained artifacts in `models/` (8 tracked files, 1.7 MB: `autoencoder.pt, temporal_autoencoder.pt, isolation_forest.joblib, mahalanobis.joblib, fault_classifier.joblib, preprocessor.joblib, scaler.joblib, model_metadata.json`): loaded by the legacy pipeline; `docker-compose.yml` mounts `./models`.

### B2. Backend services, health, schemas, sources, simulator

| Group | Files | Evidence |
|---|---|---|
| Services (6) | `backend/app/services/{__init__,analytics_service,ingestion_service,phase2_service,phase3_service,simulation_service}.py` | Imported only by `api/routes.py`, `api/websocket.py`, `main.py` (`simulation_service`), `sources/*`, `tests`, `scripts`. They import `ml.*`, `db.repositories`, `simulator`, `health.tracker`. |
| Health (1) | `backend/app/health/tracker.py` (293 lines, no `__init__.py`) | Imported by `api/routes.py`, `services/phase3_service.py`, tests only. |
| Schemas (3) | `backend/app/schemas/{__init__,canonical,schemas}.py` | Imported by `api/routes.py`, `services`, `sources`, tests; contain T/P/RH observation, anomaly, health, simulation models. No rainfall/locations import. |
| Data sources (8) | `backend/app/sources/{__init__,base,external_source,manager,noaa_source,physical_source,replay_source,simulated_source}.py` | `manager.py` is started in `main.py` lifespan (`data_source_manager.start()`); `physical_source.py` is the only importer of `paho-mqtt`; `noaa_source`/`replay_source` use `ml.screening`; `external_source` polls Open-Meteo for T/P/RH (a separate client from `locations/openmeteo.py`). Config default is `NOAA_ISD` reading `data/noaa_aws_network.csv`. |
| Simulator (5) | `backend/simulator/{__init__,anomaly_injector,cli,diurnal_generator,scenarios}.py` | Generates synthetic T/P/RH with injected spikes/drift/frozen. Imported by `services/simulation_service.py`, `sources/simulated_source.py`, `scripts/{audit_tool,generate_datasets,stream_telemetry_feed}.py`, `tests/test_simulator.py`, `test_m1_challenger.py`, `test_scenario_stress_durations.py`. |
| Spatial (rest of file) | `backend/app/spatial/consensus.py` except `haversine_distance_km`, plus `spatial/__init__.py` re-exports | `SpatialConsensusEngine` has `temperature_deviation`, `pressure_deviation`, `humidity_deviation` fields (lines 36-40); used by `ml/stages`, `services/phase2/phase3`, `sources/replay_source`, `tests/test_spatial_consensus.py`. |

### B3. API routes (33 route decorators in `routes.py` + 1 WebSocket)

All in `backend/app/api/routes.py` (906 lines) and `backend/app/api/websocket.py` (253 lines, `/ws/live`):
`/api/stations` (GET, POST, GET/{id}, DELETE/{id}), `/api/stations/{id}/health`, `/api/observations` (GET, POST, batch), `/api/telemetry/live`, `/api/telemetry/process`, `/api/anomalies` (+ `/alerts/active`, `/stats`, `/stats/summary`, `/{id}`), `/api/alerts`, `/api/health`, `/api/health/{id}`, `/api/simulate/{start,stop,inject,status}`, `/api/simulation/inject`, `/api/upload` (CSV, 5-tier inference), `/api/metrics`, `/api/infer`, `/api/data-sources` (+ status, select, external/configure, external/preview, physical/virtual-packet), `/api/feedback`.
Evidence: handlers call `services.*`, `ml.stages`, `db.repositories`, `data_source_manager`. Note `/api/health` and `/api/stations` names are not part of rainfall (rainfall uses `/api/rainfall/*`), so nothing is shared. `/api/upload` is a CSV upload route for T/P/RH; the rainfall platform will need its own upload/validate route (python-multipart is its only user, see section 5).

### B4. Database tables and the data layer

| Item | Status |
|---|---|
| Tables `stations`, `observations`, `anomaly_events`, `sensor_health`, `model_runs`, `operator_feedback` (`backend/app/db/models.py`, 192 lines) | Legacy. All FK to `stations.station_id`; no FK from `locations` tables. Imported by `db/repositories.py`, `services/*`, `routes.py`, `database.init_db` (seed), `phase2/3_service`, scripts, tests. |
| `backend/app/db/repositories.py` (631 lines: Station/Observation/Anomaly/Health/ModelRun/OperatorFeedback repositories) | Legacy; imported by routes, `analytics_service`, `ingestion_service`, scripts, tests. |
| `database.init_db` legacy parts | ALTER TABLE migrations on legacy tables, TimescaleDB hypertable on `observations`, seed of 6 NEXRAD stations (KTLX, KOKX, KAMX, KATX, KFWS, KDMX). |
| `scripts/init_timescaledb.sql`, `scripts/servers.json`, `docker-compose.yml` (timescaledb, pgadmin, backend with `DEFAULT_DATA_SOURCE=SIMULATED`, MQTT env) | Timescale/pgAdmin stack exists for the `observations` hypertable. The compose backend service and frontend service are reusable; the DB services are tied to the persistence decision (MAP "Not yet specified": persistence). Rainfall feed does not use any DB. |

### B5. Frontend (12 components, plus services)

Legacy-only components (imports: `App.tsx` mounts them; they call legacy endpoints `fetchStations`, `fetchAnomalies`, `fetchObservations`, `fetchStationHealth`, `injectAnomaly`, `uploadCSV`, `startSimulation`, WebSocket stream):
`AlertCenterView.tsx, AnomalyInjectorUI.tsx, ContextualStatusStrip.tsx, DataExplorerView.tsx, DataSourceControl.tsx, EventDetailView.tsx, ExplainabilityViewer.tsx, LiveMonitoringView.tsx, OverviewView.tsx, SensorHealthView.tsx, TriageActions.tsx` (11), plus `context/SystemConfigurationContext.tsx` (used by the views and `SettingsCenter`), `settings/SettingsCenter.tsx` (CITY_PRESETS, simulation controls), `design-system/components/NetworkMap.tsx`, `StationGlobe3D.tsx` (+ `three`, `@types/three` deps, `public/assets/earth/*` 62 MB, `scripts/generate_earth_assets.py`, `sketchfab.html`, `sketchfab_embed.html`, `frontend/test_sf.js`), `services/websocket.ts`, the non-location half of `services/api.ts`, most of `types/index.ts`.
`DataSourceControl.tsx` is not imported by `App.tsx` (grep) and is only referenced by itself: dead code even in the legacy app.
`LocationsView.tsx` is the only non-legacy view. `NetworkMap`/`StationGlobe3D` are generic map/globe widgets, so a rainfall station map could reuse them; they are listed as legacy because their only importer is `OverviewView` and they type against `Station` (legacy).

### B6. Hardware, scripts, data, reports, root files

- `hardware/esp32/skyguard_aws/` (3 files: `.ino`, `config.example.h`, README): ESP32 T/P/RH publisher over MQTT. Only consumer is `sources/physical_source.py`. Remove with it. Docs: `docs/MQTT_PROTOCOL.md`, `docs/PHYSICAL_AWS_SETUP.md`.
- `scripts/` (22 files). Legacy: `audit_tool.py, benchmark_noaa.py, benchmark_system.py, build_noaa_network.py, empirical_stress_test.py, generate_datasets.py, generate_replay_dataset.py, import_noaa_data.py, probe_api_concurrency.py, stream_telemetry_feed.py, test_anomaly_detection.py, test_noaa_nexrad.py, train_models.py, verify_current_state.py, verify_phase2_pipeline.py, verify_phase3_pipeline.py, verify_timescaledb_ingestion.py, init_timescaledb.sql, servers.json` (import `ml.*`, `services.*`, `sources.*`, `simulator`, `db.models/repositories`, or write the legacy CSVs). Not legacy: `generate_earth_assets.py` (frontend globe asset, goes with the globe if the globe goes), `build_weather_union_catalog.py` (branch-only, rainfall). `scripts/` is copied into the image by `Dockerfile.backend` (`COPY scripts/`); nothing at runtime needs it.
- `data/*.csv` (9 files, 4.6 MB): `baseline_clean, cli_test_front, cli_test_multistation, historical_benchmark_30d, noaa_aws_network, noaa_benchmark, test_anomalies, train_clean, val_mixed`. Read by `config.py` defaults, `noaa_source`, `replay_source`, `simulator/cli.py`, `scripts/*`, `tests/conftest.py`, several tests. All T/P/RH. `data/.gitkeep` stays (`locations/scores.py` reads `data/location_scores/`, which is not tracked).
- `reports/` (4 files): `noaa_benchmark.{json,md}`, `api_concurrency_probe*.json`: legacy outputs of the scripts above.
- Root: `run.bat` (launches the full legacy system), `TEST_INFRA.md`, `.env.example` (sections: data source, MQTT, ML pipeline settings; keep DB/CORS), `openspec/specs/{api-parity,perf-evidence,residual-isolation-forest,sqlite-truth,triage-ui}` and the 2 archived changes (describe legacy behaviour; `openspec/changes/{datamend-light-rebrand,tab-continuity-station-truth}` are UI changes to legacy views).
- Not decided here: `.agents/` (398 tracked files, mostly agent run logs from the T/P/RH build; they contain no imports) and `.cline`, `.clinerules`, `.opencode` (tool skills/workflows, 33 openspec-related files). They are not code; the spec should decide whether to purge history-noise.

### B7. Tests (40 files in `tests/`; 351 tests collected on this machine)

Collected counts per file come from `pytest --collect-only`. Verdict is from each file's imports and the `/api/...` paths it calls.

**Shared, keep (22 tests on `main` plus 27 on the branch):** `tests/test_locations.py` (21 tests: `db.database`, `locations.*`, `main`), `tests/test_rainfall_feed.py` (27, branch only).

**Legacy-only, delete with the code they cover (approx. 322 tests):**
- ML tiers and pipeline: `test_tier0_screener` (6), `test_tier1_qc` (17), `test_tier2_ml` (9), `test_tier3_multivariate` (8), `test_tier4_classifier` (9), `test_tier5_health_explain` (6), `test_fusion` (12), `test_pipeline` (7), `test_alert_xai` (2), `test_empirical_m2_challenge` (6), `test_m2_adversarial_stress` (27), `test_phase2_ml_core` (16), `test_phase3_explain_heal_health` (8), `test_phase4_canonical_if` (10), `test_phase1_replay_pipeline` (3).
- Spatial consensus engine: `test_spatial_consensus` (4). (If `haversine_distance_km` moves, it deserves a 1-test replacement.)
- Simulator: `test_simulator` (28), `test_m1_challenger` (9), `test_scenario_stress_durations` (60).
- Sources and ingestion: `test_data_sources` (9), `test_city_presets` (4), `test_live_city_switch_integration` (1), `test_ingestion` (12), `test_m3_stress` (4), `test_task4_perf` (3).
- Legacy HTTP/API: `test_api` (22), `test_alert_drilldown_forensics` (3), `test_event_station_integrity` (2), `test_task4_triage` (4), `test_phase4_api_websocket` (6), `test_task4_parity` (5).
- NOAA tools: `test_noaa_benchmark` (1), `test_noaa_importer` (4); both fail at collection on this machine with `NameError: name 'Any' is not defined` (existing defect, independent of this work).
- Placeholder: `test_edge_cases` (1) is `assert True`, covers nothing.

**Generic but coupled to legacy, rewrite then keep:** `test_sanity` (3, checks `/api/health`, a legacy route), `test_config_stress` (9 tests on `Settings` defaults including legacy settings; also needs `pydantic_settings`, not installed in this environment so it errors at collection here), `test_task4_sqlite` (4, SQLite + legacy routes `/api/stations`, `/api/observations`, `/api/alerts`).

**Critical coupling:** `tests/conftest.py` imports `scripts.train_models` at import time and has a session-scoped autouse fixture `ensure_trained_models` which trains all legacy models (torch, sklearn) if any `models/*` artifact is missing; it also seeds the DB with `init_db()` for every test. Every test, including `test_locations` and `test_rainfall_feed`, therefore depends on the legacy training script and its heavy imports. This must be the first thing decoupled.

### B8. Docs about the legacy app (root and `docs/`)

Judged by keyword density (T/P/RH/MQTT/ESP32/SkyGuard vs rain/precip) and subject; this is a reading of the files' topics, with counts, not a deep review.
- Legacy, remove or archive: `docs/MQTT_PROTOCOL.md, PHYSICAL_AWS_SETUP.md, DATA_SOURCE_ARCHITECTURE.md, DATA_SOURCE_IMPLEMENTATION_PLAN.md, DATA_SOURCE_TESTING.md, EXTERNAL_API_SETUP.md, THREE_SOURCE_DATA_INTEGRATION_REPORT.md, THREE_SOURCE_INTEGRATION_AUDIT.md, LIVE_DATA_MATRIX.md, LIVE_DATA_VERIFICATION.md, LIVE_SYSTEM_ARCHITECTURE.md, LIVE_SYSTEM_AUDIT_REPORT.md, LIVE_SYSTEM_FINAL_AUDIT.md, FINAL_SYSTEM_VERIFICATION.md, CURRENT_STATE_VERIFICATION.md, END_TO_END_TEST_REPORT.md, API_LIVE_DATA_AUDIT.md, DATA_FLOW_AND_LIVE_VERIFICATION.md, DATA_LINEAGE.md, DATAMEND_COMPAT_ALLOWLIST.md, NOAA_BENCHMARKING.md, PHASE4_RESIDUAL_ISOLATION_FOREST.md, SPATIAL_BUDDY_CHECK.md, SKYGUARD_CURRENT_STATE_AND_REMAINING_WORK.md, SKYGUARD_FINAL_CURRENT_STATE_AND_REMAINING_WORK.md, EARTH_GLOBE_IMPLEMENTATION_REPORT.md, evaluation_report.md` (27 files). Of these, `NOAA_BENCHMARKING.md`, `evaluation_report.md`, `DATA_LINEAGE.md` mention rainfall 1-3 times; spot check before deleting.
- UI/UX docs for the legacy dashboard: `DESIGN_DIRECTION.md, DESIGN_RESEARCH_REPORT.md, DESIGN_SYSTEM.md, SETTINGS_*.md (3), UI_UX_AUDIT.md, UI_UX_RESEARCH_AND_DATA_FLOW_AUDIT.md` (8). `DESIGN_SYSTEM.md` and `DESIGN_DIRECTION.md` may still describe the visual language the new UI reuses; decide in the spec.
- Mixed, rewrite: `docs/PROJECT_OVERVIEW_WEBAPP.md` (23 T/P/RH hits, 30 rain hits), root `README.md` (8 T/P/RH, 0 rain), `ARCHITECTURE.md` (696 lines, 24 / 3), `GOAL.md` (12 / 1), `PROJECT.md`, `AGENTS.md` (827 lines, 20 / 9; section 1 and 6 still state the T/P/RH-only input constraint, which contradicts the rainfall direction), `TODO.md`, `TEST_INFRA.md`, `ORIGINAL_REQUEST.md`. MAP.md already lists the README/architecture/positioning rewrite as follow-up.

## 4. Group C: needs a decision or a split

1. `backend/app/spatial/consensus.py`: split `haversine_distance_km` out (shared) from the engine (legacy).
2. `backend/app/sources/data/weather_union_stations.csv`: move to `backend/app/rainfall/data/` and change `CATALOG_PATH` in `rainfall/catalog.py`; update `scripts/build_weather_union_catalog.py` output path.
3. `backend/app/config.py`, `.env.example`: delete legacy settings; keep `DATABASE_URL`, CORS, rainfall settings.
4. `backend/app/main.py`: drop `api_router`, `ws_router`, `simulation_service`, `data_source_manager` and the station seed; keep locations preset seeding and rainfall start/stop.
5. `backend/app/db/database.py`: drop legacy migrations, hypertable and station seed. Whether the DB layer stays at all for the rainfall platform depends on the persistence ticket (rainfall feed has none; Locations needs it).
6. `backend/app/locations/*` weather half is T/P/RH (see Group A table). Spec decision.
7. `docker-compose.yml`: timescaledb/pgadmin/`DEFAULT_DATA_SOURCE`/MQTT env are legacy-shaped; Render does not use compose (Render config is not in the repo).
8. `python-multipart` (only legacy `/api/upload` uses `UploadFile`): needed again if the new platform accepts uploaded rainfall series; keep or re-add at that slice.

## 5. Python dependencies in `requirements.txt`

Import evidence is from `grep` over `backend/`, `scripts/`, `tests/`, `ml-service/` (ml-service has its own dependency files, so it does not constrain the root file).

| Package | Used by (root app) | Verdict |
|---|---|---|
| `torch` (>=2.2,<2.6) | `ml/legacy_tiers/tier2_temporal_ml.py`, `ml/stages/stage2_ensemble.py`, `scripts/train_models.py`, 2 tests | Legacy only. Drop. (ml-service has its own torch pin.) |
| `shap` | `ml/legacy_tiers/tier5_explain.py`, `ml/stages/stage5_explain.py` | Legacy only. Drop. Pulls `numba` and `llvmlite` (measured here: numba 27 MB, llvmlite 122 MB, shap 3 MB). |
| `pyod` | `ml/stages/stage2_ensemble.py` | Legacy only. Drop. |
| `paho-mqtt` | `sources/physical_source.py` only | Legacy only. Drop. |
| `statsmodels` | `ml/stages/stage1_stl.py` only | Legacy only. Drop (57 MB here). |
| `scikit-learn` | `ml/legacy_tiers/{preprocessor,tier2_point_ml}.py`, `ml/stages/{stage2,stage5}`, `scripts/train_models.py`; and a lazy `KDTree` import in `spatial/consensus.py:83` | Legacy only once `haversine_distance_km` is moved (rainfall does not call `SpatialIndex`). Drop. |
| `scipy` | `ml/legacy_tiers/tier3_multivariate.py` only (plus sklearn's own dependency) | Legacy only. Drop. |
| `joblib` | legacy tiers, `stage2_ensemble`, `scripts/train_models.py` | Legacy only. Drop. |
| `pandas` (not on your list) | `ml/*`, `services/{ingestion,phase2,phase3}`, `simulator/*`; no use in `locations` or `rainfall` | Legacy only. Drop. `numpy` stays (`locations/normals.py`, `locations/qc.py`, `spatial/consensus.py`). |
| `psycopg2-binary` | **No import anywhere** (grep for `psycopg` hits only `requirements.txt` and strings in two scripts/compose using `asyncpg` URLs) | Unused already. Drop independent of legacy removal. |
| `asyncpg` | No import; it is the driver selected by URL `postgresql+asyncpg://` in `docker-compose.yml` and two verify scripts. SQLAlchemy loads it by URL | Needed only if the Postgres/Timescale path is kept. Depends on the persistence ticket. Not a legacy-code dependency but a deployment option. |
| `websockets` (and `uvicorn[standard]`) | no import; `api/websocket.py` uses FastAPI's WebSocket, served by uvicorn's websocket implementation | Can go with `api/websocket.py` unless a streaming view is kept. Low weight. |
| `python-multipart` | FastAPI form/file upload for `/api/upload` | See Group C item 8. |
| Keep | `fastapi, uvicorn, pydantic, pydantic-settings, sqlalchemy, aiosqlite, numpy, httpx` (httpx used by rainfall), `pytest, pytest-asyncio` | |

### Effect on image size and Render free-tier memory

- **Measured (Windows, Python 3.13, this machine):**
  - Importing `backend.app.main` as it is on `main` takes the process to about **440 MB RSS** before serving a request (baseline interpreter 18 MB). It loads `torch`, `shap`, `pyod`, `sklearn`, `scipy`, `pandas`. `statsmodels` and `paho` are not imported at startup (lazy or unreachable).
  - Importing only the shared stack (`fastapi`, `sqlalchemy`, `httpx`, `numpy`, `api.locations`, `spatial.consensus`) gives about **87 MB RSS**, none of the heavy libraries loaded.
  - Installed package sizes here: torch 465 MB (CPU build on Windows), llvmlite 122 MB, scipy 106 MB, pandas 66 MB, statsmodels 57 MB, sklearn 42 MB, numba 27 MB, numpy 33 MB.
- **Estimate, not measured:** on Linux, `pip install torch` pulls the CUDA build with `nvidia-*` wheels by default; that makes the backend image multiple gigabytes. Dropping the legacy dependencies should take the Python layer to a few hundred MB (fastapi, sqlalchemy, httpx, numpy, uvicorn). Render's free web service is documented as 512 MB RAM (taken from Render's published plan limits, not re-verified in this session), so 440 MB at import plus the running data source manager, SQLite and request handling sits at the limit, while about 90 MB leaves headroom. Verify with a real Linux build and `docker stats`/Render metrics when the slice is done.
- Also remove `COPY scripts/` and the `models/` volume from the container once those are gone.

## 6. Suggested removal order (app and tests stay green at each step)

Each step ends with `pytest tests` green (remaining tests) and the app starting. Steps are ordered so a deletion happens only after its last importer is gone.

0. **Baseline.** Merge `isd-rainfall-feed` into the working branch (rainfall is needed first). Fix or consciously drop the three collection errors (`test_noaa_importer`, `test_noaa_benchmark` `NameError: Any`; `test_config_stress` needs `pydantic_settings` installed). Record pass counts.
1. **Decouple shared code from legacy (no deletions).**
   a. Move `haversine_distance_km` to `backend/app/spatial/geo.py` (or `rainfall/geo.py`); re-export from `consensus.py`; point `rainfall/service.py`, `rainfall/catalog.py` at the new location.
   b. Move `weather_union_stations.csv` to `backend/app/rainfall/data/`; update `CATALOG_PATH` and `scripts/build_weather_union_catalog.py`.
   c. Rewrite `tests/conftest.py`: remove `from scripts.train_models import ...` and the autouse `ensure_trained_models`; keep `init_db` and `async_client`. (Tests that need models, the legacy ML tests, still run only if they request trained models themselves: move that fixture into a `tests/legacy` conftest or mark them, so the legacy tests keep passing until they are deleted in step 3.)
2. **Remove leaf non-code and frontend consumers.** Delete `hardware/`, `sketchfab*.html`, `frontend/test_sf.js`, `run.bat`, `reports/`, legacy docs (B8 list). In the frontend, make `App.tsx` mount only `LocationsView` (plus the new rainfall view when it exists), then delete the 11 legacy components, `SettingsCenter`, `SystemConfigurationContext`, `NetworkMap`, `StationGlobe3D`, `websocket.ts`, legacy parts of `api.ts` and `types/index.ts`; then `three`/`@types/three` from `package.json` and `public/assets/earth`. Frontend goes first because it is the consumer of the legacy API; the backend still serves the routes meanwhile, so nothing breaks.
3. **Remove backend legacy from the top down** (consumers before providers), deleting each group together with its tests:
   1. `main.py`: stop mounting `api_router`/`ws_router`, remove `simulation_service` and `data_source_manager` from the lifespan. Then delete `api/routes.py`, `api/websocket.py` and tests `test_api, test_alert_drilldown_forensics, test_event_station_integrity, test_task4_triage, test_phase4_api_websocket, test_task4_parity, test_sanity (rewrite to hit an existing route), test_task4_sqlite (rewrite to Locations/rainfall)`.
   2. `sources/` (keep nothing; CSV already moved) with tests `test_data_sources, test_city_presets, test_live_city_switch_integration, test_phase1_replay_pipeline`, the hardware and `scripts/stream_telemetry_feed.py`.
   3. `services/` with tests `test_ingestion, test_m3_stress, test_task4_perf, test_phase2_ml_core, test_phase3_explain_heal_health`, `health/`, `schemas/`.
   4. `simulator/` with tests `test_simulator, test_m1_challenger, test_scenario_stress_durations` and scripts `generate_datasets.py, generate_replay_dataset.py, audit_tool.py`.
   5. `ml/` and `models/` with tests `test_tier*, test_fusion, test_pipeline, test_alert_xai, test_empirical_m2_challenge, test_m2_adversarial_stress, test_phase4_canonical_if`, and scripts `train_models.py, benchmark_*, empirical_stress_test.py, verify_*, test_anomaly_detection.py`.
   6. Rest of `spatial/consensus.py` and `test_spatial_consensus.py`; `db/repositories.py`; legacy tables in `db/models.py`; trim `init_db` (migrations, hypertable, seed). Drop the 6 legacy tables (existing `skyguard.db` files keep orphaned tables; harmless on SQLite, note for Render persistent disks).
   7. `data/*.csv`, remaining legacy `scripts/`, `test_noaa_*`, `test_edge_cases` placeholder, `openspec` legacy specs.
4. **Trim configuration.** `config.py` legacy settings, `.env.example`, `docker-compose.yml` (drop pgadmin/timescale or keep per the persistence decision), `Dockerfile.backend` (`COPY scripts/`, build-essential not needed once nothing compiles).
5. **Drop dependencies last**, in this order, each followed by a full test run and an app start: `torch`, `shap` (+ numba/llvmlite fall away), `pyod`, `statsmodels`, `paho-mqtt`, `scikit-learn`, `scipy`, `joblib`, `pandas`, `psycopg2-binary` (could be done at any step, it is unused), `websockets` (with the WebSocket route gone). Keep `asyncpg` until persistence is decided; keep `python-multipart` if the new platform takes uploads. Do the dependency edits only after the imports are gone, otherwise the app breaks on import.
6. **Rewrite docs** (README, ARCHITECTURE, GOAL, PROJECT, AGENTS sections 1 and 6, TODO, TEST_INFRA) per the spec.

## 7. Counts

- Legacy-only backend Python modules: ml 21, services 6, sources 8, schemas 3, simulator 5, health 1, api routes 2 (`routes.py`, `websocket.py`), db 2 (`models.py`, `repositories.py`, partial `database.py`), spatial 2 (partial `consensus.py` + `__init__`) = about 50 files; about 9,600 lines in `backend/` in total on `main`.
- Routes: 33 REST route decorators + 1 WebSocket legacy; 6 tables legacy; 4 tables (Locations) shared.
- Frontend: 11 legacy views, 2 globe/map widgets, 1 settings screen, 1 context, 1 websocket client; 1 shared view (`LocationsView`).
- Tests: 40 files, 351 collected (3 files fail at collection in this environment). Shared 21 (plus 27 on the branch); legacy-only about 322; generic-but-coupled 7 collected (plus `test_config_stress` 9 not collected here); placeholder 1.
- Scripts: 19 of 22 legacy. Data: 9 CSVs legacy. Hardware: 1 folder (3 files). Models: 8 artifacts. Docs: about 27 legacy topics, 8 UI docs for the legacy dashboard, 9 mixed root docs.
- Dependencies: of the 9 named in the ticket, 7 are legacy-only in the root app (`torch, shap, pyod, paho-mqtt, statsmodels, scikit-learn, scipy`); `psycopg2-binary` is unused anywhere; `asyncpg` depends on the Postgres decision. Extra candidates: `joblib`, `pandas`, `websockets`.
