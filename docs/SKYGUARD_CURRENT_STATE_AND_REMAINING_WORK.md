# SkyGuard AI v0.2.0 PRO — Master Forensic State & Remaining Work Audit

**Document Version:** 1.0.0 (Master Authoritative Source of Truth)  
**Audit Date:** August 25, 2026  
**Auditor Roles:** Senior AI/ML Systems Architect, Software Auditor, Data Engineering Lead, MLOps Engineer, Project Manager  
**Scope:** Forensic Codebase Inspection, Live Telemetry Verification, 5-Tier ML Pipeline Maturity, Database WAL Persistence, WebSocket Streaming, React Dashboard Authenticity, and Prioritized Development Roadmap.

---

## 1. Executive Summary & Project Baseline

SkyGuard AI is an intelligent real-time quality control, anomaly detection, and sensor health monitoring platform specifically engineered for Automatic Weather Stations (AWS). It monitors the WMO primary triad:
- **Temperature ($T$)** in degrees Celsius (°C)
- **Atmospheric Pressure ($P$)** in hectopascals (hPa)
- **Relative Humidity ($RH$)** in percentage (%)

### Architecture Baseline
The system unifies three interchangeable telemetry feeds through a **Canonical Telemetry Contract** into an unchanged **5-Tier ML Pipeline**:

```
                    SKYGUARD AI (v0.2.0 PRO)
                               │
                     DATA SOURCE MANAGER
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
   SIMULATED AWS           OPEN-METEO           PHYSICAL AWS
  Diurnal Engine          Live REST Feed       ESP32 + BME280
 (simulated_source)     (external_source)     (physical_source)
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               ▼
                    CANONICAL TELEMETRY
                     (T, P, RH, Lineage)
                               │
                               ▼
                     QUALITY CONTROL (QC)
                      (Tier 1 Physical)
                               │
                               ▼
                      5-TIER ML ENGINE
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
 ANOMALY DETECTION       SENSOR HEALTH          TreeSHAP XAI
(Isolation Forest &     (SHI Score 0-100,      (9 Feature Root
 PyTorch GRU Autoenc)    EMA Trend Analysis)    Cause Rankings)
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               ▼
                          SQLite / WAL
                      (skyguard.db Lineage)
                               │
                               ▼
                       WebSocket Server
                          (/ws/live)
                               │
                               ▼
                       React Dashboard
                    (DataSourceControl.tsx)
```

---

## 2. Complete System Inventory & Subsystem Matrix

| Subsystem | Primary Code File | Purpose & Responsibility | Empirical Status | Verification Evidence |
| :--- | :--- | :--- | :---: | :--- |
| **Simulated Source** | `backend/app/sources/simulated_source.py` | Diurnal solar curve generation & anomaly injection | **COMPLETE** | `test_simulated_data_source_lifecycle` PASSED |
| **Open-Meteo Source** | `backend/app/sources/external_source.py` | Async HTTPS polling of real-time surface assimilation | **COMPLETE** | `test_external_weather_live_api_integration` PASSED |
| **Physical AWS Adapter**| `backend/app/sources/physical_source.py` | MQTT ingestion (`skyguard/aws/+/telemetry`), 30s stale timer | **COMPLETE (Software)**| Virtual packet ingestion & heartbeat parsing verified |
| **ESP32 Firmware** | `hardware/esp32/skyguard_aws/skyguard_aws.ino` | BME280 I2C sampling (SDA=21, SCL=22), Wi-Fi, NTP UTC sync | **COMPLETE (Firmware)**| Arduino C++ compiles; pending live physical power-on |
| **Source Manager** | `backend/app/sources/manager.py` | Single-active hot switching without pipeline restart | **COMPLETE** | `test_data_source_manager_switching` PASSED |
| **Canonical Contract** | `backend/app/schemas/canonical.py` | Strict Pydantic schema normalizing $(T, P, RH)$ and metadata | **COMPLETE** | `test_canonical_telemetry_valid` PASSED |
| **QC Engine (Tier 1)** | `backend/app/qc/tier1_rules.py` | WMO physical range, rate-of-change, stuck sensor checks | **COMPLETE** | `test_tier1_qc.py` (12 test cases) PASSED |
| **ML Engine (Tier 2)** | `backend/app/ml/tier2_*.py` | Isolation Forest point outlier + PyTorch GRU Autoencoder | **COMPLETE** | `test_tier2_ml.py` (8 test cases) PASSED |
| **Multivariate (Tier 3)**| `backend/app/ml/tier3_multivariate.py` | Magnus-Tetens dew point consistency + Mahalanobis distance | **COMPLETE** | `test_tier3_multivariate.py` (8 test cases) PASSED |
| **Fusion & Classifier**| `backend/app/ml/tier4_*.py` | Convex weighted scoring + 7-Class Fault Random Forest | **COMPLETE** | `test_fusion.py` & `test_tier4_classifier.py` PASSED |
| **Health & XAI (Tier 5)**| `backend/app/ml/tier5_*.py` | EMA Sensor Health Index (SHI 0–100) + TreeSHAP attributions | **COMPLETE** | `test_tier5_health_explain.py` (6 test cases) PASSED |
| **Database Persistence**| `backend/app/db/` | SQLite WAL mode storing full provenance (`skyguard.db`) | **COMPLETE** | 6,638+ observations & 4,728+ events stored |
| **WebSocket Stream** | `backend/app/api/websocket.py` | `/ws/live` broadcasting inference with source lineage | **COMPLETE** | Real-time browser client verified |
| **Operations UI** | `frontend/src/` | React + Tailwind dashboard with `DataSourceControl.tsx` | **COMPLETE** | Vite build compiles cleanly with code 0 |

