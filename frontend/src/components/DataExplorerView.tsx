// Data Explorer in the layout of the ORIGINAL dashboard, restored in slice S2b: an ingestion card, then the stored telemetry table with
// paging. Two sources, both for the selected station: the stored stream readings (GET /api/observations, paged, newest first: temperature,
// pressure, humidity, rain, the verdict, the rule score and the id of the source that produced each reading) and the platform's stored
// rainfall rows from uploaded files (the run view, all rows) below it.
// Changed against the original: the CSV dropzone is replaced by a link to the Import page (which already validates uploads), and the
// private station list is replaced by the header's station picker.
import { useEffect, useState } from 'react';
import { fetchObservations, isNotBuilt, errorText } from '../services/api';
import { fmtScore, verdictWords } from '../services/stream';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { Observation } from '../types';
import { TableSkeleton } from '../design-system/components/SkeletonLoader';
import { EmptyState } from '../design-system/components/EmptyState';
import { useStation } from '../validation/StationContext';
import { StationRunPanel } from './StationRunPanel';

const PAGE_LIMIT = 50;

export function DataExplorerView({ onImport }: { onImport: () => void }) {
  const { stationId } = useStation();
  const [observations, setObservations] = useState<Observation[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [isLoading, setIsLoading] = useState(false);
  const [notBuilt, setNotBuilt] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadObservations = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetchObservations({ station_id: stationId || undefined, limit: PAGE_LIMIT, page });
      setObservations(res.items);
      setTotalCount(res.total);
      setNotBuilt(false);
    } catch (err) {
      setObservations([]);
      setTotalCount(0);
      if (isNotBuilt(err)) setNotBuilt(true);
      else setError(errorText(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { setPage(1); }, [stationId]);
  useEffect(() => { void loadObservations(); }, [stationId, page]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6">
      {/* Ingestion section */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 flex items-center gap-2 font-mono">Batch Dataset Ingestion</h3>
          <p className="text-xs text-slate-600 mt-0.5">
            Upload a rainfall file, or import one from an Amazon S3 or Kaggle link. Files are validated on arrival; a bad file is rejected with the reason.
          </p>
        </div>
        <button onClick={onImport} className="flex items-center gap-2 px-4 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg transition-all shadow">
          Open Import →
        </button>
      </div>

      {/* Stored T/P/RH observations */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">
            Stored stream readings: temperature, pressure, humidity, rain ({totalCount.toLocaleString()} records{stationId ? ` for ${stationId}` : ''})
          </h3>
          <button onClick={() => void loadObservations()} className="px-2.5 py-1.5 bg-[#F4F6FA] hover:bg-[#EDF1F7] text-slate-700 rounded-lg text-xs border border-[#D3DCE7] font-mono font-semibold">
            Reload
          </button>
        </div>

        {notBuilt ? (
          <EmptyState title="Stored readings not available" description="GET /api/observations did not answer (404, 501, 502 or 503). The rainfall rows below are stored separately." />
        ) : error ? (
          <div className="p-3 rounded-xl border border-rose-300 bg-rose-50 text-xs text-rose-800 font-mono">{error}</div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-200 text-slate-500 font-sans font-semibold uppercase text-[11px] tracking-wider">
                    <th className="pb-3">ID</th>
                    <th className="pb-3">Timestamp (UTC)</th>
                    <th className="pb-3">Station</th>
                    <th className="pb-3">Temperature (°C)</th>
                    <th className="pb-3">Pressure (hPa)</th>
                    <th className="pb-3">Humidity (%)</th>
                    <th className="pb-3">Rain (mm)</th>
                    <th className="pb-3">Source</th>
                    <th className="pb-3 text-right">Rule score</th>
                    <th className="pb-3 text-right">QC Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {isLoading ? (
                    <tr><td colSpan={10} className="py-6"><TableSkeleton rows={4} /></td></tr>
                  ) : observations.length === 0 ? (
                    <tr><td colSpan={10} className="py-8 text-center text-slate-500 font-sans">No stored stream readings{stationId ? ` for ${stationId}` : ''}. Start a source on the Live page.</td></tr>
                  ) : (
                    observations.map((obs, i) => (
                      <tr key={obs.id ?? `${obs.station_id}-${obs.timestamp}-${i}`} className="hover:bg-[#EDF1F7] transition-colors">
                        <td className="py-2.5 text-slate-500">{obs.id !== undefined ? `#${obs.id}` : '—'}</td>
                        <td className="py-2.5 text-slate-600">{new Date(obs.timestamp).toLocaleString()}</td>
                        <td className="py-2.5 text-sky-600 font-bold">{obs.station_id}</td>
                        <td className="py-2.5 text-slate-900 font-bold">{obs.temperature != null ? obs.temperature.toFixed(2) : '--'}</td>
                        <td className="py-2.5 text-slate-700">{obs.pressure != null ? obs.pressure.toFixed(1) : '--'}</td>
                        <td className="py-2.5 text-slate-700">{obs.humidity != null ? obs.humidity.toFixed(1) : '--'}</td>
                        <td className="py-2.5 text-slate-700">{obs.rain_mm != null ? obs.rain_mm.toFixed(2) : '--'}</td>
                        <td className="py-2.5 text-slate-600">{obs.source ?? '--'}</td>
                        <td className="py-2.5 text-right text-sky-600 font-bold">{fmtScore(obs.rule_score)}</td>
                        <td className="py-2.5 text-right">{(() => { const w = verdictWords(obs.check_status ?? obs.validation_status); return <StatusBadge label={w.label} variant={w.tone} size="sm" />; })()}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            <div className="pt-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500 font-mono">
              <span>Page {page} of {Math.max(1, Math.ceil(totalCount / PAGE_LIMIT))}</span>
              <div className="flex items-center gap-2">
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="px-3 py-1 bg-[#F4F6FA] hover:bg-[#EDF1F7] disabled:opacity-40 rounded text-xs text-slate-700 border border-[#D3DCE7]">Previous</button>
                <button onClick={() => setPage((p) => p + 1)} disabled={page >= Math.ceil(totalCount / PAGE_LIMIT)} className="px-3 py-1 bg-[#F4F6FA] hover:bg-[#EDF1F7] disabled:opacity-40 rounded text-xs text-slate-700 border border-[#D3DCE7]">Next</button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Stored rainfall rows */}
      <div className="space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">Stored rainfall rows from uploaded files (latest run of the station)</h3>
        <StationRunPanel scope="all" focus={null} onImport={onImport} />
      </div>
    </div>
  );
}
