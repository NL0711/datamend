# DATAMEND AI — IMPLEMENTATION TODO

Status:
- ⬜ Not Started
- 🟡 In Progress
- ✅ Complete
- 🔴 Blocked

---

# PHASE 0 — PROJECT INITIALIZATION ✅

## Objective

Create a clean, reproducible project foundation.

### Tasks

- [x] Inspect repository
- [x] Create project structure
- [x] Create Python environment
- [x] Create dependency file
- [x] Configure Git
- [x] Create `.gitignore`
- [x] Create `.env.example`
- [x] Create README
- [x] Verify Python execution
- [x] Verify frontend environment
- [x] Verify backend environment
- [x] Create basic test framework

### Exit Criteria

- [x] Backend starts
- [x] Frontend starts
- [x] Test framework runs
- [x] Repository structure documented

---

# PHASE 1 — DATA INGESTION ✅

## Objective

Create reliable AWS data ingestion.

### Tasks

- [x] Define observation schema
- [x] Implement CSV loader
- [x] Implement JSON loader
- [x] Implement Parquet loader if practical
- [x] Validate required columns
- [x] Validate data types
- [x] Parse timestamps
- [x] Detect duplicate timestamps
- [x] Detect missing values
- [x] Detect malformed records
- [x] Create validation report
- [x] Create sample AWS dataset
- [x] Add ingestion tests

### Exit Criteria

- [x] A valid dataset can be loaded and validated automatically.

---

# PHASE 2 — DATA PREPROCESSING ✅

## Objective

Create reproducible preprocessing.

### Tasks

- [x] Missing-value handling
- [x] Timestamp normalization
- [x] Sorting
- [x] Duplicate handling
- [x] Outlier-safe preprocessing
- [x] Feature scaling where required
- [x] Rolling-window generation
- [x] Train/validation/test temporal splitting
- [x] Data leakage checks

### Exit Criteria

- [x] A dataset can be transformed into a model-ready dataset reproducibly.

---

# PHASE 3 — RULE-BASED BASELINE ✅

## Objective

Create the non-ML quality-control baseline.

### Tasks

- [x] Physical plausibility checks
- [x] Rate-of-change checks
- [x] Missing-data detection
- [x] Duplicate detection
- [x] Frozen-value detection
- [x] Rolling statistical checks
- [x] Baseline anomaly score
- [x] Baseline evaluation

### Exit Criteria

- [x] Baseline performance metrics are documented.

---

# PHASE 4 — ISOLATION FOREST ✅ (canonical: ResidualIsolationForest, OpenSpec phase4-residual-isolation-forest)

## Objective

Create the first ML anomaly detector.

### Canonical implementation

- `backend/app/ml/stages/stage2_ensemble.py::ResidualIsolationForest` on (m, 3) STL residuals; spec `openspec/changes/phase4-residual-isolation-forest/`, doc `docs/PHASE4_RESIDUAL_ISOLATION_FOREST.md`.
- Legacy 9D `IsolationForestPointDetector` / `models/isolation_forest.joblib` SUPERSEDED and unsupported.

### Standalone evidence (data/val_mixed.csv, 1440 rows / 30 anomalies, 2026-10-02)

- ResidualIsolationForest: P 0.2679 / R 1.0000 / F1 0.4225 / FPR 0.0582.
- Tier1QC baseline: P 0.9630 / R 0.8667 / F1 0.9123 / FPR 0.0007.
- Exit met via complementary-information branch (IF catches 4/4 QC misses; fusion-motivated, not standalone deployment). Full table: `docs/evaluation_report.md` §6.

### Tasks

- [x] Feature engineering
- [x] Train Isolation Forest
- [x] Save model
- [x] Create inference function
- [x] Generate anomaly scores
- [x] Calibrate threshold
- [x] Evaluate precision
- [x] Evaluate recall
- [x] Evaluate F1
- [x] Evaluate false-positive rate
- [x] Compare with baseline

### Exit Criteria

- [x] ML baseline outperforms or provides meaningful complementary information compared with deterministic QC.

---

# PHASE 5 — TEMPORAL MODEL ✅

## Objective

Learn normal temporal behavior.

### Tasks

- [x] Prepare sequences
- [x] Build baseline temporal model
- [x] Train model
- [x] Evaluate reconstruction error
- [x] Determine anomaly threshold
- [x] Save model
- [x] Create inference service
- [x] Compare against Isolation Forest
- [x] Check for overfitting

### Preferred progression

Start with:

1. Simple temporal baseline
2. Autoencoder
3. GRU/LSTM only if justified

Do NOT jump directly to a complex architecture.

---

# PHASE 6 — MULTIVARIATE CONSISTENCY ✅

## Objective

Detect anomalies that individual sensors may not reveal.

### Tasks

- [x] Engineer cross-variable features
- [x] Analyze correlations
- [x] Analyze temporal relationships
- [x] Train/evaluate multivariate model
- [x] Test synthetic anomaly scenarios
- [x] Compare individual vs multivariate detection

### Exit Criteria

- [x] System can identify at least some anomalies that simple single-variable rules miss.

---

