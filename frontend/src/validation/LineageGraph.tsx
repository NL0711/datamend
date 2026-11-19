// The lineage of the data pipeline as a graph: ingest job -> checking run -> snapshot -> training -> model (with its gate). Drawn from what the
// platform stored (nothing is guessed); click a box for its facts. Row-level lineage (flag -> evidence -> raw hours) is in the run view.
import { useMemo, useState } from 'react';
import type { Lineage, LineageNode } from './types';
import { Panel } from './ui';

const W = 188, H = 70, GX = 52, GY = 18, PAD = 12;
const TITLES: Record<string, string> = { job: 'Ingest job', run: 'Check run', snapshot: 'Snapshot', train: 'Training', model: 'Model and gate' };

function tone(n: LineageNode): string {
  const s = n.status;
  if (s === 'champion' || s === 'done' || s === 'complete' || s === 'completed') return '#059669';
  if (s === 'failed' || s === 'rejected') return '#DC2626';
  if (s === 'running' || s === 'queued' || s === 'challenger') return '#0284C7';
  return '#64748B';
}

export function LineageGraph({ data, onOpenRun }: { data: Lineage; onOpenRun: (id: number) => void }) {
  const [sel, setSel] = useState<string | null>(null);
  const layout = useMemo(() => {
    const pos = new Map<string, { x: number; y: number }>();
    data.columns.forEach((col, ci) => {
      data.nodes.filter((n) => n.kind === col).forEach((n, ri) => pos.set(n.id, { x: PAD + ci * (W + GX), y: PAD + 22 + ri * (H + GY) }));
    });
    const rows = Math.max(1, ...data.columns.map((c) => data.nodes.filter((n) => n.kind === c).length));
    return { pos, width: PAD * 2 + data.columns.length * W + (data.columns.length - 1) * GX, height: PAD * 2 + 22 + rows * H + (rows - 1) * GY };
  }, [data]);
  const node = data.nodes.find((n) => n.id === sel);
  const touching = (id: string) => sel !== null && (id === sel || data.edges.some((e) => (e.from === sel && e.to === id) || (e.to === sel && e.from === id)));

  if (data.nodes.length === 0) return <p className="text-xs text-slate-500">Nothing stored yet. Upload a file to start the graph.</p>;
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <svg width={layout.width} height={layout.height} role="img" aria-label="Lineage of jobs, runs, snapshots, training and models">
          {data.columns.map((c, ci) => <text key={c} x={PAD + ci * (W + GX)} y={PAD + 10} fontSize="10" fontFamily="monospace" fill="#64748B">{TITLES[c] ?? c}</text>)}
          {data.edges.map((e, i) => {
            const a = layout.pos.get(e.from), b = layout.pos.get(e.to);
            if (!a || !b) return null;
            const x1 = a.x + W, y1 = a.y + H / 2, x2 = b.x, y2 = b.y + H / 2, mx = (x1 + x2) / 2;
            const on = sel === null || e.from === sel || e.to === sel;
            return <path key={i} d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`} fill="none" stroke={on ? '#0E7490' : '#CBD5E1'} strokeWidth={on && sel ? 2 : 1.3} />;
          })}
          {data.nodes.map((n) => {
            const p = layout.pos.get(n.id);
            if (!p) return null;
            const dim = sel !== null && !touching(n.id);
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} onClick={() => setSel(sel === n.id ? null : n.id)} style={{ cursor: 'pointer', opacity: dim ? 0.35 : 1 }}
                 role="button" tabIndex={0} aria-label={`${TITLES[n.kind]} ${n.label}, ${n.status}`} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setSel(sel === n.id ? null : n.id); }}>
                <rect width={W} height={H} rx="8" fill="#FFFFFF" stroke={sel === n.id ? '#0F172A' : '#CBD5E1'} strokeWidth={sel === n.id ? 2 : 1} />
                <rect width="5" height={H} rx="2" fill={tone(n)} />
                <text x="14" y="24" fontSize="12" fontWeight="600" fill="#0F172A">{n.label.length > 24 ? n.label.slice(0, 23) + '…' : n.label}</text>
                <text x="14" y="42" fontSize="10.5" fontFamily="monospace" fill={tone(n)}>{n.status}</text>
                <text x="14" y="58" fontSize="10" fill="#64748B">{Object.entries(n.facts).slice(0, 2).map(([k, v]) => `${k} ${v}`).join(' · ').slice(0, 30)}</text>
              </g>);
          })}
        </svg>
      </div>
      {node && (
        <Panel className="p-3 text-xs space-y-1">
          <div className="flex items-center gap-2 flex-wrap"><b className="text-sm">{TITLES[node.kind]}: {node.label}</b><span className="font-mono" style={{ color: tone(node) }}>{node.status}</span>
            {node.kind === 'run' && node.run_id !== undefined && <button className="px-2 py-1 rounded border border-[#D3DCE7] bg-white text-[11px] font-bold" onClick={() => onOpenRun(node.run_id as number)}>Open run</button>}</div>
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-2">{Object.entries(node.facts).map(([k, v]) => (
            <div key={k} className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-2 py-1"><dt className="text-[10px] uppercase font-mono text-slate-500">{k}</dt><dd className="font-mono break-all">{String(v)}</dd></div>))}</dl>
          {node.gate_checks && node.gate_checks.length > 0 && (
            <ul className="font-mono text-[11px]">{node.gate_checks.map((c) => <li key={c.rule} className={c.passed ? 'text-emerald-700' : 'text-red-700'}>{c.passed ? 'pass' : 'FAIL'} · {c.rule}: {c.detail}</li>)}</ul>)}
        </Panel>)}
      <p className="text-[10px] text-slate-500">{data.note}</p>
    </div>);
}
