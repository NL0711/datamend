# SKYGUARD AI — PRODUCT-LEVEL VISUAL REDESIGN SPECIFICATION & DIRECTION

**Document Version:** 3.0 (Master Visual Architecture)  
**Target Platform:** SkyGuard AI — Scientific Quality-Control & Sensor Health Operations Platform  
**Authority:** Master Product & UI/UX Architecture Specification

---

## 1. Critique & Audit of Previous Implementation

### Identified Visual & Structural Flaws
1. **Pitch-Black Void (`#080C14`, `#060910`):** The previous background created a flat, dark abyss that felt like an unpolished hacker theme rather than a scientific instrument console.
2. **Neon/Cyan Overuse:** Cyan borders (`border-sky-500/30`), text highlights, and badge strokes were applied indiscriminately, triggering the "generic AI/cyberpunk template" look.
3. **Stacked Card Monotony:** The layout relied entirely on vertically stacked rectangular cards (`Card -> Card -> Card -> Card -> Globe in Box -> Table`), creating vast empty horizontal gutters.
4. **Disconnected, Decorative 3D Globe:** The 3D Earth was isolated in a small container with massive empty space, lacked continental landmass texture, and didn't act as the spatial anchor for the operational UI.
5. **Lack of Integrated Spatial Storytelling:** Selecting a station on the globe did not seamlessly drive the operational telemetry workspace, inspect consensus links, or anchor the station dossier.

---

## 2. New Visual Identity: Atmospheric Scientific Command Center

### Color System & Surface Hierarchy (No Pitch Black)
* **Canvas Void:** `#0F1726` (Atmospheric Slate-Navy with cool blue undertones)
* **Workspace Surface (Level 1):** `#152033` (Deep Mission Surface)
* **Elevated Panels (Level 2):** `#1B2A44` (Card & Tool Containers)
* **Focus / Interactive Surface (Level 3):** `#233656` (Selected Rows, Active Modals, Flyouts)
* **Surface Dividers & Hairlines:** `#2B426B` / `rgba(255, 255, 255, 0.09)`
* **Muted Technical Insets:** `#111A2B`

### Strict Semantic Status Color Discipline
Color communicates **DATA ONLY** — never arbitrary decoration:
* **Nominal / Calibrated:** `#10B981` (Muted Sage/Emerald)
* **Notice / Operational Info:** `#38BDF8` (Sky Blue)
* **Warning / Degraded Sensor:** `#F59E0B` (Amber)
* **Critical Fault / Sensor Failure:** `#EF4444` (Precision Crimson)
* **Meteorological Extreme Event:** `#06B6D4` (Atmospheric Cyan)
* **Neutral Metadata:** `#94A3B8` / `#64748B` (Steel Slate)

---

## 3. Application Shell Architecture: Mission Operations Console

```
+---------------------------------------------------------------------------------------------------------------+
| SKYGUARD AI [QC PLATFORM] | STATION: AWS-001 | SOURCE: OPEN-METEO | STREAM: ACTIVE | UTC: 18:42:15Z | LATENCY: 1.4ms |
+----------+----------------------------------------------------------------------------------------------------+
| [CMD]    | COMMAND CENTER (OVERVIEW)                                                                          |
| Overview | +-------------------------------------------------------+----------------------------------------+ |
| [TEL]    | | 3D GEOSPATIAL STATION DIGITAL TWIN (WebGL)            | ACTIVE STATION INTELLIGENCE DOSSIER    | |
| Live     | |                                                       | Station: AWS-001 (New Delhi, IN)       | |
| [ALT]    | |   [Realistic Earth with Continents & Atmosphere]      | Health: 98/100 [NOMINAL]               | |
| Alerts   | |   - Lat/Lon WGS84 Station Pins                        | -------------------------------------- | |
| [HLT]    | |   - Tier 3.5 Spatial Consensus Arcs                   | TEMP: 28.6°C  (dT/dt: +0.2°C)          | |
| Health   | |   - Interactive Raycast Focus & Camera Zoom           | PRESS: 1008.4 hPa (Normal)             | |
| [EVT]    | |   - Floating Layer Controls (Health, Grid, Arcs)      | HUM: 54.0%    (DewPoint: 18.2°C)       | |
| Events   | |                                                       | Spatial Consensus: [SUPPORTED]         | |
| [DAT]    | +-------------------------------------------------------+----------------------------------------+ |
| Data     | FLEET TELEMETRY MATRIX & ACTIVE INCIDENTS STREAM                                                   | |
| [LAB]    | +------------------------------------+----------------------------------+-----------------------+ | |
| Lab      | | Active Stations Registry (Table)   | Live Flagged Incident Stream     | Batch Ingestion QC    | | |
| [XAI]    | +------------------------------------+----------------------------------+-----------------------+ | |
| XAI      |                                                                                                    | |
+----------+----------------------------------------------------------------------------------------------------+
```

