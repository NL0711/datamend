# SkyGuard AI — Live System Architecture & Data Flow Map

## 1. Executive Architecture Summary

SkyGuard AI is a real-time, explainable AI quality-control, fault classification, and sensor health platform for Automatic Weather Stations (AWS). The system ingests primary atmospheric observations:
- **Temperature (°C)**
- **Atmospheric Pressure (hPa)**
- **Relative Humidity (%)**

Along with timestamps and station metadata.

```
+-----------------------------------------------------------------------------------+
|                            AWS DATA SOURCE ENGINE                                |
|  - Diurnal Sinusoidal Generator (backend/simulator/diurnal_generator.py)         |
|  - Programmatic Anomaly Injector (backend/simulator/anomaly_injector.py)          |
+-----------------------------------------------------------------------------------+
                                          |
                                          v  (POST /api/observations or Ingest Loop)
+-----------------------------------------------------------------------------------+
|                             FASTAPI INGESTION ENGINE                              |
|  - Router: backend/app/api/routes.py                                              |
|  - Ingestion Service: backend/app/services/ingestion_service.py                   |
|  - Simulation Loop: backend/app/services/simulation_service.py                   |
+-----------------------------------------------------------------------------------+
                                          |
                                          v  (Passes Dict to Pipeline)
+-----------------------------------------------------------------------------------+
|                        5-TIER ML PIPELINE ORCHESTRATOR                            |
|  - Orchestrator: backend/app/ml/pipeline.py (SkyGuardPipeline)                    |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | STEP 1: Preprocessing & Buffer (backend/app/ml/preprocessor.py)            |  |
|  | - DataPreprocessor: StandardScaler, 30-step sliding window, delta & std   |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|  +-----------------------------------------------------------------------------+  |
|  | STEP 2: Tier 1 Quality Control (backend/app/ml/tier1_qc.py)                |  |
|  | - Tier1QC: Physical bounds (-40 to 60°C), rate-of-change, zero-variance    |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|  +-----------------------------------------------------------------------------+  |
|  | STEP 3: Tier 2 Point & Temporal ML (backend/app/ml/tier2_point_ml.py/temp) |  |
|  | - IsolationForestPointDetector (models/isolation_forest.joblib)             |  |
|  | - TemporalAutoencoderDetector (models/temporal_autoencoder.pt - PyTorch GRU)|  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|  +-----------------------------------------------------------------------------+  |
|  | STEP 4: Tier 3 Multivariate Consistency (backend/app/ml/tier3_multivariate)|  |
|  | - Tier3MultivariateDetector: Clausius-Clapeyron Dew Point & Mahalanobis    |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|  +-----------------------------------------------------------------------------+  |
|  | STEP 5: Anomaly Score Fusion (backend/app/ml/fusion.py)                    |  |
|  | - AnomalyFusionEngine: Convex weights, hard overrides, confidence score     |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|  +-----------------------------------------------------------------------------+  |
|  | STEP 6: Tier 4 Fault Classification (backend/app/ml/tier4_classifier.py)   |  |
|  | - FaultClassifier: SPIKE, DRIFT, FROZEN, DROPOUT, MULTIVARIATE, MET_EXTREME  |  |
|  +-----------------------------------------------------------------------------+  |
|                                         |                                         |
|  +-----------------------------------------------------------------------------+  |
|  | STEP 7 & 8: Tier 5 Health & Explainability                                  |  |
|  | - SensorHealthEngine (backend/app/ml/tier5_health.py): SHI EMA (0-100)     |  |
|  | - ExplainabilityEngine (backend/app/ml/tier5_explain.py): TreeSHAP & text  |  |
|  +-----------------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------------+
                                          |
                     +--------------------+--------------------+
                     |                                         |
                     v                                         v
+------------------------------------------+ +--------------------------------------+
|          SQLITE PERSISTENCE LAYER        | |      WEBSOCKET & REST BROADCASTER     |
| - DB Engine: backend/app/db/database.py  | | - WS Endpoint: /ws/live            |
| - ORM Models: backend/app/db/models.py   | | - Connection Mgr: websocket.py     |
| - Tables: observations, anomaly_events,  | | - TelemetryStreamClient (Frontend) |
|   sensor_health, stations, model_runs    | | - REST API: backend/app/api/routes |
+------------------------------------------+ +--------------------------------------+
                                          |                    |
                                          +----------+---------+
                                                     |
                                                     v
+-----------------------------------------------------------------------------------+
|                        REACT OPERATIONAL DASHBOARD (FRONTEND)                     |
| - App Master Layout & WS Ingestion: frontend/src/App.tsx                          |
| - REST API Client: frontend/src/services/api.ts                                   |
| - Views: Overview, Live Monitoring, Alert Center, Sensor Health, Event Detail,   |
|   Data Explorer, Anomaly Injector UI, Explainability Viewer                       |
+-----------------------------------------------------------------------------------+
```

