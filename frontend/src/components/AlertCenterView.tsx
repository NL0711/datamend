// Alert Center in the layout of the ORIGINAL dashboard (four metric cards, a filter toolbar, the incident table on the left, the dossier on
// the right), restored in slice S2b. The DATA is the platform's own, as in S2: an alert is a flagged rainfall row (SUSPECT or UNCERTAIN)
// that nobody has reviewed yet, read from GET /api/validation/review/queue. The dossier is the evidence pane (original row, evidence behind
// each flag, review box). There is no alert store, no acknowledge and no notification (NOT IMPLEMENTED). The original read /api/anomalies
// (temperature, pressure, humidity); that list is shown under the dossier through AnomalyFeed, with the evidence of every check that
// fired, and lists a reading only when the stream's checks really flagged it.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { getNarrator, getQueue, getReviewSummary } from '../validation/api';
import { errorText, fetchAnomalyStats, isNotBuilt } from '../services/api';
import { streamStatsLine } from '../services/geo';
import type { AnomalyStats } from '../types';
import { ALL_CHECKS, PAGE_SIZE, queueQuery } from '../validation/lib';
import { EvidencePane } from '../validation/EvidencePane';
import type { NarratorStatus, QueuePage, QueueRow, ReviewSummary } from '../validation/types';
import { useStation } from '../validation/StationContext';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { MetricCard } from '../design-system/components/MetricCard';
import { EmptyState } from '../design-system/components/EmptyState';
import { TableSkeleton } from '../design-system/components/SkeletonLoader';
import { AnomalyFeed } from './AnomalyFeed';
import { verdictVariant } from './severity';

interface AlertCenterViewProps {
  onNavigateToEvent?: (row: QueueRow) => void;
  onLocateOnGlobe?: (stationId: string) => void;
  onImport?: () => void;
}

const field = 'bg-[#F4F6FA] border border-[#D3DCE7] text-slate-700 rounded-lg px-3 py-1.5 focus:outline-none focus:border-sky-500 font-bold';