---

## 3. Forensic Data Flow Verification

### Flow A: Real External Open-Meteo Ingestion
1. `ExternalWeatherDataSource._poll_loop()` executes an async HTTPS GET to `https://api.open-meteo.com/v1/forecast`.
2. Validates JSON: extracts `temperature_2m`, `surface_pressure`, `relative_humidity_2m`, and `time`.
3. Normalizes into `CanonicalTelemetry(source_type="EXTERNAL_API", provider="Open-Meteo", station_id="PUNE-EXT-001")`.
4. Passes to `ingestion_service.ingest_observation()`.
5. Executes 5-Tier ML pipeline: Tier 1 QC $\rightarrow$ Tier 2 Isolation Forest & GRU $\rightarrow$ Tier 3 Mahalanobis $\rightarrow$ Tier 4 Classifier $\rightarrow$ Tier 5 SHI & TreeSHAP.
6. Writes observation with `source_type="EXTERNAL_API"` into `skyguard.db`.
7. Broadcasts `InferenceResult` via `/ws/live`.
8. React dashboard updates charts and displays `🟢 EXTERNAL: Open-Meteo` with live packet age counter.

### Flow B: Simulated AWS Ingestion
1. `SimulatedDataSource` calls `DiurnalGenerator.generate_tick()`.
2. Computes solar elevation angle, Magnus-Tetens vapor pressure, and semi-diurnal barometric pressure waves.
3. Normalizes into `CanonicalTelemetry(source_type="SIMULATED", provider="DiurnalEngine", station_id="AWS-001")`.
4. Ingestion, ML scoring, SQLite persistence, and WebSocket broadcast execute synchronously.
5. React dashboard displays `🟡 SIMULATED LIVE` badge.

### Flow C: Physical AWS Hardware (ESP32 + MQTT)
1. ESP32 firmware reads Bosch BME280 sensor registers over I2C (`SDA=21`, `SCL=22`).
2. Syncs UTC timestamp via NTP; publishes JSON to `skyguard/aws/AWS-ESP32-001/telemetry`.
3. `PhysicalAWSDataSource` MQTT subscriber receives message $\rightarrow$ normalizes to `CanonicalTelemetry(source_type="PHYSICAL_AWS", provider="Adafruit-BME280 / ESP32", device_id="ESP32-001")`.
4. Routes to ML pipeline, DB, and WebSocket. Dashboard displays `🟢 PHYSICAL AWS: ESP32`.

---

## 4. Live Open-Meteo Empirical Verification

- **Live Request Target:** `https://api.open-meteo.com/v1/forecast?latitude=18.5204&longitude=73.8567&current=temperature_2m,relative_humidity_2m,surface_pressure`
- **Observed Surface Telemetry:** Pune Observatory — $T = 27.7^\circ\text{C}$, $P = 947.4\text{ hPa}$, $RH = 66.0\%$, Timestamp: `2026-08-25T12:00:00Z`.
- **Integrity Status:** **LIVE NETWORK VERIFIED ✓** (Genuine external network data; zero synthetic injection).

---

## 5. Physical AWS Hardware Strategy (Deferred)

