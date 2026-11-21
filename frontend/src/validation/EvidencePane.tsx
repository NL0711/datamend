// Decision pane of layout D. Evidence is loaded only when a row opens (one GET). Always on screen: the original row untouched, evidence
// with measured/assumed/derived tags, generated explanations marked as generated, and the narrator slot with its real state.
import { useCallback, useEffect, useState } from 'react';
import { explain, getEvidence, getExplanations, getRow } from './api';
import { ContextTable } from './ContextTable';
import { ReviewBox } from './ReviewBox';
import { asPlainText, isGrounded } from './lib';
import type { Evidence, ExplanationItem, NarratorStatus, RowDetail } from './types';
import { BasisTag, Notice, Panel, SeverityPill, VerdictBadge, formatError } from './ui';

function EvidenceCard({ ev }: { ev: Evidence }) {
  return (
    <div className="space-y-2 text-xs rounded border border-[#D3DCE7] p-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono font-bold text-slate-900">{ev.check}</span>
        <span className="text-[10px] font-mono text-slate-500">layer: {ev.layer} · {ev.kind}</span>
        <span className="text-[10px] font-mono text-slate-500">time basis: {ev.time_basis}</span>
      </div>
      <p className="text-slate-800">{ev.reason}</p>
      <div className="grid grid-cols-2 gap-2">
        {ev.observed && (
          <div className="rounded border border-[#D3DCE7] p-2 bg-[#F4F6FA]">
            <div className="text-[10px] uppercase text-slate-500 font-mono">Observed</div>
            <div className="font-mono font-bold">{ev.observed.value} {ev.observed.unit}</div>
            <BasisTag basis={ev.observed.basis} />
          </div>)}
        {ev.threshold && (
          <div className="rounded border border-[#D3DCE7] p-2 bg-[#F4F6FA]">
            <div className="text-[10px] uppercase text-slate-500 font-mono">Threshold</div>
            <div className="font-mono">{String(ev.threshold.value)}</div>
            <div className="text-[10px] font-mono text-slate-500">{ev.threshold.why}</div>
            <BasisTag basis={ev.threshold.basis} />
          </div>)}
      </div>
      {ev.window && ev.window.length > 0 && (
        <div>
          <div className="text-[10px] uppercase text-slate-500 font-mono mb-1">Window ({ev.window.length}{ev.window_truncated ? ', cut to the last entries' : ''})</div>
          <table className="w-full font-mono text-[11px] border border-[#D3DCE7]">
            <tbody>{ev.window.map((w, i) => (
              <tr key={i} className="border-t border-[#E2E8F2]">
                <td className="px-2">{String(w.row_ref ?? w.day ?? i)}</td>
                <td className="px-2 text-right">{Object.entries(w).filter(([k]) => !['row_ref', 'day', 'basis'].includes(k)).map(([k, v]) => `${k} ${String(v)}`).join(' · ')}</td>
                <td className="px-2"><BasisTag basis={w.basis} /></td>
              </tr>))}</tbody>
          </table>
        </div>)}
      {ev.neighbours && ev.neighbours.length > 0 && (
        <div className="font-mono text-[11px]">
          <div className="text-[10px] uppercase text-slate-500 mb-1">Neighbours used ({ev.neighbours.length})</div>
          {ev.neighbours.map((n) => <div key={n.station_id}>{n.station_id} · {n.distance_km} km · {n.wet ? 'wet' : 'dry'} · {n.basis}</div>)}
        </div>)}
      {ev.history && <div className="font-mono text-[11px]">own history: {ev.history.n_wet_days} earlier wet days <BasisTag basis={ev.history.basis} /></div>}
      {ev.tail_probability && <div className="font-mono text-[11px]">upper-tail probability {ev.tail_probability.value.toExponential(2)} <BasisTag basis={ev.tail_probability.basis} /></div>}
      {ev.truncated && <Notice tone="warn">This payload was cut to stay under 64 KB; the full record is at <span className="font-mono">{ev.next}</span>.</Notice>}
    </div>
  );
}

