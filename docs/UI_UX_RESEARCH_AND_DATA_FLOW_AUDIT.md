# SKYGUARD AI — UI/UX RESEARCH & DATA-FLOW AUDIT REPORT

**Author:** Senior Product Designer & Full-Stack Systems Architect  
**Project:** SkyGuard AI — Intelligent WMO-No. 8 AWS Quality Control & Sensor Health System  
**Date:** August 2026  
**Status:** Audit Complete • Root Causes Identified • Execution Plan Defined

---

## 1. Executive Summary & Root Cause Findings

Following an in-depth code-level audit of both backend and frontend systems, we have identified the exact root causes for the reported UI/UX and data-flow failures:

### Root Cause A: WebSocket Payload Unpacking Bug in Frontend
- **The Issue:** The FastAPI backend (`backend/app/api/websocket.py`) broadcasts live observation packets formatted as:
  ```json
  {
    "type": "observation",
    "station_id": "PUNE-EXT-001",
    "data": {
      "timestamp": "2026-08-26T00:20:00Z",
      "station_id": "PUNE-EXT-001",
      "temperature": 27.8,
      "pressure": 952.1,
      "humidity": 68.4,
      "anomaly_score": 0.04,
      ...
    },
    "server_time": "..."
  }
  ```
- In `frontend/src/services/websocket.ts` (lines 38-44), the incoming payload was passed directly to the callback without checking for `.data`. As a result, `latestTelemetry.temperature` and `latestTelemetry.pressure` evaluated to `undefined`.
- Consequently, UI components in `OverviewView.tsx` (line 124) and `LiveMonitoringView.tsx` (line 86) triggered their fallback default constants (`28.6°C`, `54.0%`, `1008.4 hPa`), rendering the UI completely static regardless of which city or station was transmitting.

### Root Cause B: Disconnected City Selection & Data Source State
- `DataSourceControl.tsx` had an isolated `handleCityChange` that called `POST /api/data-sources/external/configure`.
- However:
  1. `App.tsx` rendered `<DataSourceControl />` without passing an `onSourceChanged` callback.
  2. If the active data source was `SIMULATED`, configuring Open-Meteo did not automatically activate `EXTERNAL_API`, causing simulated packets to continue overriding the stream.
  3. City selection did not propagate to `selectedStationId`, the 3D globe camera, or the live charts.

### Root Cause C: Information Architecture & Visual Density
- The previous UI suffered from "card overload," where every metric, badge, and table was enclosed in a high-contrast glowing card.
- The canvas background was overly dark/black, creating visual fatigue and a "cyberpunk/gaming" aesthetic rather than a professional meteorological command console (like ECMWF, NOAA WCT, or NASA Open MCT).
- The 3D Earth was visually isolated in a small card rather than being a spacious, functional geospatial digital twin with click-to-focus synchronization.

---

## 2. Benchmark Research on Scientific & Operational Platforms

| Platform | Layout & Information Hierarchy | Geospatial & 3D Visualization | Spacing & Visual Aesthetics |
| :--- | :--- | :--- | :--- |
| **NOAA Weather & Climate Toolkit (WCT)** | Layered data inspection, multi-sensor provenance, radar/synoptic station overlay. | Orthographic & WGS84 projections with contour isolines and station vectors. | Muted steel-slate background (`#131B2E`), strict color discipline for physical units. |
| **NASA Open MCT (Mission Control)** | Time-conductor bar at top/bottom, modular telemetry panes, telemetry health status chips. | Geospatial map tiles with telemetry nodes and orbit tracks. | Spacious grids, generous padding, semantic status indicators (Nominal Green, Degraded Amber, Fault Red). |
| **ECMWF & Copernicus C3S** | High-density scientific time-series, parameter selector rails, physical anomaly boundaries. | Global gridded reanalysis projections with vector wind arrows and station consensus. | Clean dark navy canvas (`#111827`, `#162033`), subtle hairline borders (`#263B5E`). |
| **Palantir Foundry / Gotham** | Left operational rail, top mission context HUD, deep forensic drawer for entity investigation. | 3D Geospatial node graph with spatial consensus links and provenance tracking. | High information density without clutter, hierarchical typography, no gratuitous glow. |
| **Windy & Meteoblue** | Immersive map-first operational canvas, synchronized timeline scrubber, live station popup. | WebGL particle streamlines, high-resolution global bathymetry & topography. | Fluid camera zooming, clean glassmorphic telemetry cards, real-time feedback. |

---

## 3. Recommended Information Architecture

