# SkyGuard AI — Three-Source Telemetry Architecture

## 1. System Overview

SkyGuard AI supports three interchangeable real-time telemetry sources:
1. **Simulated AWS Telemetry** (Diurnal Solar Radiation, Magnus-Tetens Thermodynamics, Barometric Tides)
2. **Real External Weather Data Feed** (Open-Meteo REST API)
3. **Real Physical AWS Sensor Data** (ESP32 + Bosch BME280 Sensor via MQTT)

All three sources normalize into a single **Canonical Telemetry Contract** before passing into the 5-Tier Machine Learning Quality Control, Anomaly Detection, and Sensor Health Pipeline.

---

## 2. End-to-End Data Flow Diagram

```
+---------------------------------------------------------------------------------------------------+
|                                      DATA SOURCE ADAPTER LAYER                                    |
|                                                                                                   |
|  +---------------------------+  +-------------------------------+  +---------------------------+  |
|  |       SIMULATED AWS       |  |     EXTERNAL WEATHER API      |  |       PHYSICAL AWS        |  |
|  |  DiurnalGenerator         |  |  Open-Meteo REST Client       |  |  ESP32 + Bosch BME280     |  |
|  |  AnomalyInjector          |  |  HTTP Polling (60s cycle)     |  |  MQTT Telemetry Stream    |  |
|  |  (backend/app/sources/    |  |  (backend/app/sources/        |  |  (backend/app/sources/    |  |
|  |   simulated_source.py)    |  |   external_source.py)         |  |   physical_source.py)     |  |
|  +-------------+-------------+  +---------------+---------------+  +-------------+-------------+  |
|                |                                |                                |                |
+----------------+--------------------------------+--------------------------------+----------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                 CANONICAL TELEMETRY CONTRACT                                      |
|  - Schema: backend/app/schemas/canonical.py (CanonicalTelemetry)                                 |
|  - Fields: station_id, timestamp, temperature (°C), pressure (hPa), humidity (%),                 |
|            source_type, source_id, provider, device_id, coordinates, data_quality, received_at    |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                     DATA SOURCE MANAGER                                           |
|  - Coordinator: backend/app/sources/manager.py (DataSourceManager)                                |
|  - Manages active source selection, non-blocking stream switching, and stale data monitoring      |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                   FASTAPI INGESTION SERVICE                                       |
|  - Module: backend/app/services/ingestion_service.py                                              |
|  - Validates schemas, enforces per-station concurrency locks, and dispatches to ML engine         |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                 5-TIER MACHINE LEARNING PIPELINE                                  |
|  - Orchestrator: backend/app/ml/pipeline.py (SkyGuardPipeline)                                    |
|  - Tier 1: Deterministic QC Physical Range (-40 to 60°C), Rate-of-Change, Stuck Sensor            |
|  - Tier 2: Point Outlier Isolation Forest & Temporal PyTorch GRU Sequence Autoencoder             |
|  - Tier 3: Multivariate Magnus-Tetens Dew Point Consistency & Chi-Square Mahalanobis Distance    |
|  - Tier 4: Anomaly Fusion Engine & 7-Class Fault Taxonomy Random Forest Classifier                |
|  - Tier 5: Exponential Moving Average Sensor Health Index (SHI 0-100) & TreeSHAP Attributions     |
+---------------------------------------------------------------------------------------------------+
                                                  |
                     +----------------------------+----------------------------+
                     |                                                         |
                     v                                                         v
+------------------------------------------+             +------------------------------------------+
|            SQLITE WAL DATABASE           |             |           WEBSOCKET BROADCASTER          |
|  - File: skyguard.db                     |             |  - Endpoint: /ws/live                    |
|  - Tables: observations, anomaly_events, |             |  - Payload: InferenceResultSchema with   |
|            sensor_health, stations       |             |    live source metadata and provenance   |
+------------------------------------------+             +------------------------------------------+
                     |                                                         |
                     +----------------------------+----------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                                 REACT OPERATIONAL DASHBOARD                                       |
|  - UI Component: frontend/src/components/DataSourceControl.tsx                                    |
|  - Features: 1-click source selector, live connection badges, data freshness timers, live charts  |
+---------------------------------------------------------------------------------------------------+
```

---

## 3. Comparison of the Three Data Sources

| Dimension | 🟡 SIMULATED AWS | 🌐 EXTERNAL API | 📟 PHYSICAL AWS |
| :--- | :--- | :--- | :--- |
| **Origin** | Internal `DiurnalGenerator` | Open-Meteo REST API | ESP32 + Bosch BME280 Sensor |
| **Transport** | In-memory Asyncio Coroutines | HTTPS GET Request (JSON) | MQTT TCP (Port 1883 / 8883) |
| **Default Station** | `AWS-001` (Delhi Observatory) | `PUNE-EXT-001` (Pune Center) | `AWS-ESP32-001` (Hardware Node) |
| **Sampling Interval**| 1.5 seconds | 60 seconds (configurable) | 3 seconds (configurable in firmware) |
| **Anomaly Injection**| Full support via UI Injector | Natural meteorological anomalies | Physical stimulus / virtual packet |
| **Failure State** | `STOPPED` / `ERROR` | `DEGRADED` / `DISCONNECTED` | `DISCONNECTED` (>30s timeout) |
| **Stale Threshold** | > 30 seconds | > 150 seconds | > 30 seconds |
