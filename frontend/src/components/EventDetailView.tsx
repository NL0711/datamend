// Event Forensics in the header layout of the ORIGINAL dashboard, restored in slice S2b. The original listed temperature, pressure and
// humidity anomalies with a "5-tier decomposition". The DATA here is the platform's own, as in
// S2: the flagged rainfall rows of the selected station's latest stored run with the evidence behind each flag (the run view). Under it
// are the stream's detections from GET /api/anomalies with the evidence of every check that fired; no tier scores or SHAP-style
// factors are shown, because the platform computes none.
import { useStation } from '../validation/StationContext';
import type { EventFocus } from '../validation/shell';
import { StationRunPanel } from './StationRunPanel';
import { AnomalyFeed } from './AnomalyFeed';

interface EventDetailViewProps {
  focus: (EventFocus & { station: string | null }) | null;
  onImport: () => void;
  onNavigateToLive?: (stationId: string) => void;
}

export function EventDetailView({ focus, onImport, onNavigateToLive }: EventDetailViewProps) {
  const { stationId, entry, selectedCycle } = useStation();

  return (
    <div className="space-y-6">
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] p-4 rounded-xl shadow-lg space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-sky-500/15 border border-sky-500/35 rounded-lg text-sky-600" />
            <div>
              <h2 className="text-sm font-bold text-slate-900 uppercase font-mono tracking-wide flex items-center gap-2">
                Event Forensics & Evidence
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-500/15 text-sky-700 border border-sky-500/30 font-semibold">
                  {stationId ? 'SELECTED STATION' : 'NO STATION'}
                </span>
              </h2>
              <p className="text-xs text-slate-600">
                Flagged rows of the station's latest run, with the check, the observed value, the threshold and the window behind every flag
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono text-slate-600">
            {stationId && (
              <span className="px-2.5 py-1 rounded bg-[#F4F6FA] border border-[#D3DCE7] text-slate-600">
                <strong className="text-sky-600">{stationId}</strong>{entry ? ` · ${entry.place}` : ''}
              </span>
            )}
            {selectedCycle && (
              <span className="px-2.5 py-1 rounded bg-[#F4F6FA] border border-[#D3DCE7] text-slate-600">
                Flagged: <strong className="text-sky-600">{selectedCycle.flagged}</strong> of {selectedCycle.checked} rows
              </span>
            )}
            {stationId && onNavigateToLive && (
              <button onClick={() => onNavigateToLive(stationId)} className="px-2.5 py-1 rounded bg-[#EDF1F7] hover:bg-[#E2E8F2] text-sky-700 border border-sky-500/40 font-bold">
                Live →
              </button>
            )}
          </div>
        </div>
      </div>

      <StationRunPanel scope="flagged" focus={focus} onImport={onImport} />

      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg space-y-2">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">Stream detections (temperature, pressure, humidity, rain)</h4>
        <AnomalyFeed stationId={stationId} limit={12} evidence />
      </div>
    </div>
  );
}
