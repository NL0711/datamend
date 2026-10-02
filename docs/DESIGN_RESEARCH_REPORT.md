# SKYGUARD AI — DESIGN RESEARCH & ARCHITECTURAL SPECIFICATION REPORT

**Target Platform:** SkyGuard AI — Scientific Quality-Control & Sensor Health Operations Platform  
**Target Domain:** Meteorological Operations, Automatic Weather Stations (AWS), Real-Time Quality Control (WMO-No. 8 / CIMO)  
**Document Status:** Approved Master Design Specification (v2.0)

---

## 1. Relevant SkyGuard References & Genesis

### Smart India Hackathon (SIH) 2026 Mandate
* **Sponsor:** Ministry of Earth Sciences (MoES), Government of India (Disaster Management Track).
* **Core Problem Statement:** Real-time automated anomaly detection and sensor quality control for Surface Automatic Weather Stations (AWS), monitoring:
  1. **Temperature (°C)** (Thermistor / RTD sensor)
  2. **Atmospheric Pressure (hPa)** (Piezoresistive / Resonant silicon barometer)
  3. **Relative Humidity (%)** (Capacitive thin-film polymer hygrometer)
* **Operational Need:** Distinguish between physical sensor faults (spikes, drift, frozen values, dropouts, multivariate thermodynamic violations) and genuine extreme meteorological events (synoptic cold fronts, convective storm cells, microbursts).
* **Explainability (XAI):** Calibrated confidence scoring with TreeSHAP feature attributions and 5-tier mathematical signal decomposition.

### Homonymous Products Identified (Out of Scope)
* **AccuWeather SkyGuard®:** Commercial severe weather warning service.
* **SkyGuard UAV / Airport Defense:** Drone detection / bird-strike radar.
* **Rheinmetall Oerlikon Skyguard:** Air defense radar.
* **NASA Space Apps SkyGuard:** Satellite air quality prototype.

---

## 2. Benchmark Analysis of Scientific & Enterprise Systems

### Scientific Meteorological Platforms
1. **NOAA Weather & Climate Toolkit (WCT):** High data density, raw matrix inspection, strict WMO flag semantics, polar/isoline slicing.
2. **NASA Worldview & Open MCT (JPL/Ames):** Unified temporal scrubbing ("Time Conductor"), synoptic sensor mimics, mission elapsed timers, dark slate (`#0C0D0E` / `#16181A`).
3. **ECMWF Climate Data Store (CDS) & Copernicus C3S:** Deep marine blues (`#0F2B48`), ensemble spread bands, anomaly deviation meters, structured methodological disclosure.
4. **Windy.com & MeteoBlue:** WebGL particle streamlines, high-density Meteograms (stacked temperature, pressure isobars, cloud heights), fluid layer switching.
5. **IBM Environmental Intelligence Suite (EIS) & DTN Weather Hub:** Operational action centers, threshold-breach countdowns, asset overlays on GIS layers.

### Enterprise Observability & Mission Control Systems
1. **Palantir Foundry / Gotham:** BlueprintJS design tokens (`#1C2127`, `#252A31`), border-defined spatial separation (`1px solid #383E47`), ontology object linking, zero gratuitous shadows.
2. **Datadog (DRUIDS):** Synchronized crosshair cursors across multi-timeseries panels, query value sparklines, threshold color floods.
3. **Grafana (Saga):** Modular panel system, uPlot 60fps time-series engine, discrete state timeline heatmaps.
4. **Bloomberg Terminal:** Brutalist zero-latency density, pure black background (`#000000`), amber tickers (`#FF9900`), strict monospaced tabular alignment.
5. **Linear:** 120fps micro-craft, subtle elevation layers, translucent borders (`rgba(255,255,255,0.08)`), keyboard-first shortcuts (`Cmd+K`).
6. **Aviation Weather (METAR/TAF):** Dual-presentation of raw ICAO strings and decoded parameters, strict flight-safety color rules (Green VFR, Blue MVFR, Red IFR, Magenta LIFR).

---

## 3. Synthesis: Patterns to Adopt vs. Patterns to Avoid