function ExplanationCard({ e }: { e: ExplanationItem }) {
  const ai = e.generator === 'mcp-narrator' && !isGrounded(e);
  return (
    <div className={`rounded border p-2 text-xs ${ai ? 'border-violet-300 bg-violet-50' : 'border-sky-200 bg-sky-50'}`}>
      <div className="text-[10px] uppercase font-mono font-bold flex items-center gap-2 flex-wrap">
        <span className={ai ? 'text-violet-700' : 'text-sky-700'}>{ai ? 'AI-generated' : isGrounded(e) ? 'Grounded answer · no language model' : 'Explanation · baseline rules · generated'}</span>
        <span className="text-slate-500">{e.check ?? 'row'} · {e.model_id}</span>
        {e.confidence !== null && <span className="text-slate-500">narrator's own confidence {e.confidence}</span>}
      </div>
      <p className="mt-1 text-slate-800 whitespace-pre-wrap">{asPlainText(e.text)}</p>
    </div>
  );
}

export function EvidencePane({ runId, rowId, narrator, onSelectRow, onReviewed }: {
  runId: number; rowId: number | null; narrator: NarratorStatus | null; onSelectRow?: (id: number) => void; onReviewed?: () => void;
}) {
  const [row, setRow] = useState<RowDetail | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [explanations, setExplanations] = useState<ExplanationItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setRow(null); setEvidence([]); setExplanations([]); setError(null);
    if (rowId === null) return;
    let live = true;
    Promise.all([getRow(runId, rowId), getEvidence(runId, rowId), getExplanations(runId, rowId)])
      .then(([r, e, x]) => { if (live) { setRow(r); setEvidence(e.evidence); setExplanations(x.explanations); } })
      .catch((err) => live && setError(formatError(err)));
    return () => { live = false; };
  }, [runId, rowId]);

  const run = useCallback(async (generator: 'baseline' | 'narrator') => {
    if (rowId === null) return;
    setBusy(true); setError(null);
    try {
      const res = await explain(runId, rowId, generator);
      setExplanations((prev) => [...prev, ...res.explanations]);
    } catch (err) { setError(formatError(err)); } finally { setBusy(false); }
  }, [runId, rowId]);

  if (rowId === null) return <Panel className="p-4 min-h-[300px]"><p className="text-xs text-slate-500">Select a marker, a tick or a worklist item.</p></Panel>;

  return (
    <Panel className="p-4 min-h-[300px] space-y-3">
      {error && <Notice tone="error">{error}</Notice>}
      {row && (
        <>
          <div className="flex items-center gap-3 flex-wrap">
            <VerdictBadge v={row.verdict} /><SeverityPill s={row.severity} />
            <h2 className="text-lg font-bold text-slate-900">{row.station_id} · {row.time ?? 'no time'}</h2>
            <span className="text-[10px] font-mono text-slate-500">{row.score_kind}: {row.rule_score.toFixed(2)} · row {row.row_ref}</span>
          </div>
          <div>
            <div className="text-[10px] uppercase text-slate-500 font-mono">Original row (untouched)</div>
            <pre className="text-[11px] font-mono bg-[#F4F6FA] border border-[#D3DCE7] rounded p-2 overflow-x-auto">{JSON.stringify(row.original_row, null, 1)}</pre>
            {row.input_issues.length > 0 && <ul className="text-[11px] font-mono text-amber-800 mt-1">{row.input_issues.map((i) => <li key={i.code}>{i.code}: {i.message}</li>)}</ul>}
          </div>
          {evidence.length === 0
            ? <p className="text-xs text-slate-500">No check fired for this row.</p>
            : <div className="grid xl:grid-cols-2 gap-3">{evidence.map((ev) => <EvidenceCard key={ev.check} ev={ev} />)}</div>}
          <ContextTable runId={runId} rowId={row.id} onSelect={onSelectRow} />
          <ReviewBox runId={runId} rowId={row.id} verdict={row.verdict} onReviewed={onReviewed ? () => onReviewed() : undefined} />
          {explanations.map((e) => <ExplanationCard key={e.id} e={e} />)}
          <div className="flex items-center gap-2 flex-wrap">
            <button disabled={busy || evidence.length === 0} onClick={() => run('baseline')}
                    className="px-2 py-1 rounded border border-sky-300 text-sky-800 text-[11px] font-bold disabled:opacity-50">Explain (rules)</button>
            {narrator?.connected && (
              <button disabled={busy || evidence.length === 0} onClick={() => run('narrator')}
                      className="px-2 py-1 rounded border border-violet-300 text-violet-800 text-[11px] font-bold disabled:opacity-50">Explain (AI)</button>)}
          </div>
          {!narrator?.connected && <p className="text-[11px] text-slate-500">AI narrator not connected.</p>}
        </>)}
    </Panel>
  );
}
