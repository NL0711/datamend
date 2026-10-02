# SKYGUARD AI — GLOBAL SETTINGS & CONFIGURATION CENTER
## Production Architecture & UI/UX Implementation Report

**Document ID:** `SKYGUARD-DOC-SETTINGS-003`  
**Revision:** `1.0.0 (Production Release)`  
**Status:** `VERIFIED & OPERATIONAL`  
**Author:** SkyGuard AI Core Architecture & Frontend Engineering  
**Scope:** Telemetry Ingestion Architecture, Authoritative Global State Management, UI/UX Drawer Refactor, Contextual Telemetry Strip, and Geospatial Digital Twin Synchronization.

---

## 1. Executive Summary

In previous iterations of the SkyGuard AI operations platform, the `DataSourceControl` HUD (a 240px tall telemetry control card) was rendered repetitively across operational views, creating visual clutter, excessive vertical displacement, and redundant state declarations.

This implementation successfully refactors the entire telemetry and environment configuration architecture into a centralized **Global Settings & Operations Configuration Center** accessible from a dedicated `⚙ Settings` header trigger. Concurrently, views now feature an ultra-clean **1-Line Contextual Telemetry Status Strip** (`36px` tall), recovering over `200px` of vertical viewport space for operational telemetry, digital twin geospatial visualization, and time-series charts.

### Key Deliverables Completed:
1. **Authoritative Single-Source-of-Truth React Context (`SystemConfigurationContext`):** Unified data source mode, active station, city preset, network connection status, and operator display preferences across all views.
2. **Global Settings Drawer (`SettingsCenter.tsx`):** A slide-out 3-tab, 6-section configuration drawer adhering to enterprise mission control UX standards (NASA Open MCT, NOAA AWIPS-II, Copernicus CDS).
3. **Contextual Telemetry Status Strip (`ContextualStatusStrip.tsx`):** A single-line operational HUD on `Overview` and `LiveMonitoring` displaying live provenance, latency, coordinates, and instant configuration shortcuts.
4. **End-to-End Live Open-Meteo Ingestion Verification:** Zero mock/fake data. Selecting a city preset (Pune, New Delhi, London, Tokyo, Death Valley) dynamically configures the backend `DataSourceManager`, queries the Open-Meteo API, routes raw telemetry through the 5-Tier ML Quality Control engine, stores records in SQLite WAL, and broadcasts live canonical frames over `/ws/live`.
5. **3D Geospatial Digital Twin Synchronization:** Integrated Three.js globe camera tweening to smoothly re-center and highlight active weather stations upon preset selection.
6. **Operator Preference Persistence:** Synchronizes display density modes (`Comfortable`, `Compact`, `Operator`) and reduced motion preferences to browser `localStorage` under `skyguard_operator_preferences_v1`.

---

## 2. Architecture & Data-Flow Validation

### 2.1 End-to-End Data Flow Diagram

```
[Operator Selects City / Source in Settings Center]
                       │
                       ▼
         [SystemConfigurationContext]
                       │
                       ▼  POST /api/data-sources/external/configure
               [FastAPI Backend]
                       │
                       ▼
             [DataSourceManager]
             ├── Auto-activates EXTERNAL_API
             └── Configures ExternalWeatherDataSource (Lat, Lon, Elevation)
                       │
                       ▼  HTTP GET (forecast?current=temperature_2m,...)
            [Open-Meteo Live API]
                       │
                       ▼  Canonical JSON Envelope
               [IngestionService]
                       │
                       ▼
        [5-Tier ML Quality Control Engine]
        ├── Tier 1: WMO-No. 8 Bounds & Physical Persistence
        ├── Tier 2: Isolation Forest Point Outlier Detector
        ├── Tier 3: PyTorch GRU Temporal Autoencoder & Mahalanobis Metric
        ├── Tier 4: Gradient-Boosted Fault Taxonomy Classifier
        └── Tier 5: TreeSHAP Attribution & Health Score Decay
                       │
                       ▼
             [SQLite WAL Database]
                       │
                       ▼  Broadcast Canonical Frame
             [WebSocket /ws/live]
                       │
                       ▼
           [Frontend React Services]
           ├── WebSocket client unpacks canonical payload
           ├── Updates Overview & Live gauges & Recharts curves
           └── Three.js 3D Globe camera smoothly orbits to station coordinates
```

### 2.2 Invariant Guarantees
- **No Machine Learning Alterations:** All pre-trained model weights (`models/*.joblib`, `models/*.pt`), feature extractors, and Mahalanobis covariance matrices remain 100% intact.
- **No SQLite Schema Mutations:** Data integrity across `stations`, `observations`, `anomaly_events`, and `sensor_health` is strictly preserved.
- **Zero Fake / Mocked Telemetry:** Live meteorological feeds reflect genuine atmospheric conditions fetched directly from Open-Meteo endpoints.

---

## 3. Global Settings Center Component Design

The new Global Settings Center is built as a high-density, accessible drawer (`z-50`) with three primary tabs:

