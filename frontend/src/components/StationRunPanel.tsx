// The selected station's latest stored run, shown with the existing run view: flagged rows with their evidence (Events) or every row (Explorer).
// Moved here from the shell in slice S2b; behaviour unchanged.
import { useStation } from '../validation/StationContext';
import { RunView } from '../validation/RunView';
import type { EventFocus } from '../validation/shell';
import { EmptyState } from '../design-system/components/EmptyState';

export function StationRunPanel({ scope, focus, onImport }: { scope: 'flagged' | 'all'; focus: (EventFocus & { station: string | null }) | null; onImport: () => void }) {
  const { stationId, selectedCycle, cycleLoaded } = useStation();
  if (!stationId) return <EmptyState title="No station selected" description="Select a station in the header to see its rows." />;
  const usable = scope === 'flagged' && focus && (focus.station === null || focus.station === stationId) ? focus : null;
  const runId = usable?.runId ?? selectedCycle?.latest_run_id ?? null;
  if (runId === null) {
    return cycleLoaded
      ? <EmptyState title={`No rows checked for ${stationId} yet`} description="Import a file, or connect the live feed in Settings." actionLabel="Import a file" onAction={onImport} />
      : <p className="text-xs text-slate-500 font-mono">Loading…</p>;
  }
  return <RunView key={`${scope}:${runId}:${stationId}:${usable?.rowId ?? ''}`} runId={runId} forcedStation={stationId} fixedScope={scope} initialRowId={usable?.rowId ?? null} />;
}
