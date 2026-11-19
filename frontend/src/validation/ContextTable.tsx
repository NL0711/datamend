// Event forensics: the same station's readings just before and after the selected one, with the verdict and the checks on each.
import { useEffect, useState } from 'react';
import { getContext } from './api';
import type { RowContext } from './types';
import { VerdictBadge, formatError } from './ui';

export function ContextTable({ runId, rowId, onSelect }: { runId: number; rowId: number; onSelect?: (id: number) => void }) {
  const [ctx, setCtx] = useState<RowContext | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setCtx(null); setError(null);
    getContext(runId, rowId).then(setCtx).catch((e) => setError(formatError(e)));
  }, [runId, rowId]);

  if (error) return <p className="text-xs text-red-700">{error}</p>;
  if (!ctx) return <p className="text-xs text-slate-500">Loading the surrounding readings…</p>;
  if (ctx.rows.length <= 1) return <p className="text-xs text-slate-500">No other readings with a time for this station.</p>;
  return (
    <div>
      <div className="text-[10px] uppercase text-slate-500 font-mono mb-1">Around this reading · {ctx.station_id} · original values</div>
      <table className="w-full font-mono text-[11px] border border-[#D3DCE7]">
        <thead className="bg-[#EDF1F7] text-left"><tr><th className="px-2">time</th><th className="px-2 text-right">intensity</th><th className="px-2 text-right">counter</th><th className="px-2 text-right">mm</th><th className="px-2">verdict</th><th className="px-2">checks</th></tr></thead>
        <tbody>{ctx.rows.map((r) => (
          <tr key={r.id} onClick={() => onSelect?.(r.id)} className={`border-t border-[#E2E8F2] ${onSelect ? 'cursor-pointer hover:bg-[#F4F6FA]' : ''} ${r.id === ctx.selected_id ? 'bg-amber-50 font-bold' : ''}`}>
            <td className="px-2">{r.time?.slice(0, 16).replace('T', ' ')}</td>
            <td className="px-2 text-right">{r.intensity ?? '—'}</td><td className="px-2 text-right">{r.accumulation ?? '—'}</td><td className="px-2 text-right">{r.mm ?? '—'}</td>
            <td className="px-2"><VerdictBadge v={r.verdict} /></td><td className="px-2 text-slate-600">{r.checks.join(', ')}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}