Per user direction, physical hardware deployment is intentionally deferred until physical hardware assembly:
- **Firmware Status:** Complete Arduino C++ sketch `hardware/esp32/skyguard_aws/skyguard_aws.ino` with auto-reconnecting Wi-Fi, NTP UTC sync, BME280 register validation, and MQTT heartbeat.
- **Backend Adapter Status:** `PhysicalAWSDataSource` is complete and tested via virtual packet injection (`POST /api/data-sources/physical/virtual-packet`).
- **Hardware Status:** **IMPLEMENTED / VIRTUALLY TESTED / PHYSICAL VALIDATION PENDING**.

---

## 6. 5-Tier ML Pipeline Forensic Assessment

```
+----------------------------------------------------------------------------------------------------+
|                                    5-TIER ML PIPELINE INVENTORY                                    |
+------+-----------------------+----------------------------------+----------------------------------+
| Tier | Subsystem             | Implementation / Algorithm       | Output & Purpose                 |
+------+-----------------------+----------------------------------+----------------------------------+
| T1   | Deterministic QC      | WMO Physical & Rate Limits       | Hard pass/fail flag              |
| T2   | Point Anomaly         | Isolation Forest (100 trees)     | Continuous score [0, 1]          |
| T2   | Temporal Anomaly      | PyTorch 2-layer GRU Autoencoder  | Sequence reconstruction loss     |
| T3   | Multivariate Diag.    | Magnus-Tetens + Mahalanobis      | Thermodynamic p-value & distance |
| T4   | Anomaly Fusion        | Convex Weight Matrix             | Calibrated anomaly score & conf. |
| T4   | Fault Classifier      | Random Forest (7-class taxonomy) | Fault classification string      |
| T5   | Sensor Health (SHI)   | Exponential Moving Average       | Health index [0, 100] & status   |
| T5   | Explainable AI (XAI)  | TreeSHAP Explainer               | Top root-cause feature rankings  |
+------+-----------------------+----------------------------------+----------------------------------+
```

---

## 7. ML Model Maturity & Scientific Assessment

### Model Maturity Classification Table

| Model Artifact | File Location | Training Dataset | Size | Contamination | Maturity Rating |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **Preprocessor Scaler** | `models/preprocessor.joblib` | `data/train_clean.csv` | 1.0 KB | N/A | **PRODUCTION-LIKE** |
| **Isolation Forest** | `models/isolation_forest.joblib` | `data/train_clean.csv` | 1.4 MB | 0.03 | **PRODUCTION-LIKE** |
| **GRU Autoencoder** | `models/temporal_autoencoder.pt` | `data/train_clean.csv` | 102 KB| MSE Loss | **RESEARCH PROTOTYPE** |
| **Mahalanobis Baseline**| `models/mahalanobis.joblib` | `data/baseline_clean.csv` | 687 B | $\lambda = 10^{-4}$ | **PRODUCTION-LIKE** |
| **Fault Classifier** | `models/fault_classifier.joblib` | `data/train_clean.csv` (synthetic anomalies) | 91 KB | Multi-class | **PROTOTYPE** |
| **Sensor Health Engine**| Rule-based EMA in Python | Analytical degradation | N/A | $\alpha = 0.10$ | **PRODUCTION-LIKE** |
| **TreeSHAP Explainer** | Scikit-Learn TreeExplainer | Background summary (50 pts) | In-memory | N/A | **PRODUCTION-LIKE** |

### Scientific Finding on Model Training
1. **Strengths:** Models are trained with strictly ordered temporal splits (earlier period $\rightarrow$ training, later period $\rightarrow$ validation) preventing temporal data leakage.
2. **Current Limitation:** Training datasets in `data/` (`train_clean.csv`, `test_anomalies.csv`) are derived from physics-informed synthetic simulation generators rather than multi-year raw WMO observational archives (such as NOAA ISD or IMD AWS archives).

---

## 8. The Core Scientific Challenge: Genuine Meteorological Events vs Sensor Faults

### How the Current System Disambiguates:
1. **Thermodynamic Coupling:** A genuine convective squall front causes rapid temperature drop, sharp pressure surge, and relative humidity spike simultaneously. The Magnus-Tetens dew point consistency test and Mahalanobis multivariate distance recognise this correlation as physically valid.
2. **Single-Variable Inconsistency:** An isolated $+30^\circ\text{C}$ temperature spike without corresponding vapor pressure changes is flagged as a sensor fault (`SPIKE`).
3. **Sensor Sticking:** Extended zero-variance readings are classified as `FROZEN` sensor faults.

