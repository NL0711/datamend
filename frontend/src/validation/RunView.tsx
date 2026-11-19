// Run view, layout D (spec section 7): headline numbers and exports, a live strip, the full-width timeline with check lanes, then the
// worklist (server-side pages of 50, highest rule score first), the decision pane and the AI chat. A chart marker, a lane tick and a
// worklist item select the same row.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Download, Radio } from 'lucide-react';
import { exportUrl, getFeed, getNarrator, getRows, getRun, getSeries } from './api';
import { ChatPanel } from './ChatPanel';
import { EvidencePane } from './EvidencePane';
import { Timeline } from './Timeline';
import { PAGE_SIZE, completenessText, pct, rowsQuery } from './lib';
import type { NarratorStatus, RowsPage, RunFull, Series, Verdict } from './types';
import { Notice, Panel, SeverityPill, SyntheticBadge, VerdictBadge, formatError } from './ui';

type Feed = Awaited<ReturnType<typeof getFeed>>;

function LiveStrip() {
  const [feed, setFeed] = useState<Feed | null>(null);
  useEffect(() => { getFeed().then(setFeed).catch(() => setFeed(null)); }, []);
  return (
    <Panel className="px-4 py-2 flex items-center gap-4 flex-wrap text-[11px] font-mono">
      <span className={`flex items-center gap-1.5 font-bold ${feed?.enabled ? 'text-emerald-700' : 'text-slate-500'}`}><Radio className="w-3.5 h-3.5" />LIVE · Weather Union</span>
      {feed === null && <span className="text-slate-500">live feed status unavailable</span>}
      {feed && !feed.enabled && <span className="text-slate-500">feed not enabled (add a key and a city in Settings)</span>}
      {feed?.enabled && (
        <>
          <span>{feed.status.calls_used_today}/{feed.status.calls_used_today + feed.status.calls_remaining_today} calls today</span>
          <span>poll {Math.round(feed.status.poll_interval_seconds / 60)} min</span>
          <span>time basis: received</span>
          <span>{feed.stations.filter((s) => s.quality?.assessment === 'OK').length} of {feed.stations.length} gauges OK</span>
        </>)}
    </Panel>
  );
}

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
      <p className="text-[10px] text-slate-500">{h.basis}. {run.report.score_note}. Thresholds are design choices, uncalibrated.</p>
      {run.not_run.length > 0 && (
        <div className="text-[11px]"><span className="font-bold">Checks not run ({run.not_run.length}):</span>
          <ul className="font-mono text-slate-600 mt-1">{run.not_run.map((n, i) => <li key={i}>{n.check}{n.station_id ? ` · ${n.station_id}` : ''}: {n.reason}</li>)}</ul></div>)}
      {Object.keys(run.renamed_headers).length > 0 && <p className="text-[11px] text-slate-600">Headers renamed: {Object.entries(run.renamed_headers).map(([a, b]) => `${a} → ${b}`).join(', ')}</p>}
    </Panel>
  );
}

