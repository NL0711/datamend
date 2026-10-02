# SKYGUARD AI — GLOBAL SETTINGS & CONFIGURATION ARCHITECTURE AUDIT

**Author:** Senior Product Designer & Full-Stack Systems Architect  
**Project:** SkyGuard AI — WMO-No. 8 Automatic Weather Station Quality Control System  
**Date:** August 2026  
**Status:** Audit Complete • Architecture Planned

---

## 1. Executive Summary

A comprehensive architectural audit was performed across frontend components, state management, API services, WebSocket streaming, and backend ingestion pipelines. 

### Key Findings:
1. **Vertical UI Bloat & Layout Clutter:**
   - `<DataSourceControl />` was rendered persistently inside `<main>` in `App.tsx`, occupying over 240px of vertical viewport across all 8 operational views.
   - This forced critical charts, the 3D Earth digital twin, incident triage lists, and forensic tables below the fold, resulting in "card overload" and severe vertical crowding.
2. **Scattered Configuration Controls:**
   - Controls for data source switching, Open-Meteo city selection, simulation starting/pausing, and physical hardware monitoring were coupled into one large visual HUD rather than a focused, purposeful Global Settings Center.
3. **State Authoritative Flow:**
   - The backend `DataSourceManager` is the true source of truth for telemetry ingestion. When reconfigured via `POST /api/data-sources/external/configure` or `POST /api/data-sources/select`, it updates the active source, coordinates, and station metadata, queries Open-Meteo or the generator, executes the 5-Tier ML Quality Control Pipeline, and broadcasts canonical packets over `/ws/live`.
   - The frontend needs a unified `SystemConfigurationContext` to govern:
     - Active Data Source (`SIMULATED`, `EXTERNAL_API`, `PHYSICAL_AWS`)
     - Selected Location / Synoptic Station Preset (`pune`, `delhi`, `london`, `tokyo`, `death_valley`)
     - Display Preferences (`comfortable`, `compact`, `operator` density; reduced motion)
     - Operator Defaults & Persistent Storage (`localStorage`)
     - Global Diagnostics & Link Status (WebSocket, REST, ML Engine, SQLite WAL)

---

## 2. Component & Data-Flow Audit Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER SETTINGS ACTION                              │
│              (Click ⚙ Settings Header Button or Contextual Strip)           │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               SETTINGS CENTER (Right-Side Drawer / Workspace)               │
│  - Section 1: Ingest Data Source (Simulated / Open-Meteo / Physical ESP32) │
│  - Section 2: Climate Synoptic Site (Pune / Delhi / London / Tokyo / DV)    │
│  - Section 3: Simulation Engine Parameters (Interval, Scenario, Controls)   │
│  - Section 4: Hardware Link Status & Serial / Socket Telemetry             │
│  - Section 5: Display Preferences (Density, Motion, Default View)          │
│  - Section 6: System Diagnostics & 5-Tier QC Pipeline Status                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              SystemConfigurationContext & configurationService              │
│       - LocalStorage Persistence for Operator UI Preferences                │
│       - REST API Dispatcher: POST /api/data-sources/external/configure      │
│       - REST API Dispatcher: POST /api/data-sources/select                  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       BACKEND DataSourceManager                             │
│       - Dynamic reconfiguration of ExternalWeatherDataSource                │
│       - Synchronous live query to Open-Meteo REST API                       │
│       - CanonicalTelemetry normalization -> IngestionService                │
│       - 5-Tier ML Quality Control Pipeline (WMO Hard QC, IF, GRU, XAI)      │
│       - SQLite WAL Database persistence                                     │
│       - WebSocket Broadcast (/ws/live)                                      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ALL FRONTEND OPERATIONAL CONSUMERS                       │
│  - Top Header: Compact Global Status Indicator [Open-Meteo • Delhi • LIVE]  │
│  - Level 2 Context Strip: 1-line provenance, freshness, and quick configure │
│  - 3D Geospatial Globe: WGS84 camera focus & consensus arcs                 │
│  - Live Monitoring: Real-time gauges, area charts, Dew Point math           │
│  - Overview, Alert Center, Sensor Health, Event Forensics, Data Explorer    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed File-by-File Inventory

| File Path | Current Role | Refactor Plan |
| :--- | :--- | :--- |
| `frontend/src/types/index.ts` | Type definitions for `DataSourceStatus`, `CityPreset`, `InferenceResult`. | Add `SystemConfiguration`, `DisplayDensity`, `OperatorPreferences`, `SystemHealthStatus` interfaces. |
| `frontend/src/context/SystemConfigurationContext.tsx` | *New* Global state context. | Create single authoritative React context managing active source, location, display preferences, and diagnostics. |
| `frontend/src/settings/SettingsCenter.tsx` | *New* Centralized drawer. | Modern slide-out drawer containing 6 structured configuration panels with zero visual clutter. |
| `frontend/src/components/ContextualStatusStrip.tsx` | *New* Compact 1-line HUD. | Replaces the bulky 240px `DataSourceControl` with a sleek 36px contextual status strip on views. |
| `frontend/src/App.tsx` | Root layout and router. | Remove persistent bulky `DataSourceControl`, wire `SystemConfigurationProvider`, add header `⚙ Settings` button with active status chip. |
| `frontend/src/components/DataSourceControl.tsx` | Old large HUD. | Deprecate or refactor into modular sub-panels inside `SettingsCenter`. |
| `frontend/src/design-system/components/StationGlobe3D.tsx` | 3D Earth digital twin. | Consume `SystemConfigurationContext` for active station and city coordinates. |
| `frontend/src/components/OverviewView.tsx` & `LiveMonitoringView.tsx` | Core operational views. | Remove repeated source selector, display compact contextual strip, maximize chart & map space. |

---

## 4. Integrity and Non-Destructive Invariants

- **ML Models Preserved:** No changes to `models/*.joblib`, `models/*.pt`, or inference weights.
- **Database & Schema Preserved:** SQLite schemas, tables, and WAL configurations remain 100% intact.
- **No Mock or Fake Data:** All weather parameters come strictly from live Open-Meteo queries, physical serial streams, or the deterministic diurnal simulation engine.