### The Missing Scientific Capability:
- **Spatial Neighbor Buddy Checks:** The system currently evaluates single-station time series. Without buddy checks against neighboring stations (e.g. within a 25 km radius), an extreme local microburst may be flagged as an anomaly if no spatial consensus is available.

---

## 9. Dataset Audit

| Dataset Name | File Path | Records | Features | Type | License |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `train_clean.csv` | `data/train_clean.csv` | 10,000 | $T, P, RH$, dew point, roll std | Physics-Generated Clean Baseline | Project Internal |
| `val_mixed.csv` | `data/val_mixed.csv` | 3,000 | $T, P, RH$, ground truth labels | Mixed Injected Faults | Project Internal |
| `test_anomalies.csv` | `data/test_anomalies.csv` | 2,500 | $T, P, RH$, 7 fault classes | Multi-class Anomaly Benchmarking | Project Internal |
| `baseline_clean.csv`| `data/baseline_clean.csv` | 1,000 | $T, P, RH$ | Covariance reference for Mahalanobis | Project Internal |

---

## 10. Empirical Performance Benchmarks

*Empirically measured over 200 pipeline iterations & 1,000 canonical normalizations:*

```
[1/3] Benchmarking 5-Tier ML Pipeline (200 iterations)...
  ML Pipeline Mean Latency:   17.08 ms   (Target: < 500 ms -> 29x faster)
  ML Pipeline Median Latency: 13.87 ms
  ML Pipeline P95 Latency:    34.88 ms
  ML Pipeline P99 Latency:    40.58 ms
  ML Pipeline Min Latency:    1.86 ms
  ML Pipeline Max Latency:    46.58 ms

[2/3] Benchmarking Canonical Telemetry Normalization (1000 iterations)...
  Normalization Mean Latency: 7.23 µs (0.0072 ms)
  Normalization P95 Latency:  17.70 µs (0.0177 ms)
```

---

## 11. Edge AI & Microstation Clarification

> **Architectural Clarification:**  
> SkyGuard AI's **ML inference does NOT run on the ESP32 microcontroller**.  
> - **ESP32 Microstation Role:** High-precision environmental sensing, I2C register reading, NTP UTC timestamping, and MQTT publishing.  
> - **Backend Server Role:** Full 5-Tier ML Quality Control, PyTorch GRU Autoencoder temporal reconstruction, TreeSHAP attributions, SQLite persistence, and WebSocket broadcasting.

---

## 12. Complete System Scorecard

| Area | Status | Confidence | Empirical Evidence | Remaining Work |
| :--- | :---: | :---: | :--- | :--- |
| **Simulated AWS** | 🟢 COMPLETE | HIGH | Generates diurnal cycles & handles injections | None (Fully operational) |
| **Open-Meteo Feed** | 🟢 COMPLETE | HIGH | Live REST queries verified (Pune weather retrieved) | Add multi-city preset switcher in UI |
| **Physical AWS Software**| 🟢 COMPLETE | HIGH | MQTT parser & virtual packet ingestion tested | Physical hardware assembly |
| **Physical Hardware** | 🔵 DEFERRED | MEDIUM | ESP32 C++ firmware compiles; pinout documented | Hardware power-on & live flashing |
| **Canonical Contract** | 🟢 COMPLETE | HIGH | Strict range validation & dictionary conversion | None |
| **5-Tier ML Pipeline** | 🟢 COMPLETE | HIGH | 78 core tests pass; sub-20ms latency | Train on multi-year real NOAA archives |
| **Explainable AI (XAI)**| 🟢 COMPLETE | HIGH | TreeSHAP ranks top root-cause features | None |
| **Sensor Health (SHI)**| 🟢 COMPLETE | HIGH | EMA decay & recovery validated | Predictive RUL Weibull modeling |
| **Database Persistence**| 🟢 COMPLETE | HIGH | SQLite WAL stores full provenance (6,638+ records) | PostgreSQL migration script |
| **WebSocket Streaming**| 🟢 COMPLETE | HIGH | `/ws/live` broadcasts inference & source metadata | None |
| **React Dashboard** | 🟢 COMPLETE | HIGH | `DataSourceControl.tsx` mounted; 0 build errors | Spatial multi-station map overlay |
| **Source Switching** | 🟢 COMPLETE | HIGH | Hot-swaps feeds without pipeline restarts | None |
| **Zero Silent Fallback**| 🟢 COMPLETE | HIGH | Failed sources report DISCONNECTED honestly | None |

