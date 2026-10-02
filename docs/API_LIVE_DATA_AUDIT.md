# SkyGuard AI — API & Live Transport Audit

## 1. Overview
This document audits every REST endpoint and WebSocket interface exposed by the backend (`backend/app/api/routes.py` and `backend/app/api/websocket.py`), mapping consumer frontend modules, backend data sources, database queries, and live transport behaviors.

---

## 2. API Endpoint Matrix

| Endpoint | HTTP Method | Frontend Consumer | Backend Service / Module | Database Query / Action | Data Classification | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/api/health` | GET | Status Indicator | `routes.health_check()` | Connection ping | Internal Status | 🟢 Working |
| `/api/stations` | GET | `OverviewView`, `LiveMonitoringView`, `AlertCenterView`, `SensorHealthView` | `routes.get_stations()` | `SELECT * FROM stations` | Real DB Records | 🟢 Working |
| `/api/stations/{id}` | GET | `EventDetailView` | `routes.get_station()` | `SELECT * FROM stations WHERE station_id=?` | Real DB Record | 🟢 Working |
| `/api/observations` | GET | `DataExplorerView` | `routes.get_observations()` | `SELECT * FROM observations ORDER BY timestamp DESC LIMIT ? OFFSET ?` | Real DB Records | 🟢 Working |
| `/api/observations` | POST | External REST / Simulator | `ingestion_service.ingest_observation()` | `INSERT INTO observations`, `INSERT INTO anomaly_events`, `INSERT INTO sensor_health` | Simulated / External Real Live Data | 🟢 Working |
| `/api/anomalies` | GET | `OverviewView`, `AlertCenterView`, `EventDetailView` | `routes.get_anomalies()` | `SELECT * FROM anomaly_events WHERE ... ORDER BY timestamp DESC` | Real DB Records | 🟢 Working |
| `/api/anomalies/stats` | GET | `OverviewView`, `AlertCenterView` | `analytics_service.get_anomaly_stats()` | Aggregates `anomaly_events` over last $N$ hours | Real DB Calculation | 🟢 Working |
| `/api/health/fleet` | GET | `OverviewView`, `SensorHealthView` | `analytics_service.get_fleet_health()` | Aggregates latest `sensor_health` for all active stations | Real DB Calculation | 🟢 Working |
| `/api/health/station/{id}`| GET | `SensorHealthView` | `analytics_service.get_station_health()` | Queries latest `sensor_health` & historical trend | Real DB Calculation | 🟢 Working |
| `/api/metrics` | GET | `OverviewView` | `analytics_service.get_system_metrics()` | Queries SQLite table row counts, latency stats, uptime | Real DB Calculation | 🟢 Working |
| `/api/simulator/status` | GET | `OverviewView` | `simulation_service.get_status()` | Inspects `SimulationService` singleton state | Internal Runtime State | 🟢 Working |
| `/api/simulator/start` | POST | `OverviewView` | `simulation_service.start()` | Launches background asyncio telemetry generation loop | Control Trigger | 🟢 Working |
| `/api/simulator/stop` | POST | `OverviewView` | `simulation_service.stop()` | Cancels background asyncio telemetry generation task | Control Trigger | 🟢 Working |
| `/api/simulator/inject` | POST | `AnomalyInjectorUI` | `simulation_service.inject_fault()` | Pushes fault injection spec into `SimulationService.injection_queue` | Interactive Telemetry Disturbances | 🟢 Working |
| `/api/upload` | POST | `DataExplorerView` | `ingestion_service.process_batch()` | Sequentially ingests CSV file rows through 5-tier pipeline into DB | Batch Data Processor | 🟢 Working |
| `/ws/live` | WebSocket | `App.tsx` (`TelemetryStreamClient`) | `websocket.py` (`websocket_endpoint`) | `ConnectionManager.connect()`, receives live broadcast packets | Real-Time Push Stream | 🟢 Working |

---

## 3. WebSocket Real-Time Transport Specification

- **Endpoint URL:** `ws://localhost:8899/ws/live` (proxied via Vite on `ws://localhost:5199/ws/live`)
- **Transport Mechanism:** Starlette / FastAPI WebSocket handler managed by `ConnectionManager`.
- **Broadcast Trigger:** When `simulation_service` generates a new telemetry step (every 1.5 seconds) or an external `POST /api/observations` request occurs, `ingestion_service` executes 5-tier inference, writes to SQLite, and immediately broadcasts the resulting `InferenceResult` JSON payload over all active WebSocket connections.
- **Frontend Reconnection & Resiliency:** `TelemetryStreamClient` (`frontend/src/services/websocket.ts`) incorporates automatic exponential backoff reconnection (initial delay: 1,000 ms, max delay: 30,000 ms).
