// Run view: headline numbers and exports, the full-width timeline with check lanes, then the row list (flagged rows by rule score, or every
// row in time order, server-side pages of 50) with the decision pane. A chart marker, a lane tick and a list item select the same row.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';
import { exportUrl, getNarrator, getRows, getRun, getSeries } from './api';
import { EvidencePane } from './EvidencePane';
import { Timeline } from './Timeline';
import { PAGE_SIZE, completenessText, explorerQuery, pct, rowsQuery } from './lib';
import type { NarratorStatus, RowsPage, RunFull, Series, Verdict } from './types';
import { Notice, Panel, SeverityPill, SyntheticBadge, VerdictBadge, formatError } from './ui';

function Headline({ run }: { run: RunFull }) {
  const h = run.report.headline;
  const cell = (label: string, value: string) => (
    <div className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-3 py-2"><div className="text-[10px] uppercase font-mono text-slate-500">{label}</div><div className="text-sm font-bold font-mono">{value}</div></div>);
  return (
    <Panel className="p-3 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <h2 className="text-base font-bold text-slate-900">Run {run.id} · {run.label}</h2>
        {run.synthetic && <SyntheticBadge />}
        <span className="text-[10px] font-mono text-slate-500" title={`platform v${run.platform_version} · commit ${run.git_commit} · input sha256 ${run.input_sha256 ?? 'n/a'}`}>{run.profile} profile · {run.source} · {run.status}</span>
        <span className="ml-auto flex items-center gap-2">
          <a href={exportUrl(run.id, 'json')} className="px-2 py-1 rounded border border-[#D3DCE7] text-[11px] font-bold flex items-center gap-1"><Download className="w-3 h-3" />JSON</a>
          <a href={exportUrl(run.id, 'csv')} className="px-2 py-1 rounded border border-[#D3DCE7] text-[11px] font-bold flex items-center gap-1"><Download className="w-3 h-3" />CSV</a>
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {cell('Completeness', completenessText(h.completeness))}
        {cell('SUSPECT', pct(h.share_suspect))}
        {cell('UNCERTAIN', pct(h.share_uncertain))}
        {cell('NO_DATA', pct(h.share_no_data))}
        {cell('Rows · stations', `${h.rows} · ${h.stations}`)}
      </div>
      <p className="text-[10px] text-slate-500">{h.basis}. Rule scores are uncalibrated.</p>
      {run.not_run.length > 0 && (
        <div className="text-[11px]"><span className="font-bold">Checks not run ({run.not_run.length}):</span>
          <ul className="font-mono text-slate-600 mt-1">{run.not_run.map((n, i) => <li key={i}>{n.check}{n.station_id ? ` · ${n.station_id}` : ''}: {n.reason}</li>)}</ul></div>)}
      {Object.keys(run.renamed_headers).length > 0 && <p className="text-[11px] text-slate-600">Headers renamed: {Object.entries(run.renamed_headers).map(([a, b]) => `${a} → ${b}`).join(', ')}</p>}
    </Panel>
  );
}

/** `forcedStation`: the shell's selected station (the station pills are then hidden, unless the run has no rows for it). `fixedScope`:
 *  Events shows flagged rows only, Explorer every row, so the scope switch is hidden. `initialRowId`: a row opened from the Alerts list. */
export function RunView({ runId, onSelectRow, forcedStation, fixedScope, initialRowId }: {
  runId: number; onSelectRow?: (id: number | null) => void; forcedStation?: string; fixedScope?: 'flagged' | 'all'; initialRowId?: number | null;
}) {
  const [run, setRun] = useState<RunFull | null>(null);
  const [narrator, setNarrator] = useState<NarratorStatus | null>(null);
  const [pickedStation, setStation] = useState<string | null>(null);
  const forced = forcedStation && run && forcedStation in run.report.stations ? forcedStation : undefined;
  const station = forced ?? pickedStation;
  const [series, setSeries] = useState<Series | null>(null);
  const [page, setPage] = useState(1);
  const [verdict, setVerdict] = useState<Verdict | 'ALL'>('ALL');
  const [check, setCheck] = useState('');
  const [everyStation, setEveryStation] = useState(false);
  const [scope, setScope] = useState<'flagged' | 'all'>(fixedScope ?? 'flagged');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [rows, setRows] = useState<RowsPage | null>(null);
  const [selected, setSelected] = useState<number | null>(initialRowId ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRun(null); setStation(null); setSeries(null); setSelected(initialRowId ?? null); setPage(1); setError(null);
    getRun(runId).then((r) => {
      setRun(r);
      const st = Object.entries(r.report.stations).sort((a, b) => (b[1].verdicts.SUSPECT ?? 0) + (b[1].verdicts.UNCERTAIN ?? 0) - ((a[1].verdicts.SUSPECT ?? 0) + (a[1].verdicts.UNCERTAIN ?? 0)));
      setStation(st[0]?.[0] ?? null);
    }).catch((e) => setError(formatError(e)));
    getNarrator().then(setNarrator).catch(() => setNarrator(null));
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!station) return;
    getSeries(runId, station).then(setSeries).catch((e) => setError(formatError(e)));
  }, [runId, station]);

  const stationFilter = everyStation ? undefined : station ?? undefined;
  useEffect(() => { setPage(1); }, [verdict, check, everyStation, station, scope, from, to]);
  useEffect(() => { if (scope === 'flagged' && verdict === 'OK') setVerdict('ALL'); }, [scope, verdict]);
  useEffect(() => {
    if (!run) return;
    const q = scope === 'all' ? explorerQuery({ page, verdict, check, station: stationFilter, from, to }) : rowsQuery({ page, verdict, check, station: stationFilter });
    getRows(runId, q).then(setRows).catch((e) => setError(formatError(e)));
  }, [runId, run, page, verdict, check, stationFilter, scope, from, to]);

  useEffect(() => { onSelectRow?.(selected); }, [selected, onSelectRow]);
  useEffect(() => () => onSelectRow?.(null), [onSelectRow]);

  const checks = useMemo(() => Object.keys(run?.report.checks ?? {}).sort(), [run]);
  const pick = useCallback((id: number) => setSelected(id), []);

  if (error && !run) return <Notice tone="error">{error}</Notice>;
  if (!run) return <p className="text-xs text-slate-500">Loading run…</p>;
  if (run.status === 'failed') return <Notice tone="error">Run {run.id} was rejected: {run.error}</Notice>;

  return (
    <div className="space-y-3">
      {error && <Notice tone="error">{error}</Notice>}
      <Headline run={run} />
      {forcedStation && !forced && <Notice tone="info">Run #{run.id} has no rows for station {forcedStation}; showing {station ?? 'its first station'} instead.</Notice>}
      <Panel className="p-3">
        <div className="flex items-center gap-2 flex-wrap mb-2">
          {forced ? <span className="text-[11px] font-mono text-slate-600">station {forced} · run #{run.id}</span> : Object.keys(run.report.stations).map((s) => (
            <button key={s} onClick={() => { setStation(s); setSelected(null); }}
                    className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${station === s ? 'bg-sky-600 text-white border-sky-600' : 'border-[#D3DCE7] text-slate-600'}`}>{s}</button>))}
          {station && <span className="ml-auto text-[11px] font-mono text-slate-500">completeness {completenessText(run.report.stations[station]?.completeness)}</span>}
        </div>
        {series ? <Timeline series={series} selectedId={selected} onSelect={pick} profile={run.profile} /> : <p className="text-xs text-slate-500">Loading series…</p>}
      </Panel>
      <div className="grid lg:grid-cols-[380px_1fr] gap-3">
        <Panel className="p-2 flex flex-col h-[640px]">
          <div className="flex gap-1 p-1" role="tablist" aria-label="row scope" hidden={!!fixedScope}>
            {(['flagged', 'all'] as const).map((s) => (
              <button key={s} role="tab" aria-selected={scope === s} onClick={() => setScope(s)}
                      className={`flex-1 px-2 py-1 rounded text-[11px] font-bold ${scope === s ? 'bg-sky-600 text-white' : 'bg-[#F4F6FA] text-slate-600'}`}>{s === 'flagged' ? 'Flagged rows' : 'All rows'}</button>))}
          </div>
          <div className="flex gap-1 flex-wrap p-1 items-center">
            {(scope === 'all' ? ['ALL', 'OK', 'SUSPECT', 'UNCERTAIN', 'NO_DATA'] : ['ALL', 'SUSPECT', 'UNCERTAIN', 'NO_DATA'] as const).map((f) => (
              <button key={f} onClick={() => setVerdict(f as Verdict | 'ALL')} className={`px-2 py-0.5 rounded text-[10px] font-bold border ${verdict === f ? 'bg-slate-900 text-white border-slate-900' : 'border-[#D3DCE7] text-slate-600'}`}>{f === 'ALL' ? (scope === 'all' ? 'EVERY' : 'FLAGGED') : f}</button>))}
            <label className="ml-auto text-[10px] text-slate-600 flex items-center gap-1" hidden={!!forced}><input type="checkbox" checked={everyStation} onChange={(e) => setEveryStation(e.target.checked)} />all stations</label>
          </div>
          {scope === 'all' && (
            <div className="flex gap-1 px-1 pb-1">
              <input value={from} onChange={(e) => setFrom(e.target.value)} placeholder="from 2026-07-01" aria-label="from" className="flex-1 min-w-0 text-[11px] border border-[#D3DCE7] rounded px-1 py-0.5" />
              <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="to 2026-07-31" aria-label="to" className="flex-1 min-w-0 text-[11px] border border-[#D3DCE7] rounded px-1 py-0.5" />
            </div>)}
          <select value={check} onChange={(e) => setCheck(e.target.value)} className="mx-1 mb-1 text-[11px] border border-[#D3DCE7] rounded px-1 py-0.5" aria-label="filter by check">
            <option value="">any check</option>{checks.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className="text-[10px] font-mono text-slate-500 px-2 pb-1">
            {rows ? `${rows.total} rows · page ${rows.page} of ${Math.max(1, rows.pages)} · ${PAGE_SIZE} per page · ${scope === 'all' ? 'time order' : 'highest score first'}` : 'loading…'}
          </div>
          <ul className="overflow-y-auto flex-1">
            {rows?.rows.map((r) => (
              <li key={r.id} onClick={() => setSelected(r.id)} className={`px-2 py-2 border-t border-[#E2E8F2] cursor-pointer ${selected === r.id ? 'bg-sky-50' : 'hover:bg-[#F4F6FA]'}`}>
                <div className="flex items-center gap-2"><VerdictBadge v={r.verdict} /><SeverityPill s={r.severity} /><span className="text-xs font-mono">{r.time?.slice(0, 16).replace('T', ' ')}</span><span className="ml-auto text-[10px] font-mono">{r.rule_score.toFixed(2)}</span></div>
                <div className="text-[11px] text-slate-700 mt-0.5">{r.station_id} · <span className="font-mono">{r.checks.join(', ') || 'no check fired'}</span></div>
              </li>))}
            {rows && rows.rows.length === 0 && <li className="p-3 text-xs text-slate-500">No rows match.</li>}
          </ul>
          <div className="flex items-center justify-between p-1 border-t border-[#E2E8F2]">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Previous</button>
            <span className="text-[10px] font-mono">{page}</span>
            <button disabled={!rows || page >= rows.pages} onClick={() => setPage((p) => p + 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Next</button>
          </div>
        </Panel>
        <div className="space-y-3">
          <EvidencePane runId={run.id} rowId={selected} narrator={narrator} onSelectRow={pick} />
        </div>
      </div>
    </div>
  );
}