| Dimension | ❌ Anti-Patterns to AVOID | ✅ Mission-Control Patterns to ADOPT |
| :--- | :--- | :--- |
| **Color & Lighting** | Neon cyan borders everywhere; glowing cards; purple/magenta gradient backgrounds; cyber/hacker aesthetic. | Deep graphite & atmospheric navy canvas (`#080C14`, `#0D1322`); hairline dividers (`rgba(255,255,255,0.07)`); strictly semantic status colors. |
| **Layout & Rhythm** | Generic stacked cards; repetitive 4-card KPI rows without hierarchy; flat admin templates. | Command Center composition; visual anchor around an interactive 3D Station Earth Globe; progressive disclosure drawers. |
| **3D & Visualization** | Gimmicky spinning wireframes; video-game HUD overlays; FPS-dropping unoptimized particles. | Scientific 3D Earth Globe with WebGL hardware acceleration; lat/lon station nodes; elevation vectors; spatial consensus buddy links. |
| **Data & Metrics** | Isolated scalar numbers with no context; fake accuracy claims; hardcoded SHAP scores. | Physical values paired with rate-of-change ($\Delta T/\Delta t$), normal bounds, dew-point calculations, and 5-tier pipeline verification. |
| **Alerts & XAI** | Basic alert modals; unexplained anomaly scores; claiming "AI detected anomaly". | Forensic Incident Dossier; TreeSHAP force waterfalls; Weather vs Fault discrimination matrix; actionable operator SOP runbooks. |
| **Motion** | Constant pulsing outlines; floating elements; bouncing spring animations. | Calm, precise 150–250ms ease-out transitions; hardware-accelerated transforms; `prefers-reduced-motion` compliance. |

---

## 4. SkyGuard Visual Identity & Design Tokens

### Color Palette Architecture
* **Canvas Void:** `#080C14` (Deep Space Navy)
* **Surface 1 (Panels / Containers):** `#0D1322`
* **Surface 2 (Elevated Cards / Drawers):** `#131B2E`
* **Surface 3 (Hover / Popovers):** `#1A243D`
* **Inset Well / Data Tables:** `#060910`
* **Hairline Borders:** `rgba(255, 255, 255, 0.08)` / `#223049`
* **Telemetry Primary Accent:** `#0284C7` (Restrained Marine Blue) / `#38BDF8` (Sky Blue)
* **Semantic Status System (Strict WMO / Scientific):**
  * `NOMINAL` / `PASSED`: `#10B981` (Calibrated Emerald)
  * `INFO` / `METEOROLOGICAL`: `#0284C7` (Notice Sky)
  * `WARNING` / `DEGRADED`: `#F59E0B` (Amber)
  * `CRITICAL` / `HARD FAULT`: `#EF4444` (Crimson)
  * `METEOROLOGICAL EXTREME`: `#06B6D4` (Synoptic Cyan)
  * `NEUTRAL` / `METADATA`: `#64748B` (Steel Slate)

### Typography Hierarchy
* **Interface Text:** Inter / Plus Jakarta Sans (`font-sans`)
* **Readouts, Timestamps, Coordinates, Telemetry, Flags:** Monospace (`font-mono` / SF Mono / Consolas)
* **Weights:** Regular (400) for prose, Medium (500) for labels, Semi-bold (600) for headers, Bold (700) for primary metrics with `tabular-nums`.

---

## 5. 3D Geospatial Earth & Sensor Network Strategy

### Technology Selection: Three.js (ESM + WebGL)
* **Geometry:** Low-poly sphere ($R=1.0$) with procedural dark night earth texture, atmospheric rim shader glow ($R=1.03$), and coordinate grid lines (isobars / parallels).
* **Station Nodes:** Rendered at accurate WGS84 Cartesian coordinates:
  $$x = R \cdot \cos(\text{lat}) \cdot \cos(\text{lon})$$
  $$y = R \cdot \sin(\text{lat})$$
  $$z = -R \cdot \cos(\text{lat}) \cdot \sin(\text{lon})$$
* **Station Visual States:**
  * Healthy: Subtle emerald beacon pin with normal height ($H=0.08$).
  * Warning / Degraded: Amber beacon pin with pulsating halo.
  * Critical / Fault: Crimson beacon pin with warning strobe.
  * Meteorological Extreme: Cyan beacon pin.
* **Spatial Consensus Vectors:** Great-circle arc lines connecting station nodes to display spatial buddy-check correlation when stations are within consensus radius ($<250\,\text{km}$).
* **Interaction:** Smooth camera rotation, raycasting station selection, orbit controls with bounded pitch, and smooth fly-to zoom upon selecting a station.
* **Graceful Degradation:** Automatic WebGL detection with high-performance 2D SVG canvas fallback if WebGL is unavailable or user has reduced-motion preference.

---

## 6. Screen Architecture Blueprint