### Key Elements of the Redesigned Application Shell:
1. **Left Command Rail:** Compact 64px vertical navigation with high-craft iconography, tooltips, and keyboard shortcuts (`Cmd+1` to `Cmd+8`).
2. **Top Mission Telemetry Banner:** Real-time stream indicator, data provenance badge (Physical ESP32 / Open-Meteo / Simulated), packet counter, and live UTC clock.
3. **Integrated Split Command Center Deck:**
   - **Left 60%:** Functional, cinematic 3D Earth Globe with realistic procedural landmasses, atmospheric rim glow, true WGS84 station pins, and Tier 3.5 spatial consensus links.
   - **Right 40%:** Active Station Intelligence Dossier & Telemetry Profile updating in real-time as stations are clicked or streamed.
4. **Bottom Multi-Modal Operational Deck:** Live Active Incident Stream, Station Registry Table, and Quick Simulation Controls with zero dead space.

---

## 4. Screen-by-Screen Redesign Strategy

1. **Overview (Command Center):** Integrated 3D Earth + Station Intelligence Dossier + Fleet Health + Real-time Incident Stream.
2. **Live Monitoring (Instrument Console):** Station callsign header, 3 high-precision analog/digital instruments (Temperature, Pressure, Humidity) with rate-of-change ($\Delta/\text{step}$) and Magnus-Tetens dew point, 5-tier pipeline decision flow, and synchronized Recharts area plots with confidence bands.
3. **Alert Center (Incident Response Console):** 3-pane incident triage workspace (Incident Queue -> Selected Incident Dossier -> TreeSHAP Root Cause Forensics & Runbook).
4. **Sensor Health (Predictive Maintenance Console):** Fleet health distribution, subsystem transducer integrity matrix (Thermistor RTD, Piezoresistive Barometer, Capacitive Hygrometer), and EMA drift trend lines.
5. **Event Detail (Forensic Incident Dossier):** Connected 5-tier mathematical signal decomposition flow cards (Tier 1 Physical QC $\rightarrow$ Tier 2A Isolation Forest $\rightarrow$ Tier 2B GRU Autoencoder $\rightarrow$ Tier 3 Clausius-Clapeyron $\rightarrow$ Tier 3.5 Spatial Consensus $\rightarrow$ Tier 5 Fusion).
6. **Data Explorer (Scientific Data Lab):** Drag-and-drop CSV batch ingestion dropzone with schema validation, statistical summary cards, and high-density paginated telemetry table.
7. **Anomaly Lab (Simulation Testbed):** Experimentation testbed with 6 disturbance preset cards (Spike, Drift, Freeze, Dropout, Thermodynamic Inconsistency, Severe Storm Front) and parametric disturbance generator.
8. **Explainability Viewer (XAI Reasoner):** Human-readable verdict summary, normalized TreeSHAP feature contribution weights, and Weather vs Sensor Fault discrimination matrix.
