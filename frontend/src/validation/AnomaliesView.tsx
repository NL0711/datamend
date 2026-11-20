// Step 6, Anomalies: the flagged items of the chosen run with their evidence and explanation (rule-based baseline now, the narrator when
// connected), a panel that says how a flag is made (from the server's model card), and the synthetic-fault lab, collapsed.
import { useEffect, useState } from 'react';
import { getModelCard, getNarrator, getRows } from './api';
import { EvidencePane } from './EvidencePane';
import { LabView } from './LabView';
import { PAGE_SIZE, rowsQuery } from './lib';
import type { ImportedJob, ModelCard, NarratorStatus, RowsPage } from './types';
import { NextButton, Notice, Panel, SeverityPill, VerdictBadge, field, formatError } from './ui';

export function HowFlagged() {
  const [card, setCard] = useState<ModelCard | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { getModelCard().then(setCard).catch((e) => setError(formatError(e))); }, []);
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!card) return <p className="text-xs text-slate-500">Loading how flags are made…</p>;
  return (
    <div className="space-y-3 text-xs">
      <p className="text-slate-700">{card.method}</p>
      {card.flags_how.length > 0 && <ul className="list-disc ml-5 space-y-0.5 text-slate-800">{card.flags_how.map((s, i) => <li key={i}>{s}</li>)}</ul>}
      <div className="overflow-x-auto"><table className="w-full text-[11px]">
        <thead className="text-left bg-[#EDF1F7]"><tr><th className="px-2 py-1">Check</th><th className="px-2">Layer</th><th className="px-2">Kind</th><th className="px-2 text-right">Weight</th><th className="px-2">Needs</th><th className="px-2">Threshold</th></tr></thead>
        <tbody>{card.checks.map((c) => (
          <tr key={`${c.profile}-${c.name}`} className="border-t border-[#E2E8F2] align-top">
            <td className="px-2 py-0.5 font-mono font-bold">{c.name}<div className="text-[10px] text-slate-400 font-normal">{c.profile} profile</div></td><td className="px-2">{c.layer}</td><td className="px-2">{c.kind}</td>
            <td className="px-2 text-right font-mono">{c.weight ?? '-'}</td><td className="px-2">{Array.isArray(c.needs) ? c.needs.join(', ') : c.needs ?? '-'}</td><td className="px-2">{c.threshold_note ?? '-'}</td></tr>))}</tbody></table></div>
      <div className="rounded border border-[#D3DCE7] px-3 py-2">
        <div className="text-[10px] uppercase font-mono text-slate-500">Champion label model</div>
        {card.champion
          ? <p><b>{card.champion.name} {card.champion.version}</b>{card.champion.trained_from_snapshot !== null ? ` · trained from snapshot #${card.champion.trained_from_snapshot}` : ''} · <span className="font-mono font-bold">declared, not verified</span>
              <span className="block text-slate-500">{card.champion.metrics_basis}</span></p>
          : <p className="text-slate-600">None. Flags come from the rule score only (uncalibrated).</p>}
      </div>
      <div className="rounded border border-[#D3DCE7] px-3 py-2">
        <div className="text-[10px] uppercase font-mono text-slate-500">Explainer in use</div>
        <p><span className="font-mono font-bold">{card.explanation.generator}</span> · AI narrator {card.explanation.narrator_connected ? 'connected' : 'not connected'}. {card.explanation.note}</p>
      </div>
      {card.not_implemented.length > 0 && (
        <div className="rounded border border-dashed border-slate-400 bg-slate-50 px-3 py-2"><div className="font-bold">NOT IMPLEMENTED</div>
          <ul className="list-disc ml-5 mt-1">{card.not_implemented.map((s, i) => <li key={i}>{s}</li>)}</ul></div>)}
    </div>);
}

