## Why

Switching tabs confuses operators about which station's data they are looking at: each tab keeps its own station idea (Health is stuck on its own default, Alerts is always fleet-wide, Events freezes its initial value), every tab switch unmounts and rebuilds the view (refetch flash, lost timeline continuity), and an empty history renders a hardcoded fake data point instead of an honest empty state.

## What Changes

- **Single station truth:** `selectedStationId` from `SystemConfigurationContext` becomes the only station selection. `SensorHealthView`, `AlertCenterView`, `EventDetailView`, and `ExplainabilityViewer` drop their private station states (keeping their other filters) and follow the global selection; views with no valid selection show an explicit "select a station" state.
- **Mount-persistent tabs:** all tab views mount once and inactive tabs hide via CSS instead of unmounting, so timelines, filters, and selections survive switching. Background polling (e.g. the 5s Overview refetch) pauses while its tab is hidden via an `active` prop / visibility check.
- **Honest empty states:** the hardcoded fallback telemetry point in `LiveMonitoringView` is removed; empty history renders an explicit "no data for this station" state. The global default station is reconciled with actually-seeded stations so first paint is real data, not fiction.

## Capabilities

### New Capabilities

- `station-truth`: one global station selection consumed by every tab, with no divergent local copies.
- `tab-persistence`: tabs stay mounted across switches with background work paused while hidden.
- `honest-empty-states`: no fabricated telemetry; explicit empty/error states and a valid default station.

### Modified Capabilities

- None (existing specs in `openspec/specs/` describe backend behavior untouched by this change).

## Impact

- Affected code: `frontend/src/App.tsx` (mount-once tab rendering + `active` prop), `frontend/src/context/SystemConfigurationContext.tsx` (default station reconciliation), `SensorHealthView`, `AlertCenterView`, `EventDetailView`, `ExplainabilityViewer`, `OverviewView` (polling pause), `LiveMonitoringView` (empty state, dedupe hardening).
- No backend, API, schema, or ML changes. No route changes.
- Risk: all tabs mounted means more live subscriptions in memory — mitigated by pausing hidden-tab polling and keeping WS fan-out subscription-based.
