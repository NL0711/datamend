## 1. Single station truth

- [ ] 1.1 Consume the global `selectedStationId` in `SensorHealthView` (drop the private default) and `AlertCenterView` (sync station filter, keep explicit "All stations")
- [ ] 1.2 Replace `EventDetailView` initial-only station/event props with live props that follow global selection
- [ ] 1.3 Sync `ExplainabilityViewer` station filter with the global selection
- [ ] 1.4 Reconcile the context default station against the fetched registry with first-station fallback

## 2. Mount-persistent tabs

- [ ] 2.1 Render all tab views mount-once (lazy on first visit), hiding inactive panes with CSS in `App.tsx`
- [ ] 2.2 Add an `active` prop to views and gate polling/auto-refetch effects on it (Overview 5s poll and equivalents)
- [ ] 2.3 Reset Live timeline + dedupe cursor on station change and drop out-of-order frames

## 3. Honest empty states

- [ ] 3.1 Remove the fabricated baseline telemetry point; render named empty/error states with manual reload

## 4. Verification

- [ ] 4.1 `npx tsc --noEmit` and production build clean; sweep for `activeTab ===` conditional mounts and ungated intervals
- [ ] 4.2 Manual pass: switch stations then tabs (every tab follows), round-trip tabs (state preserved), empty station (named empty state, no fiction)
