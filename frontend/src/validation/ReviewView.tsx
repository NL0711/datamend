// The admin review queue (the old Alert Center triage): flagged rows across every run, highest rule score first, with review state.
// Select a row to see its evidence and the surrounding readings and to record a decision. Reviews never change a verdict or score.
import { useCallback, useEffect, useState } from 'react';
import { getNarrator, getQueue, getReviewSummary } from './api';
import { ALL_CHECKS, DECISION_LABEL, PAGE_SIZE, queueQuery } from './lib';
import { EvidencePane } from './EvidencePane';
import { ProposalsPanel } from './ProposalsPanel';
import type { NarratorStatus, QueuePage, ReviewSummary } from './types';
import { NextButton, Notice, Panel, SeverityPill, SyntheticBadge, VerdictBadge, formatError } from './ui';

export function ReviewView({ station: initialStation = '', onClearStation, runId = null, onNext }: { station?: string; onClearStation?: () => void; runId?: number | null; onNext?: () => void }) {
  const [station, setStation] = useState(initialStation);
  const [status, setStatus] = useState<'unreviewed' | 'reviewed' | 'all'>('unreviewed');
  const [verdict, setVerdict] = useState<'' | 'SUSPECT' | 'UNCERTAIN'>('');
  const [check, setCheck] = useState('');
  const [source, setSource] = useState<'all' | 'synthetic' | 'real'>('all');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<QueuePage | null>(null);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [narrator, setNarrator] = useState<NarratorStatus | null>(null);
  const [sel, setSel] = useState<{ run: number; id: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getQueue(queueQuery({ page, status, verdict, check, synthetic: source, station })).then(setData).catch((e) => setError(formatError(e)));
    getReviewSummary().then(setSummary).catch(() => undefined);
  }, [page, status, verdict, check, source, station]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [status, verdict, check, source, station]);
  useEffect(() => { getNarrator().then(setNarrator).catch(() => setNarrator(null)); }, []);

  const checks = ALL_CHECKS;
  return (
    <div className="space-y-3">
      {error && <Notice tone="error">{error}</Notice>}
      {station && (
        <Notice tone="info">
          Showing only station <b className="font-mono">{station}</b>.{' '}
          <button className="font-bold text-sky-700" onClick={() => { setStation(''); onClearStation?.(); }}>Show every station</button>
        </Notice>)}
      {summary && (
        <Panel className="p-3 space-y-2">
          <div className="flex items-center gap-4 flex-wrap text-[11px] font-mono">
            <span className="font-bold text-sm font-sans text-slate-900">Review loop</span>
            <span>{summary.unreviewed_rows} unreviewed of {summary.flagged_rows} flagged</span>
            {(Object.keys(summary.by_decision) as (keyof typeof summary.by_decision)[]).map((d) => <span key={d}>{DECISION_LABEL[d]} {summary.by_decision[d]}</span>)}
          </div>
          <p className="text-[10px] text-slate-500">{summary.caveat}</p>
        </Panel>)}

      <div className="grid lg:grid-cols-[400px_1fr] gap-3">
        <Panel className="p-2 flex flex-col h-[760px]">
          <div className="flex gap-1 flex-wrap p-1 items-center">
            {(['unreviewed', 'reviewed', 'all'] as const).map((s) => (
              <button key={s} onClick={() => setStatus(s)} className={`px-2 py-0.5 rounded text-[10px] font-bold border ${status === s ? 'bg-slate-900 text-white border-slate-900' : 'border-[#D3DCE7] text-slate-600'}`}>{s}</button>))}
          </div>
          <div className="flex gap-1 px-1 pb-1">
            <select value={verdict} onChange={(e) => setVerdict(e.target.value as '' | 'SUSPECT' | 'UNCERTAIN')} className="text-[11px] border border-[#D3DCE7] rounded px-1 py-0.5" aria-label="verdict filter">
              <option value="">any verdict</option><option value="SUSPECT">SUSPECT</option><option value="UNCERTAIN">UNCERTAIN</option></select>
            <select value={check} onChange={(e) => setCheck(e.target.value)} className="text-[11px] border border-[#D3DCE7] rounded px-1 py-0.5" aria-label="check filter">
              <option value="">any check</option>{checks.map((c) => <option key={c} value={c}>{c}</option>)}</select>
            <select value={source} onChange={(e) => setSource(e.target.value as 'all' | 'synthetic' | 'real')} className="text-[11px] border border-[#D3DCE7] rounded px-1 py-0.5" aria-label="data filter">
              <option value="all">all data</option><option value="real">uploaded or live</option><option value="synthetic">synthetic</option></select>
          </div>
          <div className="text-[10px] font-mono text-slate-500 px-2 pb-1">{data ? `${data.total} rows · page ${data.page} of ${Math.max(1, data.pages)} · ${PAGE_SIZE} per page · highest rule score first` : 'loading…'}</div>
          <ul className="overflow-y-auto flex-1">
            {data?.rows.map((r) => (
              <li key={`${r.run_id}-${r.id}`} onClick={() => setSel({ run: r.run_id, id: r.id })}
                  className={`px-2 py-2 border-t border-[#E2E8F2] cursor-pointer ${sel?.id === r.id && sel.run === r.run_id ? 'bg-sky-50' : 'hover:bg-[#F4F6FA]'}`}>
                <div className="flex items-center gap-2 flex-wrap"><VerdictBadge v={r.verdict} /><SeverityPill s={r.severity} />
                  <span className="text-xs font-mono">{r.time?.slice(0, 16).replace('T', ' ')}</span>
                  {r.synthetic && <SyntheticBadge />}<span className="ml-auto text-[10px] font-mono">{r.rule_score.toFixed(2)}</span></div>
                <div className="text-[11px] text-slate-700 mt-0.5">{r.station_id} · run #{r.run_id} · <span className="font-mono">{r.checks.join(', ')}</span></div>
                {r.review && <div className="text-[10px] font-bold text-slate-600 mt-0.5">{DECISION_LABEL[r.review.decision]}{r.review.reviewer ? ` · ${r.review.reviewer}` : ''}</div>}
              </li>))}
            {data && data.rows.length === 0 && <li className="p-3 text-xs text-slate-500">{status === 'unreviewed' ? 'Nothing left to review.' : 'Nothing here.'}</li>}
          </ul>
          <div className="flex items-center justify-between p-1 border-t border-[#E2E8F2]">
            <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Previous</button>
            <span className="text-[10px] font-mono">{page}</span>
            <button disabled={!data || page >= data.pages} onClick={() => setPage((p) => p + 1)} className="px-2 py-0.5 text-[11px] border rounded disabled:opacity-40">Next</button>
          </div>
        </Panel>
        {sel ? <EvidencePane runId={sel.run} rowId={sel.id} narrator={narrator} onSelectRow={(id) => setSel({ run: sel.run, id })} onReviewed={load} />
          : <Panel className="p-4"><p className="text-xs text-slate-500">Select a flagged row to read its evidence and record a review.</p></Panel>}
      </div>
      <details className="rain-panel p-3">
        <summary className="cursor-pointer text-sm font-bold text-slate-900">Proposals and audit sample{runId !== null ? ` for run ${runId}` : ''}</summary>
        <div className="mt-3">{runId === null ? <p className="text-xs text-slate-500">Run the checks (step 4) to get a run to work on.</p> : <ProposalsPanel key={runId} runId={runId} />}</div>
      </details>
      {onNext && <NextButton label="Anomalies" onClick={onNext} />}
    </div>
  );
}
