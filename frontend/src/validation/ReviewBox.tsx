// The admin review loop on one flagged row: past reviews, and a form to record a decision. A review is stored separately and never changes
// the verdict, score or evidence. Writing uses the signed-in session.
import { useEffect, useState } from 'react';
import { getReviews, postReview, storedToken } from './api';
import { DECISION_LABEL } from './lib';
import type { Decision, ReviewItem, Verdict } from './types';
import { Notice, formatError } from './ui';

const DECISIONS: Decision[] = ['confirmed_fault', 'false_alarm', 'genuine_extreme', 'needs_followup'];
const STYLE: Record<Decision, string> = {
  confirmed_fault: 'border-red-300 bg-red-50 text-red-800', false_alarm: 'border-slate-300 bg-slate-50 text-slate-700',
  genuine_extreme: 'border-sky-300 bg-sky-50 text-sky-800', needs_followup: 'border-amber-300 bg-amber-50 text-amber-800',
};
const input = 'text-xs border border-[#D3DCE7] rounded px-2 py-1 w-full';

export function ReviewBox({ runId, rowId, verdict, onReviewed }: { runId: number; rowId: number; verdict: Verdict; onReviewed?: (r: ReviewItem) => void }) {
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [note, setNote] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const flagged = verdict === 'SUSPECT' || verdict === 'UNCERTAIN';

  useEffect(() => {
    setReviews([]); setDecision(null); setNote(''); setError(null);
    getReviews(runId, rowId).then((r) => setReviews(r.reviews)).catch((e) => setError(formatError(e)));
  }, [runId, rowId]);

  const submit = async () => {
    if (!decision) return;
    setBusy(true); setError(null);
    try {
      const r = await postReview(runId, rowId, { decision, note: note.trim() || undefined, reviewer: reviewer.trim() || undefined }, storedToken());
      setReviews((prev) => [...prev, r]);
      setDecision(null); setNote('');
      onReviewed?.(r);
    } catch (e) { setError(formatError(e)); } finally { setBusy(false); }
  };

  const latest = reviews[reviews.length - 1];
  return (
    <div className="rounded border border-[#D3DCE7] p-3 space-y-2 text-xs">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[10px] uppercase font-mono font-bold text-slate-500">Review</span>
        {latest ? <span className={`px-2 py-0.5 rounded border text-[10px] font-bold ${STYLE[latest.decision]}`}>{DECISION_LABEL[latest.decision]}</span>
          : <span className="text-[10px] font-mono text-slate-500">not reviewed</span>}
      </div>
      {reviews.length > 0 && (
        <ul className="space-y-1">{reviews.map((r) => (
          <li key={r.id} className="font-mono text-[11px] text-slate-700">
            {DECISION_LABEL[r.decision]}{r.reviewer ? ` · ${r.reviewer}` : ''} · {r.created_at?.slice(0, 16).replace('T', ' ')}{r.note ? ` · “${r.note}”` : ''}</li>))}</ul>)}
      {error && <Notice tone="error">{error}</Notice>}
      {!flagged ? <p className="text-slate-500">Only flagged rows (SUSPECT or UNCERTAIN) are reviewed.</p> : (
        <>
          <div className="flex gap-1 flex-wrap">{DECISIONS.map((d) => (
            <button key={d} onClick={() => setDecision(d)} aria-pressed={decision === d}
                    className={`px-2 py-1 rounded border text-[11px] font-bold ${decision === d ? 'ring-2 ring-slate-800 ' : ''}${STYLE[d]}`}>{DECISION_LABEL[d]}</button>))}</div>
          {decision && (
            <div className="grid md:grid-cols-2 gap-2">
              <textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={1000} rows={2} placeholder="Note (optional)" className={`${input} md:col-span-2`} aria-label="review note" />
              <input value={reviewer} onChange={(e) => setReviewer(e.target.value)} maxLength={60} placeholder="Your name (optional label)" className={input} aria-label="reviewer" />
              <button disabled={busy} onClick={() => void submit()} className="px-3 py-1.5 rounded bg-slate-900 text-white font-bold disabled:opacity-40">{busy ? 'Saving…' : `Save: ${DECISION_LABEL[decision]}`}</button>
            </div>)}
        </>)}
    </div>
  );
}
