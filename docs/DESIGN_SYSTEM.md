# SKYGUARD AI — PRODUCTION DESIGN SYSTEM SPECIFICATION

**System Name:** SkyGuard Scientific Operations Design System (SG-SODS)  
**Target Archetype:** Mission-Critical Meteorological Observability & Industrial IoT Quality Control  
**Visual Identity:** Precision • Restraint • High Legibility • Scientific Credibility • Zero-Gimmick Engineering

---

## 1. Design Principles

1. **Restraint Over Decoration:** No unmotivated gradients, pulsing neon badges, or cybernetic glow effects. Color is strictly reserved for data encoding and operational status.
2. **Dense Yet Scannable Hierarchy:** Operational dashboards must allow meteorologists and station managers to scan 50+ stations and identify anomalies within 5 seconds.
3. **Evidence-First Visualization:** Every anomaly alert must be backed by multi-signal evidence: physical boundary checks, temporal autoencoder reconstruction residuals, thermodynamic Clausius-Clapeyron consistency, and TreeSHAP attribution forces.
4. **Typographic Rhythm:** Crisp distinction between structural UI prose (Inter / Plus Jakarta Sans) and technical data telemetry (Monospace for numerical readings, timestamps, and station callsigns).
5. **Surface Elevation & Layered Contrast:** Hierarchy is created through subtle surface brightness steps and hairline dividers (`rgba(255, 255, 255, 0.07)`), not heavy card borders.

---

## 2. Color Architecture & Tokens

### 2.1 Neutral Foundation (Dark Slate-Graphite)
```css
/* Background & Surface Hierarchy */
--sg-bg-base: #080C14;       /* Main application canvas (deep graphite-navy) */
--sg-bg-surface-1: #0D1322;   /* Level 1 cards, tables, top navigation */
--sg-bg-surface-2: #131B2E;   /* Level 2 elevated panels, drawers, popovers */
--sg-bg-surface-3: #1A243D;   /* Hover states, active tabs, selected rows */
--sg-bg-inset: #060910;       /* Recessed data displays, terminal blocks */

/* Hairline Borders & Dividers */
--sg-border-subtle: rgba(255, 255, 255, 0.06);
--sg-border-default: rgba(255, 255, 255, 0.10);
--sg-border-focus: #0284C7;
```

### 2.2 Foreground & Text Hierarchy
```css
--sg-text-primary: #F8FAFC;    /* High contrast (headers, active figures, critical labels) */
--sg-text-secondary: #94A3B8;  /* Body copy, table headers, supporting metrics */
--sg-text-muted: #64748B;      /* Metadata, timestamps, inactive units */
--sg-text-disabled: #475569;   /* Disabled controls, empty state subtitles */
```

### 2.3 Semantic Operational Status Tokens
| State | Light Fill | Border | Text | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Nominal (Normal)** | `rgba(16, 185, 129, 0.10)` | `rgba(16, 185, 129, 0.30)` | `#34D399` | Normal observation, passed QC, healthy sensor |
| **Informational / API** | `rgba(2, 132, 199, 0.10)` | `rgba(2, 132, 199, 0.30)` | `#38BDF8` | Open-Meteo feed, system notifications, info chips |
| **Notice / Low Severity** | `rgba(14, 165, 233, 0.10)` | `rgba(14, 165, 233, 0.30)` | `#7DD3FC` | Minor deviation, baseline shift within tolerance |
| **Warning / Suspicious** | `rgba(245, 158, 11, 0.10)` | `rgba(245, 158, 11, 0.35)` | `#FBBF24` | Rate-of-change alert, drift detected, degraded health |
| **Critical / Fault** | `rgba(239, 68, 68, 0.12)` | `rgba(239, 68, 68, 0.40)` | `#F87171` | Unphysical spike, frozen sensor, hardware dropout |
| **Met Extreme (Severe)** | `rgba(6, 182, 212, 0.12)` | `rgba(6, 182, 212, 0.40)` | `#22D3EE` | Genuine storm front, deep pressure trough, supported by consensus |