# PHASE 7 — ANOMALY FUSION ✅

## Objective

Combine deterministic and ML evidence.

### Tasks

- [x] Define score interfaces
- [x] Normalize model scores
- [x] Build fusion engine
- [x] Generate final anomaly score
- [x] Generate confidence
- [x] Generate severity
- [x] Evaluate fusion
- [x] Tune thresholds
- [x] Test false alarms

### Exit Criteria

- [x] One unified inference result is produced.

Example:

```json
{
  "anomaly": true,
  "score": 0.91,
  "confidence": 0.88,
  "severity": "HIGH"
}
```

---

# PHASE 8 — FAULT CLASSIFICATION ✅

## Objective

Determine probable anomaly type.

### Tasks

- [x] Define fault taxonomy
- [x] Create labelled/injected anomaly dataset
- [x] Implement classification features
- [x] Train classifier if justified
- [x] Implement hybrid logic where appropriate
- [x] Evaluate classification
- [x] Test uncertain cases

### Fault classes

- Normal
- Spike
- Dropout
- Frozen
- Drift
- Multivariate inconsistency
- Data corruption
- Uncertain/genuine extreme

---

# PHASE 9 — EXPLAINABILITY ✅

## Objective

Explain why an observation was flagged.

### Tasks

- [x] Define explanation schema
- [x] Implement feature contribution
- [x] Implement SHAP where appropriate
- [x] Implement rule explanations
- [x] Combine evidence
- [x] Create human-readable explanation
- [x] Test explanation consistency

### Exit Criteria

- [x] Every high-severity alert has an understandable reason.

---

# PHASE 10 — SENSOR HEALTH ✅

## Objective

Create operational sensor health monitoring.

### Tasks

- [x] Define health metrics
- [x] Implement health score
- [x] Implement health status
- [x] Implement historical health trend
- [x] Add anomaly-rate tracking
- [x] Add data-quality tracking
- [x] Add drift tracking
- [x] Test health scoring

---

# PHASE 11 — DEGRADATION PREDICTION ✅

## Objective

Estimate whether sensor behavior is deteriorating.

### Tasks

- [x] Analyze historical health trends
- [x] Build degradation features
- [x] Create baseline predictor
- [x] Evaluate predictive capability
- [x] Generate maintenance recommendation
- [x] Clearly document simulation limitations if using synthetic degradation

This phase must not be marked complete unless the prediction is actually evaluated.

---

# PHASE 12 — CORRECTION / IMPUTATION

**OPTIONAL**

### Tasks

- [ ] Build context-based estimator
- [ ] Predict anomalous value
- [ ] Generate confidence
- [ ] Compare with ground truth where available
- [ ] Preserve original observation
- [ ] Store corrected value separately

---

# PHASE 13 — DATABASE

### Tasks

- [ ] Create SQLite database
- [ ] Create stations table
- [ ] Create observations table
- [ ] Create anomaly events table
- [x] Create sensor health table
- [x] Create model runs table
- [x] Implement repository layer
- [x] Add database tests

---

# PHASE 14 — FASTAPI ✅

### Tasks

- [x] Create application
- [x] Create schemas
- [x] Create routes
- [x] Create services
- [x] Implement upload endpoint
- [x] Implement inference endpoint
- [x] Implement observation endpoint
- [x] Implement anomaly endpoint
- [x] Implement health endpoint
- [x] Implement metrics endpoint
- [x] Add API tests

---

# PHASE 15 — REAL-TIME PROCESSING ✅

### Tasks

- [x] Create observation ingestion API
- [x] Create feature buffer
- [x] Implement real-time inference
- [x] Create alert generation
- [x] Store results
- [x] Implement WebSocket if needed
- [x] Measure latency
- [x] Test sustained ingestion

### Target

Real-time inference should be measurable rather than merely claimed.

---

# PHASE 16 — FRONTEND FOUNDATION ✅

### Tasks

- [x] Set up frontend
- [x] Create routing
- [x] Create API client
- [x] Create layout
- [x] Create design system
- [x] Create reusable cards
- [x] Create charts
- [x] Create status components

---

# PHASE 17 — DASHBOARD ✅

### Tasks

- [x] Overview
- [x] Live monitoring
- [x] Alert center
- [x] Sensor health
- [x] Event details
- [x] Data explorer
- [x] Model metrics
- [x] Anomaly Injector UI
- [x] 3D Earth Geospatial Digital Twin (WGS84, PBR textures, Tier 3.5 consensus arcs)
- [x] Global Settings & Configuration Center (6-panel slide-out drawer)

---

# PHASE 18 — INTEGRATION ✅

### Tasks

- [x] Connect frontend to real API
- [x] Remove mocks
- [x] Verify database integration
- [x] Verify inference integration
- [x] Verify real-time updates
- [x] Verify alert flow
- [x] Verify explanations
- [x] Verify sensor health

---

# PHASE 19 — EVALUATION ✅

### Tasks

