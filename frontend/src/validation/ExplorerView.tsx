// Data Explorer: every row of a run (not only the flagged ones) in time order, one station at a time, 50 per page from the server, with
// filters by verdict, check and time window. Open a row for its evidence, the surrounding readings and its review.
import { useEffect, useState } from 'react';
import { getExplorer, getNarrator, getRun, listRuns } from './api';
import { ALL_CHECKS, PAGE_SIZE, explorerQuery } from './lib';
import { EvidencePane } from './EvidencePane';
import type { ExplorerPage, NarratorStatus, RunFull, RunSummary, Verdict } from './types';
import { Notice, Panel, SyntheticBadge, VerdictBadge, formatError } from './ui';

export function ExplorerView({ initialRunId }: { initialRunId: number | null }) {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runId, setRunId] = useState<number | null>(initialRunId);
  const [run, setRun] = useState<RunFull | null>(null);
  const [station, setStation] = useState('');
  const [verdict, setVerdict] = useState<Verdict | 'ALL'>('ALL');
  const [check, setCheck] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<ExplorerPage | null>(null);
  const [narrator, setNarrator] = useState<NarratorStatus | null>(null);
  const [sel, setSel] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns().then((r) => { const ok = r.runs.filter((x) => x.status !== 'failed'); setRuns(ok); setRunId((cur) => cur ?? ok[0]?.id ?? null); }).catch((e) => setError(formatError(e)));
    getNarrator().then(setNarrator).catch(() => setNarrator(null));
  }, []);
  useEffect(() => {
    setRun(null); setStation(''); setSel(null); setPage(1);
    if (runId === null) return;
    getRun(runId).then((r) => { setRun(r); setStation(Object.keys(r.report.stations)[0] ?? ''); }).catch((e) => setError(formatError(e)));
  }, [runId]);
  useEffect(() => { setPage(1); }, [station, verdict, check, from, to]);
  useEffect(() => {
    if (runId === null || !run) return;
    getExplorer(runId, explorerQuery({ page, station, verdict, check, from, to })).then(setData).catch((e) => setError(formatError(e)));
  }, [runId, run, page, station, verdict, check, from, to]);

  const field = 'text-[11px] border border-[#D3DCE7] rounded px-2 py-1';
  if (runs.length === 0 && !error) return <p className="text-xs text-slate-500">No runs to explore yet. Upload a file in Runs, or generate one in Anomaly Lab.</p>;
  return (
    <div className="space-y-3">
      {error && <Notice tone="error">{error}</Notice>}
      <Panel className="p-3 flex items-end gap-3 flex-wrap">
        <label className="text-[10px] font-bold text-slate-600">Run<select value={runId ?? ''} onChange={(e) => setRunId(Number(e.target.value))} className={`${field} block`} aria-label="run">
          {runs.map((r) => <option key={r.id} value={r.id}>#{r.id} {r.label}{r.synthetic ? ' (synthetic)' : ''}</option>)}</select></label>
        <label className="text-[10px] font-bold text-slate-600">Station<select value={station} onChange={(e) => setStation(e.target.value)} className={`${field} block`} aria-label="station">
          <option value="">all stations</option>{Object.keys(run?.report.stations ?? {}).map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
        <label className="text-[10px] font-bold text-slate-600">Verdict<select value={verdict} onChange={(e) => setVerdict(e.target.value as Verdict | 'ALL')} className={`${field} block`} aria-label="verdict">
          {['ALL', 'OK', 'SUSPECT', 'UNCERTAIN', 'NO_DATA'].map((v) => <option key={v} value={v}>{v === 'ALL' ? 'every row' : v}</option>)}</select></label>
        <label className="text-[10px] font-bold text-slate-600">Check<select value={check} onChange={(e) => setCheck(e.target.value)} className={`${field} block`} aria-label="check">
          <option value="">any</option>{ALL_CHECKS.map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
        <label className="text-[10px] font-bold text-slate-600">From<input value={from} onChange={(e) => setFrom(e.target.value)} placeholder="2026-07-01" className={`${field} block w-32`} aria-label="from" /></label>
        <label className="text-[10px] font-bold text-slate-600">To<input value={to} onChange={(e) => setTo(e.target.value)} placeholder="2026-07-31" className={`${field} block w-32`} aria-label="to" /></label>
        {run?.synthetic && <SyntheticBadge />}
      </Panel>
      <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-3">
        <Panel className="p-2 overflow-x-auto">
          <div className="text-[10px] font-mono text-slate-500 px-1 pb-1">{data ? `${data.total} rows · page ${data.page} of ${Math.max(1, data.pages)} · ${PAGE_SIZE} per page · time order` : 'loading…'}</div>
          <table className="w-full text-[11px] font-mono">
            <thead className="text-left bg-[#EDF1F7]"><tr><th className="px-1">time</th><th className="px-1">station</th><th className="px-1 text-right">intensity</th><th className="px-1 text-right">counter</th><th className="px-1 text-right">mm</th><th className="px-1">verdict</th><th className="px-1 text-right">score</th></tr></thead>
            <tbody>{data?.rows.map((r) => (
              <tr key={r.id} onClick={() => setSel(r.id)} className={`border-t border-[#E2E8F2] cursor-pointer ${sel === r.id ? 'bg-sky-50' : 'hover:bg-[#F4F6FA]'}`}>
                <td className="px-1">{r.time?.slice(0, 16).replace('T', ' ')}</td><td className="px-1">{r.station_id}</td>
                <td className="px-1 text-right">{r.intensity ?? '—'}</td><td className="px-1 text-right">{r.accumulation ?? '—'}</td><td className="px-1 text-right">{r.mm ?? '—'}</td>
                <td className="px-1"><VerdictBadge v={r.verdict} /></td><td className="px-1 text-right">{r.rule_score.toFixed(2)}</td></tr>))}</tbody>
          </table>
          {data && data.rows.length === 0 && <p className="p-3 text-xs text-slate-500">No rows match.</p>}
          <div className="flex items-center justify-between p-1 border-t border-[#E2E8F2]">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Previous</button>
            <span className="text-[10px] font-mono">{page}</span>
            <button disabled={!data || page >= data.pages} onClick={() => setPage((p) => p + 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Next</button>
          </div>
        </Panel>
        {runId !== null && sel !== null ? <EvidencePane runId={runId} rowId={sel} narrator={narrator} onSelectRow={setSel} />
          : <Panel className="p-4"><p className="text-xs text-slate-500">Select a row to see its evidence and the readings around it.</p></Panel>}
      </div>
    </div>
  );
}