export function AnomaliesView({ jobs, runId, onRun, onOpened, onNext }: { jobs: ImportedJob[]; runId: number | null; onRun: (id: number) => void; onOpened: () => void; onNext: () => void }) {
  const runs = jobs.filter((j) => j.run_id !== null);
  const [rows, setRows] = useState<RowsPage | null>(null);
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<number | null>(null);
  const [narrator, setNarrator] = useState<NarratorStatus | null>(null);
  const [error, setError] = useState('');

  useEffect(() => { onOpened(); getNarrator().then(setNarrator).catch(() => setNarrator(null)); }, [onOpened]);
  useEffect(() => { if (runId === null && runs[0]?.run_id) onRun(runs[0].run_id); }, [runId, runs, onRun]);
  useEffect(() => { setPage(1); setSel(null); }, [runId]);
  useEffect(() => {
    if (runId === null) { setRows(null); return; }
    getRows(runId, rowsQuery({ page, verdict: 'ALL' })).then((r) => { setRows(r); setError(''); }).catch((e) => setError(formatError(e)));
  }, [runId, page]);

  return (
    <div className="space-y-3">
      {error && <Notice tone="error">{error}</Notice>}
      {runs.length === 0 && runId === null ? <Notice tone="info">No run yet: run the checks in step 4 and its flagged items appear here.</Notice> : (
        <>
          <Panel className="p-3 flex items-end gap-3 flex-wrap">
            <label className="text-xs font-bold block">Run
              <select value={runId ?? ''} onChange={(e) => onRun(Number(e.target.value))} className={`${field} block mt-1`} aria-label="run">
                {runs.map((j) => <option key={j.run_id as number} value={j.run_id as number}>run {j.run_id} · {j.filename}</option>)}
                {runId !== null && !runs.some((j) => j.run_id === runId) && <option value={runId}>run {runId}</option>}</select></label>
            <span className="text-[11px] font-mono text-slate-500">{rows ? `${rows.total} flagged · page ${rows.page} of ${Math.max(1, rows.pages)} · ${PAGE_SIZE} per page · highest rule score first` : 'loading…'}</span>
          </Panel>
          <div className="grid lg:grid-cols-[380px_1fr] gap-3">
            <Panel className="p-2 flex flex-col h-[640px]">
              <ul className="overflow-y-auto flex-1">
                {rows?.rows.map((r) => (
                  <li key={r.id} tabIndex={0} onClick={() => setSel(r.id)} onKeyDown={(e) => { if (e.key === 'Enter') setSel(r.id); }}
                      className={`px-2 py-2 border-t border-[#E2E8F2] cursor-pointer ${sel === r.id ? 'bg-sky-50' : 'hover:bg-[#F4F6FA]'}`}>
                    <div className="flex items-center gap-2"><VerdictBadge v={r.verdict} /><SeverityPill s={r.severity} /><span className="text-xs font-mono">{r.time?.slice(0, 16).replace('T', ' ')}</span><span className="ml-auto text-[10px] font-mono">{r.rule_score.toFixed(2)}</span></div>
                    <div className="text-[11px] text-slate-700 mt-0.5">{r.station_id} · <span className="font-mono">{r.checks.join(', ') || 'no check fired'}</span></div>
                  </li>))}
                {rows && rows.rows.length === 0 && <li className="p-3 text-xs text-slate-500">Nothing flagged in this run.</li>}
              </ul>
              <div className="flex items-center justify-between p-1 border-t border-[#E2E8F2]">
                <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Previous</button>
                <span className="text-[10px] font-mono">{page}</span>
                <button disabled={!rows || page >= rows.pages} onClick={() => setPage((p) => p + 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Next</button>
              </div>
            </Panel>
            {runId !== null && <EvidencePane runId={runId} rowId={sel} narrator={narrator} onSelectRow={setSel} />}
          </div>
        </>)}

      <details className="rain-panel p-3" open>
        <summary className="cursor-pointer text-sm font-bold text-slate-900">How this was flagged</summary>
        <div className="mt-3"><HowFlagged /></div>
      </details>
      <details className="rain-panel p-3">
        <summary className="cursor-pointer text-sm font-bold text-slate-900">Test the checks on synthetic faults</summary>
        <div className="mt-3"><LabView onOpenRun={onRun} /></div>
      </details>
      <NextButton label="Models" onClick={onNext} />
    </div>);
}