---

## 2. Component Mapping & Module Tracing

| Flow Stage | Responsible Module / File | Primary Class / Function | Inputs | Outputs |
| :--- | :--- | :--- | :--- | :--- |
| **Data Generation** | `backend/simulator/diurnal_generator.py` | `DiurnalGenerator.generate()` | `StationConfig`, `DiurnalParameters` | `pd.DataFrame` with diurnal T, P, RH |
| **Anomaly Injection** | `backend/simulator/anomaly_injector.py` | `AnomalyInjector.inject_*()` | Base DataFrame, parameters | Labeled DataFrame with injected faults |
| **Simulation Loop** | `backend/app/services/simulation_service.py` | `SimulationService._run_loop()` | `interval_seconds` | Periodic telemetry dicts |
| **Ingestion Entry** | `backend/app/services/ingestion_service.py` | `IngestionService.ingest_observation()` | Telemetry Observation Dict | `InferenceResult` + DB Persistence |
| **Preprocessing** | `backend/app/ml/preprocessor.py` | `DataPreprocessor.update()` | Raw T, P, RH values | Scaled vectors & 30-step tensors |
| **Tier 1 QC** | `backend/app/ml/tier1_qc.py` | `Tier1QC.evaluate()` | Raw channel values & history | `Tier1QCResult` (hard/soft flags) |
| **Tier 2 Point ML** | `backend/app/ml/tier2_point_ml.py` | `IsolationForestPointDetector.predict_score()`| Scaled feature vector | Point anomaly score `[0, 1]` |
| **Tier 2 Temporal ML**| `backend/app/ml/tier2_temporal_ml.py` | `TemporalAutoencoderDetector.predict_score()`| 30-step sequence tensor | Reconstruction MSE score `[0, 1]` |
| **Tier 3 Multivariate**| `backend/app/ml/tier3_multivariate.py` | `Tier3MultivariateDetector.evaluate()` | Raw T, P, RH values | Clausius-Clapeyron & Mahalanobis score |
| **Score Fusion** | `backend/app/ml/fusion.py` | `AnomalyFusionEngine.fuse()` | Tier 1-3 scores | `FusionResult` (fused score, confidence) |
| **Fault Classifier** | `backend/app/ml/tier4_classifier.py` | `FaultClassifier.classify()` | Tier outputs & sliding buffer | `ClassificationResult` (fault class) |
| **Sensor Health** | `backend/app/ml/tier5_health.py` | `SensorHealthEngine.update()` | Fused score, fault history | SHI (0-100), status, degradation risk |
| **Explainability** | `backend/app/ml/tier5_explain.py` | `ExplainabilityEngine.explain()` | Feature vector, tier flags | TreeSHAP weights & rationale summary |
| **DB Persistence** | `backend/app/db/repositories.py` | `ObservationRepository.create_with_inference()`| Observation & Inference schemas| SQLite rows inserted in WAL DB |
| **WebSocket Push** | `backend/app/api/websocket.py` | `ConnectionManager.broadcast()` | JSON-serialized `InferenceResult` | Broadcast to all active browser clients |
| **Frontend State** | `frontend/src/App.tsx` | `TelemetryStreamClient.onTelemetry` | WS JSON messages | React state `historyBuffer` (60 steps) |
| **Visualization** | `frontend/src/components/*` | React Functional Components | `historyBuffer` & REST queries | Live Recharts, gauges, & tables |
