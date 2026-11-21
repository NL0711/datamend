// The selected station's latest stored run, shown with the existing run view: flagged rows with their evidence (Events) or every row (Explorer).
// Moved here from the shell in slice S2b; behaviour unchanged.
import { useStation } from '../validation/StationContext';
import { RunView } from '../validation/RunView';
import type { EventFocus } from '../validation/shell';
import { EmptyState } from '../design-system/components/EmptyState';
import { NeedStation } from './PageIntro';

/** Words for a station with no file run. It never implies the station has no data: live-stream readings and detections are stored separately. */
export function emptyRunText(scope: 'flagged' | 'all'): string {
  return scope === 'flagged'
    ? 'This list covers imported files only. Detections from the live stream for this station, if any, are listed below. Import a file to add a checked run.'
    : 'This list covers imported files only. Live-stream readings for this station are on the Live page. Import a file to add a checked run.';
}

export function StationRunPanel({ scope, focus, onImport }: { scope: 'flagged' | 'all'; focus: (EventFocus & { station: string | null }) | null; onImport: () => void }) {
  const { stationId, selectedCycle, cycleLoaded } = useStation();
  if (!stationId) return <NeedStation what={scope === 'flagged' ? 'Events shows the evidence behind the flags of one station.' : 'This list shows the checked rows of one station.'} />;
  const usable = scope === 'flagged' && focus && (focus.station === null || focus.station === stationId) ? focus : null;
  const runId = usable?.runId ?? selectedCycle?.latest_run_id ?? null;
  if (runId === null) {
    return cycleLoaded
      ? <EmptyState title={`No uploaded-file run for ${stationId}`} description={emptyRunText(scope)} actionLabel="Import a file" onAction={onImport} />
      : <p className="text-xs text-slate-500 font-mono">Loading…</p>;
  }
  return <RunView key={`${scope}:${runId}:${stationId}:${usable?.rowId ?? ''}`} runId={runId} forcedStation={stationId} fixedScope={scope} initialRowId={usable?.rowId ?? null} />;
}