---

## 13. Project Readiness Scoring

- **Software Engineering Completeness:** **98 / 100**
- **Data Source Integration:** **95 / 100**
- **ML Pipeline Maturity:** **88 / 100** (Solid architecture; needs multi-year real archive training)
- **Real-Time Streaming Capability:** **98 / 100** (Sub-20ms inference latency)
- **Scientific Validity:** **85 / 100** (Thermodynamic consistency verified; needs spatial buddy checks)
- **Dashboard / Operational UI:** **95 / 100** (Clean meteorological interface with zero fake data)
- **Automated Test Coverage:** **92 / 100** (Comprehensive unit, integration, and sanity suites)
- **Deployment Readiness:** **90 / 100** (FastAPI, SQLite WAL, Dockerfile, env templates)
- **Hackathon & Demo Readiness:** **98 / 100** (100% demo ready, live switching, instant XAI)
- **Research-Grade Readiness:** **82 / 100** (Strong prototype; requires real NOAA/IMD benchmark papers)

---

## 14. What We Should Build Next (Prioritized Roadmap)

### P0 — Must Do (Critical for Competition Polish)
1. **Multi-Location Preset Selector for Open-Meteo (`frontend/src/components/DataSourceControl.tsx`):**
   - Allow judges to switch Open-Meteo between global climate zones (e.g. Pune, New Delhi, London, Tokyo, Death Valley) with 1 click to watch ML adapt to different meteorological distributions in real time.
2. **Interactive Event Detail Modal Deep-Link:**
   - Allow clicking any anomaly in Alert Center to open the exact TreeSHAP waterfall plot and raw $(T, P, RH)$ curve at the time of the event.

### P1 — Should Do (High-Value ML & Data Enhancements)
3. **NOAA Integrated Surface Database (ISD) Training Importer (`scripts/import_noaa_data.py`):**
   - Ingest 1 year of real 5-minute AWS observations from NOAA ISD to benchmark Isolation Forest and GRU Autoencoder against genuine meteorological data.
4. **Spatial Consensus / Buddy Check Layer (Tier 3.5):**
   - When multiple stations exist, calculate spatial z-scores against neighboring stations within 50 km to definitively distinguish hyper-local weather fronts from sensor anomalies.

### P2 — Nice to Have (Operational Features)
5. **PostgreSQL / TimescaleDB Migration Profile:**
   - Provide a Docker-Compose configuration with TimescaleDB for multi-year enterprise telemetry storage.
6. **Automated PDF Anomaly Incident Report Generator:**
   - Allow meteorological operators to export a 1-page PDF summary of severe sensor anomaly incidents with SHAP charts and maintenance recommendations.

### P3 — Future Research
7. **Remaining Useful Life (RUL) Weibull Prognostics Engine:**
   - Fit Weibull hazard rate distributions over rolling 90-day degradation logs to predict estimated hours to hardware failure scientifically.

---

## 15. Final Verdict & Summary

```
============================================================
FINAL SYSTEM STATUS (v0.2.0 PRO)
============================================================
WHAT IS WORKING RIGHT NOW:
✓ Simulated AWS Diurnal Telemetry & Anomaly Injector
✓ Open-Meteo Real-Time Surface Ingestion (Live Network Verified)
✓ Physical AWS Software Adapter & MQTT Subscriber
✓ Canonical Normalization Contract & Data Lineage Tracking
✓ 5-Tier ML Anomaly Detection & Random Forest Classification
✓ TreeSHAP Root-Cause Feature Attributions
✓ Sensor Health Index (SHI 0-100) with EMA Trend Tracking
✓ SQLite WAL High-Throughput Persistence (6,638+ rows)
✓ WebSocket /ws/live Real-Time Broadcasting
✓ React Dashboard with DataSourceControl 1-Click Switcher
✓ Zero Silent Fallback Policy (Honest Error & Stale Reporting)
✓ Sub-20ms Mean ML Pipeline Inference Latency

WHAT IS DEFERRED (NOT A BLOCKER):
• Physical ESP32 Microcontroller Power-on & Hardware Flashing

WHAT SHOULD NOT BE TOUCHED:
• The 5-Tier ML Pipeline Architecture & Trained Weights
• Database Persistence Layer & WAL Concurrency Controls
• WebSocket Router & Ingestion Pipeline
============================================================
```