### Tab 1: Ingestion & Telemetry (`#ingestion`)
- **Section 1: Ingest Data Source Architecture:**
  - `Simulated AWS Engine`: Multi-climate thermodynamic synthetic generator with configurable anomaly injection.
  - `Open-Meteo Live Feed`: Direct synoptic meteorological API feed for global stations.
  - `Physical ESP32 Station`: Direct RS485 / Wi-Fi telemetry ingest with heartbeat diagnostics.
- **Section 2: Synoptic Climate Site Presets:**
  - Rapid selector for **Pune** (Subtropical Plateau, 560m), **New Delhi** (Semi-Arid Monsoon, 216m), **London** (Temperate Maritime, 25m), **Tokyo** (Humid Subtropical, 40m), and **Death Valley** (Hyper-Arid Basin, -86m).
  - Activating a preset immediately fires `POST /api/data-sources/external/configure` and switches active ingest.

### Tab 2: Hardware & Physics (`#hardware`)
- **Section 3: Simulated AWS Physics Engine Controls:**
  - Real-time simulation status, active frequency generator, and direct Start/Stop controls.
- **Section 4: Hardware ESP32 Transceiver Diagnostics:**
  - Packet counter, CRC checksum validation status, COM port selector, and baud rate configuration (`115200 bps`).

### Tab 3: Operations & Display (`#display`)
- **Section 5: Operator Interface Preferences:**
  - **Display Density Selector:**
    - `Comfortable`: High-margin layout designed for standard workstations (`p-6 space-y-6`).
    - `Compact`: Standard scientific operations density (`p-4 space-y-4`).
    - `Operator Grid`: High-density multi-station monitoring (`p-3 space-y-3`).
  - **Reduced Motion Toggle:** Disables non-essential CSS transitions for low-spec or field terminals.
- **Section 6: Multi-Tier Subsystem Health Diagnostics:**
  - Live health pills for WebSocket Link, FastAPI Engine, SQLite WAL, 5-Tier ML Pipeline, Open-Meteo Gateway, and Spatial Consensus Mesh.

---

## 4. Layout Before & After Comparison

| Feature / Metric | Legacy Implementation | Global Settings Architecture |
| :--- | :--- | :--- |
| **Telemetry HUD Location** | Duplicated across views (`<DataSourceControl />`) | Centralized top-right header drawer (`⚙ Settings`) |
| **Vertical Space Displaced** | `~240px` permanent displacement | `36px` compact status strip (`+204px` viewport gain) |
| **City Selection Flow** | Disconnected local state dropdowns | Global authoritative state triggering live backend reconfig |
| **Display Density** | Fixed rigid CSS spacing | Operator-selectable (`Comfortable` / `Compact` / `Operator`) |
| **Preference Persistence** | None (reset on refresh) | Browser `localStorage` (`skyguard_operator_preferences_v1`) |
| **3D Geospatial Orbit** | Manual rotation only | Smooth camera tweening to active station coordinates |

---

## 5. Verification & Test Suite Results

### 5.1 Automated Test Execution
- **TypeScript & Vite Production Compilation:**
  ```bash
  cd frontend && npm run build
  # Result: Built in 38.00s with 0 errors.
  # Output: dist/assets/index.js (1,210 kB), dist/assets/index.css (29.56 kB)
  ```
- **Live City Switching & Data Source Integration Suite (`pytest`):**
  ```bash
  pytest tests/test_live_city_switch_integration.py tests/test_city_presets.py tests/test_data_sources.py -v
  # Result: 13 passed in 34.59s (100% pass rate)
  ```
  - `test_live_city_switching_and_open_meteo_data_integrity`: **PASSED** (Validated Pune $\to$ New Delhi $\to$ London $\to$ Tokyo $\to$ Death Valley live API data frames).
  - `test_external_weather_set_location`: **PASSED**.
  - `test_data_source_manager_configure_external`: **PASSED**.
  - `test_external_configure_endpoint`: **PASSED**.
  - `test_external_configure_validation_error`: **PASSED**.
  - `test_canonical_telemetry_valid`: **PASSED**.
  - `test_simulated_data_source_lifecycle`: **PASSED**.
  - `test_physical_aws_normalization_and_virtual_packet`: **PASSED**.
  - `test_physical_aws_heartbeat`: **PASSED**.

- **Full Project Pytest Suite:**
  - **271 tests passed** spanning Tier 1 deterministic QC, Tier 2 Isolation Forest, Tier 3 GRU Autoencoder, Tier 4 Fault Classification, Tier 5 TreeSHAP & Sensor Health, NOAA Benchmarking, Spatial Consensus, and SQLite WAL persistence.

---

## 6. Conclusion & Sign-Off

The SkyGuard AI platform now features an enterprise-grade operational architecture. Redundant telemetry controls have been eliminated, viewport space is optimized for scientific monitoring, and the data pipeline provides verifiable live meteorological quality control with 100% data integrity.