export function AlertCenterView({ onNavigateToEvent, onLocateOnGlobe, onImport }: AlertCenterViewProps = {}) {
  const { stationId } = useStation();
  const [fleetWide, setFleetWide] = useState<boolean>(false);
  const [status, setStatus] = useState<'unreviewed' | 'reviewed' | 'all'>('unreviewed');
  const [verdict, setVerdict] = useState<'' | 'SUSPECT' | 'UNCERTAIN'>('');
  const [check, setCheck] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [page, setPage] = useState<number>(1);

  const [data, setData] = useState<QueuePage | null>(null);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [narrator, setNarrator] = useState<NarratorStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<{ run: number; id: number } | null>(null);
  const [streamStats, setStreamStats] = useState<AnomalyStats | null>(null);
  const [streamStatsError, setStreamStatsError] = useState<string | null>(null);

  const station = fleetWide ? '' : stationId ?? '';

  const load = useCallback(() => {
    setError(null);
    getQueue(queueQuery({ page, status, verdict, check, station })).then(setData).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    getReviewSummary().then(setSummary).catch(() => undefined);
  }, [page, status, verdict, check, station]);

  useEffect(() => { setData(null); load(); }, [load]);
  useEffect(() => { setPage(1); setSel(null); }, [station, status, verdict, check]);
  useEffect(() => {
    fetchAnomalyStats(24).then((s) => { setStreamStats(s); setStreamStatsError(null); }).catch((e) => { setStreamStats(null); setStreamStatsError(isNotBuilt(e) ? 'not available on this server' : errorText(e)); });
  }, []);
  useEffect(() => { getNarrator().then(setNarrator).catch(() => setNarrator(null)); }, []);

  const rows = data?.rows ?? [];
  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return rows;
    const q = searchQuery.toLowerCase();
    return rows.filter((r) => r.station_id.toLowerCase().includes(q) || r.checks.join(' ').toLowerCase().includes(q) || `#${r.id}`.includes(q) || (r.time ?? '').includes(q));
  }, [rows, searchQuery]);

  // keep a selection that exists on this page; otherwise the first row of the page
  useEffect(() => {
    if (filtered.length === 0) return;
    if (!sel || !filtered.some((r) => r.run_id === sel.run && r.id === sel.id)) setSel({ run: filtered[0].run_id, id: filtered[0].id });
  }, [filtered]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedRow = sel ? filtered.find((r) => r.run_id === sel.run && r.id === sel.id) ?? null : null;

  return (
    <div className="space-y-6">
      {/* Stream detections of the last 24 hours (GET /api/anomalies/stats; network-wide, the API has no station filter) */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl px-4 py-3 shadow-lg text-xs font-mono text-slate-700" data-testid="stream-stats">
        <b className="uppercase tracking-wider text-slate-900">Section 1, live stream: detections in the last 24 h, all stations</b>:{streamStatsLine(streamStats, streamStatsError)}
      </div>

      {/* 4 summary metric cards: counts of the stored flagged rainfall rows (uploaded files), all stations */}
      <p className="text-[11px] font-mono text-slate-500 -mb-3">Section 2, uploaded files: the four cards below count flagged readings of imported files, not stream detections. Stream detections for the chosen station are listed again at the bottom right.</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Flagged Rows (rainfall review queue)"
          value={summary?.flagged_rows ?? '…'}
          unit="rows"
          delta={{ value: 'All runs', isNeutral: true }}
          footerLeft={<span>SUSPECT or UNCERTAIN</span>}
          footerRight={<span className="text-slate-600 font-semibold">Rule checks</span>}
        />
        <MetricCard
          label="Awaiting Review (rainfall)"
          value={summary?.unreviewed_rows ?? '…'}
          unit="rows"
          delta={{ value: 'Open alerts', isPositive: false }}
          footerLeft={<span>No reviewer decision yet</span>}
          footerRight={<span className="text-amber-600 font-semibold">Needs a reviewer</span>}
        />
        <MetricCard
          label="Confirmed Faults (rainfall)"
          value={summary?.by_decision.confirmed_fault ?? '…'}
          unit="rows"
          delta={{ value: 'Reviewer decision', isNeutral: true }}
          footerLeft={<span>Latest decision per row</span>}
          footerRight={<span className="text-rose-600 font-semibold">Confirmed</span>}
        />
        <MetricCard
          label="Genuine Extremes Kept (rainfall)"
          value={summary?.by_decision.genuine_extreme ?? '…'}
          unit="rows"
          delta={{ value: 'Reviewer decision', isNeutral: true }}
          footerLeft={<span>Never called a fault by size</span>}
          footerRight={<span className="text-cyan-600 font-semibold">Preserved raw</span>}
        />
      </div>

      {/* Filter & search toolbar */}
      <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
        <div className="flex flex-wrap items-center gap-3 flex-1 min-w-[280px]">
          <div className="relative flex-1 min-w-[200px]">
            <input
              type="text"
              placeholder="Search row #, station, check or time on this page..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-[#F4F6FA] border border-[#D3DCE7] rounded-lg px-3 py-1.5 text-slate-700 placeholder-slate-500 focus:outline-none focus:border-sky-500"
            />
          </div>

          <span className="text-slate-600 font-bold">
            {station ? <>Station <span className="text-sky-600">{station}</span></> : 'All stations'}
          </span>
          {stationId && (
            <label className="flex items-center gap-1 text-slate-600">
              <input type="checkbox" checked={fleetWide} onChange={(e) => setFleetWide(e.target.checked)} /> Show all stations
            </label>
          )}

          <select value={status} onChange={(e) => setStatus(e.target.value as 'unreviewed' | 'reviewed' | 'all')} className={field} aria-label="review status">
            <option value="unreviewed">Not reviewed (alerts)</option>
            <option value="reviewed">Reviewed</option>
            <option value="all">All flagged rows</option>
          </select>
          <select value={verdict} onChange={(e) => setVerdict(e.target.value as '' | 'SUSPECT' | 'UNCERTAIN')} className={field} aria-label="verdict">
            <option value="">All Verdicts</option>
            <option value="SUSPECT">SUSPECT</option>
            <option value="UNCERTAIN">UNCERTAIN</option>
          </select>
          <select value={check} onChange={(e) => setCheck(e.target.value)} className={field} aria-label="check">
            <option value="">All Checks</option>
            {ALL_CHECKS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>

        <button onClick={load} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#F4F6FA] hover:bg-[#EDF1F7] text-slate-700 rounded-lg border border-[#D3DCE7] transition-all">
          Refresh
        </button>
      </div>

      {error && <div className="p-3 rounded-xl border border-rose-300 bg-rose-50 text-xs text-rose-800 font-mono">{error}</div>}

      {/* Main grid: incident table and dossier */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5 bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-5 shadow-lg flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono flex items-center gap-2">
                Section 2: flagged readings from uploaded files ({data ? data.total : '…'})
              </h3>
              <span className="text-[11px] font-mono text-slate-500">Click one for its evidence</span>
            </div>

            <div className="overflow-x-auto max-h-[700px] overflow-y-auto pr-1">
              <table className="w-full text-left text-xs font-mono">
                <thead className="sticky top-0 bg-[#FFFFFF] z-10">
                  <tr className="border-b border-slate-200 text-slate-500 font-sans font-semibold uppercase text-[11px] tracking-wider">
                    <th className="pb-3">Time (UTC)</th>
                    <th className="pb-3">Station</th>
                    <th className="pb-3">Verdict</th>
                    <th className="pb-3">Checks</th>
                    <th className="pb-3 text-right">Rule score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {!data && !error ? (
                    <tr><td colSpan={5} className="py-6"><TableSkeleton rows={8} /></td></tr>
                  ) : filtered.length === 0 ? (
                    <tr><td colSpan={5} className="py-12 text-center text-slate-600 font-sans space-y-2">
                      <p>{status === 'unreviewed' && !verdict && !check && !searchQuery.trim()
                        ? `Nothing is waiting for review${station ? ` at ${station}` : ''}. Flags from uploaded files appear here once a file is imported and checked.`
                        : 'No flagged readings match these filters. Loosen a filter to see more.'}</p>
                      <div className="flex justify-center gap-2">
                        {onImport && <button onClick={onImport} className="px-3 py-1.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg shadow">Import a file</button>}
                        {stationId && !fleetWide && <button onClick={() => setFleetWide(true)} className="px-3 py-1.5 bg-[#EDF1F7] hover:bg-[#E2E8F2] text-slate-700 font-mono font-semibold text-xs rounded-lg border border-[#D3DCE7]">Show all stations</button>}
                      </div>
                    </td></tr>
                  ) : (
                    filtered.map((r) => {
                      const isSelected = sel?.run === r.run_id && sel.id === r.id;
                      return (
                        <tr
                          key={`${r.run_id}:${r.id}`}
                          onClick={() => setSel({ run: r.run_id, id: r.id })}
                          className={`hover:bg-[#EDF1F7] transition-colors cursor-pointer ${isSelected ? 'bg-sky-500/15 border-l-4 border-sky-400 text-slate-900 font-semibold' : 'text-slate-600'}`}
                        >
                          <td className="py-3 text-slate-600">{r.time?.slice(0, 16).replace('T', ' ') ?? 'n/a'}</td>
                          <td className="py-3 font-bold text-slate-900">
                            <span>{r.station_id}</span>
                            <span className="text-[10px] text-slate-500 block font-normal">run #{r.run_id}</span>
                          </td>
                          <td className="py-3"><StatusBadge label={r.verdict} variant={verdictVariant(r.verdict)} size="sm" /></td>
                          <td className="py-3 text-slate-700">{r.checks.join(', ') || 'no check fired'}</td>
                          <td className="py-3 text-right font-bold text-sky-600">{r.rule_score.toFixed(2)}</td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500 font-mono">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-3 py-1 bg-[#F4F6FA] hover:bg-[#EDF1F7] disabled:opacity-40 rounded text-xs text-slate-700 border border-[#D3DCE7]">Previous</button>
            <span>Page {page} of {Math.max(1, data?.pages ?? 1)} · {PAGE_SIZE} per page · highest score first</span>
            <button disabled={!data || page >= data.pages} onClick={() => setPage((p) => p + 1)} className="px-3 py-1 bg-[#F4F6FA] hover:bg-[#EDF1F7] disabled:opacity-40 rounded text-xs text-slate-700 border border-[#D3DCE7]">Next</button>
          </div>
        </div>

        {/* Right 7 cols: the dossier */}
        <div className="lg:col-span-7 space-y-4">
          {selectedRow ? (
            <>
              <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">Flagged reading <span className="text-sky-600">#{selectedRow.id}</span></h3>
                  <span className="text-[10px] text-slate-500 font-sans">The original reading, the evidence behind each flag and your review. A review never changes a verdict or score.</span>
                </div>
                <div className="flex items-center gap-2">
                  {onLocateOnGlobe && (
                    <button onClick={() => onLocateOnGlobe(selectedRow.station_id)} className="py-2 px-3 bg-[#EDF1F7] hover:bg-[#E2E8F2] border border-sky-500/40 hover:border-sky-400 text-sky-700 hover:text-slate-900 rounded-lg text-xs font-mono font-bold transition-all">
                      Show {selectedRow.station_id} on the map
                    </button>
                  )}
                  {onNavigateToEvent && (
                    <button onClick={() => onNavigateToEvent(selectedRow)} className="py-2 px-3 bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold rounded-lg text-xs font-mono transition-all shadow-md">
                      Open in Events →
                    </button>
                  )}
                </div>
              </div>
              <EvidencePane runId={selectedRow.run_id} rowId={selectedRow.id} narrator={narrator} onSelectRow={(id) => setSel({ run: selectedRow.run_id, id })} onReviewed={load} />
            </>
          ) : (
            <EmptyState
              title="No flagged reading selected"
              description="Click a reading in the list on the left to read the evidence for its flag. When the list is empty, nothing is waiting for review with these filters."
            />
          )}

          <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">Live stream detections (temperature, pressure, humidity, rain)</h4>
            <AnomalyFeed stationId={station || null} limit={8} evidence />
          </div>
        </div>
      </div>
    </div>
  );
}