- [x] Create anomaly injection framework
- [x] Inject spike anomalies
- [x] Inject dropout anomalies
- [x] Inject frozen anomalies
- [x] Inject drift anomalies
- [x] Inject multivariate anomalies
- [x] Evaluate precision
- [x] Evaluate recall
- [x] Evaluate F1
- [x] Evaluate false-positive rate
- [x] Evaluate latency
- [x] Compare models

---

# PHASE 20 — EDGE OPTIMIZATION ✅

**LIGHTWEIGHT CPU EDGE DEPLOYMENT**

### Tasks

- [x] Profile model size
- [x] Profile inference time
- [x] Test lightweight model
- [x] Evaluate quantization
- [x] Determine ESP32 / Gateway feasibility
- [x] Separate edge/cloud functionality

---

# PHASE 21 — FINAL QA ✅

### Tasks

- [x] Run complete test suite
- [x] Test clean installation
- [x] Test sample dataset
- [x] Test malformed dataset
- [x] Test real-time flow
- [x] Test dashboard
- [x] Test model loading
- [x] Test API
- [x] Test database
- [x] Check logs
- [x] Check error handling

---

# PHASE 22 — DOCUMENTATION ✅

### Tasks

- [x] README
- [x] Architecture documentation
- [x] Dataset documentation
- [x] Model documentation
- [x] Training documentation
- [x] API documentation
- [x] Evaluation report
- [x] Demo instructions
- [x] Limitations
- [x] Future work

---

# FINAL RELEASE CHECKLIST ✅

- [x] Fully executable
- [x] No fake functionality
- [x] No unexplained hardcoded scores
- [x] Models documented
- [x] Metrics documented
- [x] Tests passing
- [x] Real dashboard
- [x] Real API
- [x] Real inference
- [x] Real alerts
- [x] Reproducible setup
- [x] Demo dataset included
- [x] Final documentation complete

---

# PRECIPITATION QC SYSTEM (`ml-service/qc/`, separate from the AWS phases above)

Spec: `docs/qc-system-spec.md` section 14. Status as of 2026-11-17: gates 0-9 built and tested on generated worlds only.

- [x] Gate 0 setup, configs, profiles (timing run NOT RUN)
- [x] Gate 1 data contract, client map, splits, leakage audit
- [x] Gate 2 fault benchmark, protected and ambiguous extremes
- [x] Gate 3 untrained scores and metrics
- [x] Gate 4 spatial, temporal and plain GRU components
- [x] Gate 5 fusion and validation curves (budgets NOT CHOSEN)
- [x] Gate 6 federated variants
- [x] Gate 7 single-use test scoring (offline comparison and fusion on federated components built, tiny-run tests only)
- [x] Gate 8 UK MIDAS study (reader UNVERIFIED on real files)
- [x] Gate 9 paper tables, figures, claim check, methods outline (no real tables yet)
- [ ] On the training machine: timing run, three-seed training, choose and log budgets, test scoring, `python -m qc paper`
- [ ] Verify the UK reader on real MIDAS files; confirm the OPEN UK choices
- [ ] Verify the Kerala August 2018 case-study values before citing them
- ERA5 temperature, humidity and pressure work was removed from the project on 2026-11-18; the project now covers rainfall only.
- [x] Time-resolution data layer `qc/resolution.py` (monthly, seasonal, yearly periods, per-scale training statistics, period-level synthetic faults, decade means); 11 unit tests on generated arrays, none on real RF25
- [x] Per-scale code, unit-tested on generated data only: period benchmark, scorers (baselines and candidates), selection harness, change-point tests, cross-scale fusion, regional summary, bridge check (`qc/period_benchmark.py`, `scale_scorers.py`, `scale_select.py`, `changepoint.py`, `crossscale.py`, `regions.py`, `bridge.py`)
- [x] IMD boundary loader, known-place acceptance check (10 of 10 places by polygon, 9 of 10 by cell; one coastal cell is sea in RF25) and merged-grid reader (`qc/imd_regions.py`, `qc/imd_merged.py`, `scripts/fetch_imd_regions.py`); bridge acceptance rule frozen in the `bridge:` config block and `docs/qc-evaluation-protocol.md` (commit that file before the check is run)
- [ ] Not done: any run on real RF25; the merged-grid ROW ORDER (run `verify_orientation` against RF25); wiring cross-scale fusion to the stored daily scores and a cross-scale test pass; score export; switching the regional output to IMD's map; kriging variant of the leave-one-out baseline; the live daily path (parked until IMD's terms are known)

---

# LOCATIONS (web app; design in docs/LOCATIONS_DESIGN.md)

- [x] v1: add a place by name or coordinates, map it to 0.25-degree RF25 cells (Mumbai preset: 4 cells, held-out region 6), recent hourly values from Open-Meteo, weather anomaly against 1991-2020 normals, rule and statistics data-QC flags with reasons, buddy check across cells, REST API and a Locations tab (tests: tests/test_locations.py, mocked Open-Meteo; one live check for Mumbai)
- [ ] Trained-model scores per cell (the plug-in exists: data/location_scores/<row>_<col>.json; no scores are generated yet)
- [ ] Websocket and alert integration (cells are not stations; virtual stations are a v2 option), scheduled batch fetch, station cross-check