export function RunView({ runId }: { runId: number }) {
  const [run, setRun] = useState<RunFull | null>(null);
  const [narrator, setNarrator] = useState<NarratorStatus | null>(null);
  const [station, setStation] = useState<string | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
  const [page, setPage] = useState(1);
  const [verdict, setVerdict] = useState<Verdict | 'ALL'>('ALL');
  const [check, setCheck] = useState('');
  const [everyStation, setEveryStation] = useState(false);
  const [rows, setRows] = useState<RowsPage | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRun(null); setStation(null); setSeries(null); setSelected(null); setPage(1); setError(null);
    getRun(runId).then((r) => {
      setRun(r);
      const st = Object.entries(r.report.stations).sort((a, b) => (b[1].verdicts.SUSPECT ?? 0) + (b[1].verdicts.UNCERTAIN ?? 0) - ((a[1].verdicts.SUSPECT ?? 0) + (a[1].verdicts.UNCERTAIN ?? 0)));
      setStation(st[0]?.[0] ?? null);
    }).catch((e) => setError(formatError(e)));
    getNarrator().then(setNarrator).catch(() => setNarrator(null));
  }, [runId]);

  useEffect(() => {
    if (!station) return;
    getSeries(runId, station).then(setSeries).catch((e) => setError(formatError(e)));
  }, [runId, station]);

  const stationFilter = everyStation ? undefined : station ?? undefined;
  useEffect(() => { setPage(1); }, [verdict, check, everyStation, station]);
  useEffect(() => {
    if (!run) return;
    getRows(runId, rowsQuery({ page, verdict, check, station: stationFilter })).then(setRows).catch((e) => setError(formatError(e)));
  }, [runId, run, page, verdict, check, stationFilter]);

  const checks = useMemo(() => Object.keys(run?.report.checks ?? {}).sort(), [run]);
  const pick = useCallback((id: number) => setSelected(id), []);

  if (error && !run) return <Notice tone="error">{error}</Notice>;
  if (!run) return <p className="text-xs text-slate-500">Loading run…</p>;
  if (run.status === 'failed') return <Notice tone="error">Run {run.id} was rejected: {run.error}</Notice>;

  return (
    <div className="space-y-3">
      {error && <Notice tone="error">{error}</Notice>}
      <LiveStrip />
      <Headline run={run} />
      <Panel className="p-3">
        <div className="flex items-center gap-2 flex-wrap mb-2">
          {Object.keys(run.report.stations).map((s) => (
            <button key={s} onClick={() => { setStation(s); setSelected(null); }}
                    className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${station === s ? 'bg-sky-600 text-white border-sky-600' : 'border-[#D3DCE7] text-slate-600'}`}>{s}</button>))}
          {station && <span className="ml-auto text-[11px] font-mono text-slate-500">completeness {completenessText(run.report.stations[station]?.completeness)}</span>}
        </div>
        {series ? <Timeline series={series} selectedId={selected} onSelect={pick} profile={run.profile} /> : <p className="text-xs text-slate-500">Loading series…</p>}
      </Panel>
      <div className="grid lg:grid-cols-[380px_1fr] gap-3">
        <Panel className="p-2 flex flex-col h-[640px]">
          <div className="flex gap-1 flex-wrap p-1 items-center">
            {(['ALL', 'SUSPECT', 'UNCERTAIN', 'NO_DATA'] as const).map((f) => (
              <button key={f} onClick={() => setVerdict(f)} className={`px-2 py-0.5 rounded text-[10px] font-bold border ${verdict === f ? 'bg-slate-900 text-white border-slate-900' : 'border-[#D3DCE7] text-slate-600'}`}>{f === 'ALL' ? 'FLAGGED' : f}</button>))}
            <label className="ml-auto text-[10px] text-slate-600 flex items-center gap-1"><input type="checkbox" checked={everyStation} onChange={(e) => setEveryStation(e.target.checked)} />all stations</label>
          </div>
          <select value={check} onChange={(e) => setCheck(e.target.value)} className="mx-1 mb-1 text-[11px] border border-[#D3DCE7] rounded px-1 py-0.5" aria-label="filter by check">
            <option value="">any check</option>{checks.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <div className="text-[10px] font-mono text-slate-500 px-2 pb-1">
            {rows ? `${rows.total} rows · page ${rows.page} of ${Math.max(1, rows.pages)} · ${PAGE_SIZE} per page · highest rule score first` : 'loading…'}
          </div>
          <ul className="overflow-y-auto flex-1">
            {rows?.rows.map((r) => (
              <li key={r.id} onClick={() => setSelected(r.id)} className={`px-2 py-2 border-t border-[#E2E8F2] cursor-pointer ${selected === r.id ? 'bg-sky-50' : 'hover:bg-[#F4F6FA]'}`}>
                <div className="flex items-center gap-2"><VerdictBadge v={r.verdict} /><SeverityPill s={r.severity} /><span className="text-xs font-mono">{r.time?.slice(0, 16).replace('T', ' ')}</span><span className="ml-auto text-[10px] font-mono">{r.rule_score.toFixed(2)}</span></div>
                <div className="text-[11px] text-slate-700 mt-0.5">{r.station_id} · <span className="font-mono">{r.checks.join(', ') || 'no check fired'}</span></div>
              </li>))}
            {rows && rows.rows.length === 0 && <li className="p-3 text-xs text-slate-500">Nothing flagged for this filter.</li>}
          </ul>
          <div className="flex items-center justify-between p-1 border-t border-[#E2E8F2]">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Previous</button>
            <span className="text-[10px] font-mono">{page}</span>
            <button disabled={!rows || page >= rows.pages} onClick={() => setPage((p) => p + 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Next</button>
          </div>
        </Panel>
        <div className="space-y-3">
          <EvidencePane runId={run.id} rowId={selected} narrator={narrator} />
          <ChatPanel runId={run.id} rowId={selected} narrator={narrator} />
        </div>
      </div>
    </div>
  );
}
