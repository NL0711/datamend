## Context

`App.tsx` conditionally renders one tab at a time (`{activeTab === 'live' && (…)}`), so leaving a tab destroys its component state: timelines, filters, dossier selections, and the WS dedupe ref are all rebuilt on return, with a REST refetch flashing older data first. Separately, station selection is nominally global (`SystemConfigurationContext.selectedStationId`, default `'KTLX'`) but only Overview and Live consume it: `SensorHealthView()` takes no props and keeps its own `'KTLX'` default, `AlertCenterView` keeps a private fleet-wide filter, `EventDetailView` reads `initialStationId` once, and `ExplainabilityViewer` keeps private filters. When history is empty, `LiveMonitoringView` fabricates a baseline point (28.5 °C / 980.2 hPa / 72 %) instead of showing an empty state.

## Goals / Non-Goals

**Goals:**

- One station selection, honored by every tab; the operator can always answer "which data am I at."
- Switching tabs preserves view state; returning shows continuity, not a refetch flash.
- Hidden tabs cost ~zero CPU/network: polling pauses, WS stays single and global.
- Empty history is visibly empty; the default station exists in the seeded registry.

**Non-Goals:**

- Changing what any tab shows (filters, layouts, and non-station state stay as-is).
- Backend, API, ML, or schema changes.
- Cross-tab linked brushing or shared timelines.

## Decisions

- **Keep conditional mounting structure, hide with CSS.** Render every tab view once inside a wrapper `<div className={activeTab === id ? 'contents' : 'hidden'}>`… precisely: a `hidden` class on the inactive panes (views stay mounted, layout cost only). Rationale: minimal diff to `App.tsx`, no router needed. Alternative (tab router / keep-alive library) rejected as heavier than the problem.
- **`active` prop gates background work.** Each view receives `active: boolean`; intervals (`OverviewView` 5s poll) and auto-refetch effects early-return or clear when `!active`. The global WS client in `App.tsx` is untouched (one socket, already subscription-filtered). Rationale: fixes the CPU-creep objection to persistent mounting without touching the socket layer.
- **Delete local station states; consume context.** `SensorHealthView` accepts and uses the global id (drop its `'KTLX'` default); `AlertCenterView` seeds/syncs its station filter from the global id (empty = fleet-wide stays possible via explicit "All stations" option, not by ignoring the prop); `EventDetailView` replaces initial-only props with live props; `ExplainabilityViewer` syncs its station filter the same way. Rationale: one source of truth; per-tab *filters* (severity, search) remain local.
- **Empty timeline renders an empty state.** Remove the fabricated baseline point; when `timelineData` is empty after load, show "No telemetry for {station} yet — waiting for stream…" plus a manual Reload. Reconcile the default: context falls back to the first registry station when the stored default is absent from `fetchStations()` results (covers the `'KTLX'`-vs-seeded-registry mismatch).
- **Harden the live seam while here.** On station change, `LiveMonitoringView` resets `timelineData` + `lastProcessedTimeRef` *before* refetching (no stale-station flash), and drops frames older than the newest rendered timestamp (not just exact-dupes), so remount/refetch races can't inject out-of-order points.

## Risks / Trade-offs

- [Risk] Seven mounted views hold seven timelines in memory → Mitigation: 50-point rolling windows already bound each; hidden-tab polling paused; acceptable.
- [Risk] Views that fetch on mount will fetch once at app start instead of on first visit (slower cold start) → Mitigation: lazy-mount on first visit, then keep mounted (mount-once + hidden thereafter).
- [Risk] Removing local station defaults changes deep-link/initial behavior → Mitigation: explicit "All stations" fleet option preserved in Alerts; everywhere else global id is always defined after reconciliation.
- [Trade-off] CSS-hidden views keep effects alive unless gated — the `active` prop discipline must be applied to every interval/fetch effect; verification task sweeps for unmounted-conditional patterns and ungated intervals.