---

## 3. Typography Architecture

### 3.1 Font Families
- **Interface & Prose:** `Inter`, `-apple-system`, `BlinkMacSystemFont`, `Segoe UI`, `sans-serif`
- **Telemetry & Technical Data:** `ui-monospace`, `SFMono-Regular`, `Menlo`, `Monaco`, `Consolas`, `monospace`

### 3.2 Type Scale
- **Display Heading:** `20px` (font-weight: 700, tracking: -0.02em) — Main Page Title
- **Section Heading:** `15px` (font-weight: 600, tracking: -0.01em) — Section / Panel Header
- **Subheading / Label:** `12px` (font-weight: 600, uppercase, tracking: 0.05em, text: secondary)
- **Body Regular:** `13px` (font-weight: 400, line-height: 1.5) — Explanations & Descriptions
- **Data Big Metric:** `28px`–`32px` (font-weight: 700, font-family: monospace) — Numerical Sensor Value
- **Data Unit / Delta:** `11px`–`12px` (font-weight: 500, font-family: monospace) — `°C`, `hPa`, `%`, `±0.4`
- **Micro Metadata:** `10px`–`11px` (font-weight: 500, font-family: monospace) — Timestamps, coordinates, hash IDs

---

## 4. Layout & Surface Structure

### 4.1 Global Application Shell
```
+---------------------------------------------------------------------------------------+
| [LOGO] SkyGuard AI | Meteorological QC Platform   [STATUS HUD: WS LIVE • 3 SOURCES]  |
+---------------------------------------------------------------------------------------+
| [Overview] [Live Monitoring] [Alert Center] [Sensor Health] [Event Detail] ...       |
+---------------------------------------------------------------------------------------+
|  TELEMETRY PROVENANCE BAR (Simulated AWS | Open-Meteo Live API | Physical ESP32)      |
+---------------------------------------------------------------------------------------+
|                                                                                       |
|  PRIMARY OPERATIONS CANVAS                                                            |
|  (Adaptive responsive grid: 12-column layout with 24px gutters and 16px row gaps)     |
|                                                                                       |
+---------------------------------------------------------------------------------------+
| FOOTER: Operational QC Engine v0.3.0 • Latency: 1.8ms • SQLite WAL • PyTorch GRU-AE   |
+---------------------------------------------------------------------------------------+
```

### 4.2 Card & Panel Treatment
- **Card Radius:** `rounded-xl` (12px)
- **Background:** `bg-[#0D1322]/90` with subtle backdrop blur (`backdrop-blur-md`)
- **Border:** `1px solid rgba(255, 255, 255, 0.07)`
- **Hover State:** `hover:border-sky-500/30 hover:bg-[#11182A]` with 150ms ease-out transition
- **Shadow:** `shadow-lg shadow-black/40`

---

## 5. Chart & Data Visualization Guidelines

1. **Gridlines:** Subtle dashed grid (`#1E293B` or `rgba(255, 255, 255, 0.05)`).
2. **Channel Colors:**
   - **Temperature:** `#F59E0B` (Amber-400)
   - **Pressure:** `#38BDF8` (Sky-400)
   - **Humidity:** `#818CF8` (Indigo-400)
3. **Reference Bands:** Transparent fill (`rgba(56, 189, 248, 0.08)`) representing $\pm 2\sigma$ normal diurnal confidence intervals.
4. **Anomaly Points:** Highlighted with distinct red/amber circles and tooltip detailing tier attributions.
5. **Tooltips:** Inverted dark popovers (`bg-[#0A0E1A]`, `border-slate-700`, monospace telemetry values).

---

## 6. Motion & Micro-Interactions

- **State Transitions:** 150ms–200ms `cubic-bezier(0.16, 1, 0.3, 1)`
- **Tab Switching:** Instant content swap with smooth opacity fade-in (120ms)
- **Live Ingest Pulse:** 2-second calm breathing cycle on connection status pills, disabled under `prefers-reduced-motion`.
