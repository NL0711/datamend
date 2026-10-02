# SKYGUARD AI — SETTINGS & CONFIGURATION CENTER UX RESEARCH

**Author:** Senior Product Designer & Full-Stack Systems Architect  
**Project:** SkyGuard AI — WMO-No. 8 Automatic Weather Station Quality Control System  
**Date:** August 2026  
**Status:** Research Complete • Design Direction Approved

---

## 1. Benchmark Analysis of Scientific, Mission Control & Enterprise Platforms

To design an industrial-grade configuration experience for meteorological operations, we analyzed best-in-class operational, scientific, and enterprise interfaces:

| Platform | Configuration Pattern | Location & Status Presentation | Key Takeaway for SkyGuard AI |
| :--- | :--- | :--- | :--- |
| **NASA Open MCT** | Slide-out telemetry drawer; contextual time conductor in persistent bar. | Provenance chips in top header; explicit channel status (Nominal, Stale, Loss-of-Signal). | Move all telemetry feed controls into a slide-out drawer; keep main viewport dedicated to high-density graphs. |
| **NOAA AWIPS-II / WCT** | Dedicated configuration dialog; menu bar access to synoptic feeds and data sources. | Station IDs (`KORD`, `EGLL`) and WMO station blocks displayed in compact status bar. | Synoptic city/station selection should be cleanly accessible without taking 250px of canvas space. |
| **ECMWF Copernicus CDS** | Clean parameter rail with flyout configuration modal; persistent operator workspace. | Gridded and point-source reanalysis datasets labeled with explicit model/observation provenance. | High visual clarity; never obscure telemetry charts with configuration widgets. |
| **Palantir Foundry / Gotham** | Top-right configuration gear opening forensic drawer; environment switcher. | Explicit data lineage (source sensor $\to$ transformation $\to$ ontology node). | Show data provenance at all times (Open-Meteo, Physical ESP32, Simulated AWS) in a 1-line header pill. |
| **Datadog / Grafana** | Global top-bar environment/data-source switcher; slide-over drawer for ingestion settings. | Agent health indicators (Active, Muted, Degraded, Stale) with last packet age in seconds. | Diagnostic panel displaying WebSocket, REST API, SQLite WAL, and ML Engine health with ping counters. |
| **Linear / Stripe Dashboard** | Right-side slide-over drawer with instant persistence; accessible via `Cmd+,` or header icon. | Clean tabbed sections (General, Data Sources, Display Preferences, Diagnostics). | Smooth slide-out transitions, instant application of safe settings, generous card padding and typography. |

---

## 2. Automatic Weather Station (AWS) Network Operational Needs

In real meteorological networks (e.g. Vaisala HydroMet, Campbell Scientific CampbellCloud, India Meteorological Department AWS network):
1. **Separation of Concerns:**
   - Situational Awareness (MapView, Live Gauges, Anomaly Stream) must remain **uncluttered and prominent**.
   - Ingest Source Configuration (Satellite link, Cellular GPRS, REST API, Polling Frequency) belongs in an **Operations Settings Center**.
2. **Data Provenance Transparency (WMO-No. 8 Compliance):**
   - Operators must know with 100% certainty whether an alert comes from a real physical station, a reanalysis/NWP API, or a training simulator.
   - When a connection drops, the system must show `DISCONNECTED` or `DEGRADED`, never silently substitute synthetic data.
3. **Display Density Modes:**
   - Operators monitoring multi-monitor video walls prefer `Comfortable` or `Compact` density with high contrast, whereas field engineers prefer high-density `Operator` tables.

---

## 3. Interaction Patterns Adopted for SkyGuard AI

### 1. Global Header Integration
- A top-right `⚙ System Configuration` trigger button paired with an active status chip (`Open-Meteo • New Delhi • LIVE • 12s ago`).
- Discoverable, non-intrusive, and always visible regardless of active view.

### 2. Premium Right-Side Settings Center Drawer
- Width: `460px` - `540px` with smooth backdrop overlay and slide-in motion.
- Structured into 6 logical operational sections:
  1. **Telemetry Data Source:** Toggle between Simulated AWS, Open-Meteo Live Feed, and Physical ESP32 with real-time connection status, data age, and packet counters.
  2. **Synoptic Climate Site:** Interactive cards for Pune, New Delhi, London, Tokyo, and Death Valley with instant coordinate updates and Open-Meteo query dispatch.
  3. **Simulation Engine:** Status, interval (1.5s), scenario selection, and Start/Pause controls (only visible when Simulated is active).
  4. **Hardware ESP32 Link:** Serial/Socket connection details, listening port 8899, raw byte stream diagnostics.
  5. **Display & Operator Preferences:** Density selector (`Comfortable`, `Compact`, `Operator`), Reduced Motion toggle, default operational tab.
  6. **System Diagnostics:** Live health indicators for WebSocket, REST API, SQLite WAL, and 5-Tier ML Quality Control Engine.

### 3. Compact Contextual Status Strip on Operational Views
- Replaces the bulky 240px `DataSourceControl` HUD with a sleek, single-line (36px) status strip on `OverviewView` and `LiveMonitoringView`.
- Displays source name, active station, connection badge, data freshness timer, and a quick `⚙ Configure` link.

---

## 4. Patterns Explicitly Avoided

- **NO** 240px tall repetitive control panels rendered in the middle of every page.
- **NO** fake weather generation or hardcoded city telemetry.
- **NO** silent fallback from Open-Meteo failure to simulation.
- **NO** tiny microscopic dropdown menus that hide connection diagnostics.
- **NO** gratuitous neon glow or unnecessary animations.
