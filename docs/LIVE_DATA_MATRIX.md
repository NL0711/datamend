# SkyGuard AI — Dashboard Live Data Matrix

## 1. Overview
This matrix audits every visual UI component across all 8 dashboard views, identifying the exact source, transport protocol, backend service, database/ML origin, classification level, and evidence of connectivity.

---

## 2. Dashboard View Element Audit Matrix

| Dashboard Feature / UI Element | Visual View | Source File | Transport | Backend Service / Endpoint | DB / ML Origin | Classification Level | Status | Verified Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Fleet Health Index Card** | Overview | `OverviewView.tsx` | REST (5s poll) | `analytics_service` / `/api/health/fleet` | SQLite `sensor_health` average | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Queries DB table `sensor_health`, returns `average_health_score` |
| **24h Flagged Events Card** | Overview | `OverviewView.tsx` | REST (5s poll) | `analytics_service` / `/api/anomalies/stats` | SQLite `anomaly_events` count | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Aggregates DB rows over last 24 hours |
| **Pipeline Latency Card** | Overview | `OverviewView.tsx` | REST (5s poll) | `analytics_service` / `/api/metrics` | Ingestion latency timer array | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Returns `average_inference_latency_ms` and `p95` |
| **Total Observations Card**| Overview | `OverviewView.tsx` | REST (5s poll) | `analytics_service` / `/api/metrics` | SQLite `observations` row count | LEVEL 2 (Simulated Live Data) | 🟢 REAL | `SELECT count(*) FROM observations` |
| **Active Stations Table** | Overview | `OverviewView.tsx` | REST (5s poll) | `routes.py` / `/api/stations` | SQLite `stations` table | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Displays 4 default stations with live SHI badges |
| **Recent Alerts List** | Overview | `OverviewView.tsx` | REST (5s poll) | `routes.py` / `/api/anomalies?limit=6` | SQLite `anomaly_events` table | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Fetches 6 latest flagged anomalies with severity badges |
| **Live Temperature Gauge**| Live Monitoring | `LiveMonitoringView.tsx` | WebSocket | `websocket.py` / `/ws/live` | `diurnal_generator` + 5-tier pipeline | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Streams live `temperature` field every 1.5s |
| **Live Pressure Gauge** | Live Monitoring | `LiveMonitoringView.tsx` | WebSocket | `websocket.py` / `/ws/live` | `diurnal_generator` + 5-tier pipeline | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Streams live `pressure` field every 1.5s |
| **Live Humidity Gauge** | Live Monitoring | `LiveMonitoringView.tsx` | WebSocket | `websocket.py` / `/ws/live` | `diurnal_generator` + 5-tier pipeline | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Streams live `humidity` field every 1.5s |
| **Pipeline Verdict Banner** | Live Monitoring | `LiveMonitoringView.tsx` | WebSocket | `websocket.py` / `/ws/live` | `AnomalyFusionEngine` & `FaultClassifier`| LEVEL 2 (Simulated Live Data) | 🟢 REAL | Displays `is_anomaly`, `severity`, `classification`, `score` |
| **Temperature Stream Area Chart**| Live Monitoring | `LiveMonitoringView.tsx` | WebSocket | `websocket.py` / `/ws/live` | `historyBuffer` state array (60 steps) | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Recharts dynamic curve updating on every WS packet |
| **Pressure & Humidity Charts**| Live Monitoring | `LiveMonitoringView.tsx` | WebSocket | `websocket.py` / `/ws/live` | `historyBuffer` state array (60 steps) | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Recharts synchronized curves updating on every WS packet |
| **Incident Log Table** | Alert Center | `AlertCenterView.tsx` | REST (Server Filter)| `routes.py` / `/api/anomalies` | SQLite `anomaly_events` table | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Supports filtering by severity, station, classification |
| **Alert Detail Drawer** | Alert Center | `AlertCenterView.tsx` | Local Select | Selected `AnomalyEvent` item | SQLite `anomaly_events` JSON fields | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Displays TreeSHAP summary, observed channels, operator recommendation |
| **Station Health Index Gauges**| Sensor Health | `SensorHealthView.tsx` | REST (On Station) | `analytics_service` / `/api/health/station/{id}` | SQLite `sensor_health` EMA calculations | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Displays SHI (0-100), degradation risk rating, TTF hours |
| **Health & Drift Trend Chart**| Sensor Health | `SensorHealthView.tsx` | REST | `analytics_service` / `/api/health/station/{id}` | `recent_history` array from `sensor_health` | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Recharts health index & component drift over time |
| **Forensic 5-Tier Decomposition**| Event Detail | `EventDetailView.tsx` | REST | `routes.py` / `/api/anomalies` | `tier_scores` JSON column in `anomaly_events` | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Displays Tier 1 QC, Tier 2 Point/Temporal, Tier 3 score |
| **Telemetry History Table**| Data Explorer | `DataExplorerView.tsx` | REST (Paginated) | `routes.py` / `/api/observations` | SQLite `observations` table | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Paginated table with station & date range filters |
| **Batch CSV Drag & Drop Uploader**| Data Explorer | `DataExplorerView.tsx` | REST (Multipart) | `ingestion_service` / `/api/upload` | Batch 5-tier pipeline + DB insert | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Uploads CSV, executes 5-tier inference, returns results |
| **Fault Preset Trigger Buttons**| Anomaly Injector UI | `AnomalyInjectorUI.tsx` | REST (POST) | `simulation_service` / `/api/simulator/inject` | `SimulationService.injection_queue` | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Pushes fault into queue; next WS stream shows disturbance |
| **TreeSHAP Feature Weight Bars**| Explainability Viewer| `ExplainabilityViewer.tsx`| REST | `routes.py` / `/api/anomalies` | `explanation` JSON column (`contributing_features`) | LEVEL 2 (Simulated Live Data) | 🟢 REAL | Visualizes TreeSHAP attributions per channel |

---

## 3. Data Classification Summary
* **Level 1 (Real External Live Data):** Not active (no physical hardware attached).
* **Level 2 (Simulated Live Data):** 100% of telemetry and AI diagnostic flow. Generator generates realistic diurnal curves, 5-tier pipeline executes in Python, SQLite stores records, FastAPI WebSocket streams telemetry, and React visualizes live data.
* **Level 3 (Replayed Historical Data):** Available via CSV upload in Data Explorer.
* **Level 4 (Mock Data):** 0%. All UI numbers originate from backend computations.
* **Level 5 (Static UI Data):** 0%. No hardcoded numbers exist in dashboard views.