We establish a 5-Level Progressive Disclosure Hierarchy:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ LEVEL 1: MISSION CONTROL BAR (UTC Clock, Ingest Mode, Provenance, Stream)   │
├─────────┬───────────────────────────────────────────────────────────────────┤
│ RAIL    │ LEVEL 2: ACTIVE OBSERVATION CONTEXT & TELEMETRY PROVENANCE        │
│ [1] CC  │ (City Selector: Pune / Delhi / London / Tokyo / Death Valley)     │
│ [2] LIVE├─────────────────────────────────┬─────────────────────────────────┤
│ [3] ALRT│ LEVEL 3: 3D GEOSPATIAL TWIN     │ LEVEL 3: STATION INTELLIGENCE   │
│ [4] HLTH│ - Realistic Earth Continents    │ - Active Transducer Telemetry   │
│ [5] FORE│ - Real WGS84 Station Pins       │ - Magnus-Tetens Dew Point       │
│ [6] EXPL│ - Spatial Consensus Links (250km│ - 5-Tier Pipeline Verdict       │
│ [7] LAB │ - Smooth Click/City Camera Zoom │ - Quick Diagnostic Actions      │
│ [8] XAI ├─────────────────────────────────┴─────────────────────────────────┤
│         │ LEVEL 4: FLEET REGISTRY TABLE & INCIDENT TRIAGE LOG               │
│         ├───────────────────────────────────────────────────────────────────┤
│         │ LEVEL 5: FORENSIC INVESTIGATION DRAWER (TreeSHAP Forces, 5-Tiers) │
└─────────┴───────────────────────────────────────────────────────────────────┘
```

---

## 4. Single Authoritative State Model: `ActiveObservationContext`

To eliminate state disconnection, all components will share a unified state context:

```typescript
export interface ActiveObservationContext {
  // Provenance & Source
  activeSourceType: 'SIMULATED' | 'EXTERNAL_API' | 'PHYSICAL_AWS';
  activeSourceStatus: DataSourceStatus | null;
  
  // Selected Station & Geography
  selectedStationId: string;
  selectedCityPreset: CityPreset | null;
  stationMetadata: Station | null;
  
  // Real-Time Telemetry & Timestamp
  currentTelemetry: {
    temperature: number;
    pressure: number;
    humidity: number;
    dewPoint: number;
    dewPointDepression: number;
    timestamp: string;
    receivedAt: string;
    dataAgeSeconds: number;
  };
  
  // 5-Tier Algorithmic State
  inferenceVerdict: {
    isAnomaly: boolean;
    anomalyScore: number;
    confidence: number;
    severity: 'NORMAL' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
    classification: string;
    reason: string;
    tierScores: TierScores;
    sensorHealth: number;
    sensorStatus: string;
  };
  
  // Time-Series Buffer for Charts
  history: InferenceResult[];
  
  // Spatial Consensus
  spatialConsensus: SpatialConsensusResult | null;
}
```

---

## 5. 3D Earth Geospatial Digital Twin Specifications

1. **Procedural / High-Resolution Geography:**
   - Accurate 2048×1024 continental landmass projection with terrain elevation shading and ocean bathymetry.
   - Lat/Lon graticule lines ($30^\circ$ parallels and meridians).
   - Atmospheric rim glow shader with Rayleigh-like light scattering.

2. **Accurate WGS84 Cartesian Coordinates:**
   $$\phi = (90 - \text{lat}) \cdot \frac{\pi}{180}, \quad \theta = (\text{lon} + 180) \cdot \frac{\pi}{180}$$
   $$x = -R \cdot \sin\phi \cdot \cos\theta, \quad y = R \cdot \cos\phi, \quad z = R \cdot \sin\phi \cdot \sin\theta$$

3. **Interactive Camera Tweening:**
   - When a city preset is clicked (e.g. Pune $\to$ New Delhi $\to$ London $\to$ Tokyo $\to$ Death Valley), the Three.js camera smoothly animates and rotates to center on that station with an elevation offset.

4. **Radial Health Beacons & Spatial Consensus Links:**
   - Color-coded pins (Emerald for Nominal, Amber for Degraded, Crimson for Faults).
   - Great-circle quadratic bezier arcs connecting neighbor stations within Tier 3.5 consensus radius ($250\text{ km}$).

---

## 6. Audit & Verification Checklist for Implementation

- [x] Fix WebSocket packet unpacking in `frontend/src/services/websocket.ts` (`payload.data || payload`).
- [x] Fix `ingestion_service.py` to broadcast a single clean packet containing telemetry values, source provenance, and tier scores.
- [x] Unify city preset selection in `DataSourceControl.tsx` so clicking a city activates `EXTERNAL_API`, triggers Open-Meteo fetch, updates global station context, moves the 3D globe camera, and refreshes gauges/charts.
- [x] Register all city preset stations in `StationRepository` so they appear on the 3D globe and registry tables.
- [x] Overhaul visual palette to deep aerospace slate/navy (`#0F1726`, `#152033`, `#1B2A44`, `#10192A`, `#263B5E` borders).
- [x] Perform live end-to-end city switching tests for Pune, New Delhi, London, Tokyo, and Death Valley.
