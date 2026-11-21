// Alerts: the flagged rows (SUSPECT or UNCERTAIN) of the selected station that nobody has reviewed yet, highest rule score first.
// Built only from GET /api/validation/review/queue, the same list the Review page reads. There is no alert store, no notification and
// no acknowledge action yet (NOT IMPLEMENTED); an alert here is a flagged row. A row opens in Events.
import { useEffect, useState } from 'react';
import { getQueue } from './api';
import { PAGE_SIZE, queueQuery } from './lib';
import type { QueuePage, QueueRow } from './types';
import { Notice, Panel, SeverityPill, SyntheticBadge, VerdictBadge, formatError } from './ui';

export function AlertsView({ stationId, onOpen }: { stationId: string | null; onOpen: (row: QueueRow) => void }) {
  const [data, setData] = useState<QueuePage | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setPage(1); }, [stationId]);
  useEffect(() => {
    if (!stationId) return;
    let current = true;
    setData(null); setError(null);
    getQueue(queueQuery({ page, status: 'unreviewed', station: stationId })).then((d) => { if (current) setData(d); }).catch((e) => { if (current) setError(formatError(e)); });
    return () => { current = false; };
  }, [stationId, page]);

  if (!stationId) return <Notice tone="info">Select a station in the header to see its alerts.</Notice>;
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!data) return <p className="text-xs text-slate-500">Loading…</p>;
  return (
    <Panel className="p-3 space-y-2">
      <div className="flex items-baseline gap-3 flex-wrap">
        <h2 className="text-sm font-bold text-slate-900">Alerts for {stationId}</h2>
        <span className="text-[11px] font-mono text-slate-500">{data.total} flagged rows not yet reviewed · {PAGE_SIZE} per page · highest rule score first</span>
      </div>
      {data.rows.length === 0 ? <p className="text-xs text-slate-500">No unreviewed flagged rows for this station.</p> : (
        <table className="w-full text-[11px]">
          <thead><tr className="text-left text-[10px] uppercase font-mono text-slate-500"><th className="p-1">Time</th><th>Verdict</th><th>Checks</th><th>Run</th><th className="text-right">Rule score</th></tr></thead>
          <tbody>{data.rows.map((r) => (
            <tr key={`${r.run_id}:${r.id}`} onClick={() => onOpen(r)} className="border-t border-[#E2E8F2] cursor-pointer hover:bg-[#F4F6FA]">
              <td className="p-1 font-mono">{r.time?.slice(0, 16).replace('T', ' ') ?? 'n/a'}</td>
              <td><span className="flex items-center gap-1"><VerdictBadge v={r.verdict} /><SeverityPill s={r.severity} /></span></td>
              <td className="font-mono text-slate-700">{r.checks.join(', ') || 'no check fired'}</td>
              <td className="font-mono">#{r.run_id}{r.synthetic && <> <SyntheticBadge /></>}</td>
              <td className="text-right font-mono">{r.rule_score.toFixed(2)}</td>
            </tr>))}</tbody>
        </table>)}
      <div className="flex items-center justify-between">
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Previous</button>
        <span className="text-[10px] font-mono">{page} of {Math.max(1, data.pages)}</span>
        <button disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Next</button>
      </div>
    </Panel>
  );
}