### 1. Overview (Command Center View)
* **Hero Visual:** Interactive 3D Earth Globe with live station cluster, camera controls, and spatial buddy-check consensus links.
* **Mission Telemetry Bar:** Fleet Health Index, Active Stations, Pipeline Latency, Ingest Rate.
* **Current Atmospheric Environment Panel:** Temperature, Pressure, Humidity, Dew Point, Magnus-Tetens saturation vapor pressure.
* **Active Station Registry Table:** Station ID, WMO callsign, coordinates, elevation, health badge, latest QC status.
* **Live Incident Log:** Real-time stream of detected anomalies with quick investigation links.

### 2. Live Monitoring (Instrument Console)
* **Station Sub-Header:** Station callsign, coordinates, elevation, live connection link status, and data source provenance.
* **3 Core Instrument Gauges:** Temperature (°C), Pressure (hPa), Relative Humidity (%) with rate-of-change indicators ($\Delta/\text{step}$) and physical range bars.
* **5-Tier Pipeline Verdict Banner:** Instant visual breakdown of Layer 1 Hard QC, Layer 2A Isolation Forest, Layer 2B PyTorch GRU Autoencoder, Layer 3 Clausius-Clapeyron Thermodynamic Consistency, and Layer 5 Fusion.
* **Synchronized Telemetry Charts:** Multi-channel area charts with confidence intervals, threshold limit lines, and interactive crosshair hover.

### 3. Alert Center (Incident Response System)
* **Incident Metrics Ribbon:** Active Incidents, Critical Faults, Degraded Channels, Meteorological Extremes.
* **Multi-Facet Search & Filter:** Filter by station, severity (LOW/MED/HIGH/CRIT), anomaly classification, and time range.
* **Incident Audit Log Table:** Dense table with timestamp, station ID, classification chip, score %, confidence, and status.
* **Forensic Investigation Drawer:** Deep side-drawer featuring root cause synthesis, TreeSHAP force attributions, spatial consensus neighbors, and operator action runbook.

### 4. Sensor Health & Predictive Maintenance Console
* **Fleet Health Summary:** Average Health Index, Optimal Stations, Degraded Sensors, Critical/Failing Units.
* **Subsystem Transducer Integrity Matrix:** Thermistor RTD integrity, Piezoresistive Barometer integrity, Capacitive Polymer Hygrometer integrity.
* **EMA Drift & Degradation Forecasting:** Exponential moving average drift tracker with historical trend line chart.

### 5. Event Detail (Forensic Incident Dossier)
* **Incident Dossier Header:** UUID, Station ID, Classification, Severity, Recorded Timestamp.
* **Observed Telemetry Readout:** 3-channel synchronous values.
* **5-Tier Mathematical Signal Decomposition Flow:** Step-by-step visual cards showing Pass/Fail/Score across all detection layers.
* **TreeSHAP Attribution Waterfall:** Exact percentage contribution weights with meteorological explanations.

### 6. Data Explorer (Scientific Data Lab)
* **Batch Dataset Ingestion Dropzone:** CSV drag-and-drop with column validation, sample template download, and batch 5-tier ML inference trigger.
* **Ingestion Summary Cards:** Total records, Valid QC pass count, Anomalies detected, Processing time (ms).
* **Persisted Telemetry Store Table:** High-density paginated tabular display with station filtering and QC validation badges.

### 7. Anomaly Simulation Laboratory (Testbed)
* **6 Disturbance Preset Cards:** Sudden Thermal Spike, Calibration Drift, Frozen Transducer, Channel Dropout, Thermodynamic Inconsistency, Severe Storm Front.
* **Parametric Disturbance Generator:** Custom anomaly type, target channel, magnitude offset, duration (steps), and decay options.
* **Direct Telemetry Link:** Real-time WebSocket dispatch with quick jump to Live Monitoring.

### 8. Explainability (XAI) Viewer
* **Incident Selector & Human-Readable Verdict Summary.**
* **TreeSHAP Normalized Feature Contribution Bars.**
* **Scientific Weather vs Sensor Fault Discrimination Matrix.**
* **Uncertainty Calibration Rationale.**

---

## 7. Performance & Verification Gate
* **Zero Mock / Fake Data:** Direct typed integration with backend REST endpoints (`/api/*`) and WebSocket streams (`/ws/live`).
* **Hardware-Accelerated Rendering:** Three.js WebGL canvas utilizing requestAnimationFrame with automatic render pausing when inactive.
* **Type-Safe Compilation:** Strict TypeScript (`tsc --noEmit`) clean compilation.
