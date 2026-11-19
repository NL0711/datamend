// PROTOTYPE (throwaway, ticket t06): small shared pieces (badges, evidence card). Layouts are NOT shared between variants.
import { Hit, Row, Verdict, Severity } from './sample';

export const VERDICT_STYLE: Record<Verdict, string> = {
  OK: 'bg-emerald-50 text-emerald-700 border-emerald-300',
  SUSPECT: 'bg-red-50 text-red-700 border-red-300',
  UNCERTAIN: 'bg-amber-50 text-amber-700 border-amber-300',
  NO_DATA: 'bg-slate-100 text-slate-600 border-slate-300',
};
export const SEVERITY_STYLE: Record<Severity, string> = {
  high: 'bg-red-600 text-white', medium: 'bg-amber-500 text-white', low: 'bg-slate-400 text-white',
};
export const VERDICT_COLOR: Record<Verdict, string> = { OK: '#10B981', SUSPECT: '#EF4444', UNCERTAIN: '#F59E0B', NO_DATA: '#94A3B8' };

export const VerdictBadge = ({ v }: { v: Verdict }) => (
  <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-bold ${VERDICT_STYLE[v]}`}>{v}</span>
);
export const SeverityPill = ({ s }: { s: Severity }) => (
  <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${SEVERITY_STYLE[s]}`}>{s}</span>
);
export const Panel = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <div className={`bg-white border border-[#D3DCE7] rounded-lg ${className}`}>{children}</div>
);

const BASIS_STYLE = { measured: 'text-emerald-700', assumed: 'text-amber-700', derived: 'text-sky-700' } as const;

/** Evidence of one fired check, with the baseline explanation and the narrator slot (NOT IMPLEMENTED). */
export function EvidenceCard({ row, hit }: { row: Row; hit: Hit }) {
  const e = hit.evidence;
  return (
    <div className="space-y-3 text-xs">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-mono font-bold text-slate-900">{hit.check}</span>
        <SeverityPill s={hit.severity} />
        <span className="text-[10px] font-mono text-slate-500">layer: {hit.layer}</span>
        <span className="text-[10px] font-mono text-slate-500">rule score {row.ruleScore.toFixed(2)} (uncalibrated)</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded border border-[#D3DCE7] p-2 bg-[#F4F6FA]">
          <div className="text-[10px] uppercase text-slate-500 font-mono">Observed</div>
          <div className="font-mono font-bold">{e.observed.value ?? 'no value'} {e.observed.unit}</div>
          <div className={`text-[10px] font-mono ${BASIS_STYLE[e.observed.basis]}`}>basis: {e.observed.basis}</div>
        </div>
        <div className="rounded border border-[#D3DCE7] p-2 bg-[#F4F6FA]">
          <div className="text-[10px] uppercase text-slate-500 font-mono">Threshold</div>
          <div className="font-mono">{e.threshold.value}</div>
          <div className="text-[10px] font-mono text-slate-500">{e.threshold.why}</div>
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase text-slate-500 font-mono mb-1">Window (last {e.window.length} readings, time basis: {e.timeBasis})</div>
        <table className="w-full font-mono text-[11px] border border-[#D3DCE7]">
          <thead className="bg-[#EDF1F7]"><tr><th className="text-left px-2">#</th><th className="text-right px-2">intensity</th><th className="text-right px-2">accum.</th></tr></thead>
          <tbody>{e.window.map((w) => (
            <tr key={w.i} className={w.i === row.i ? 'bg-amber-50 font-bold' : ''}>
              <td className="px-2">{w.i}</td><td className="px-2 text-right">{w.intensity ?? 'null'}</td><td className="px-2 text-right">{w.accumulation ?? 'null'}</td>
            </tr>))}</tbody>
        </table>
      </div>
      {e.neighbours && (
        <div className="font-mono text-[11px]">
          <div className="text-[10px] uppercase text-slate-500 mb-1">Neighbours used ({e.neighbours.length})</div>
          {e.neighbours.length === 0 ? <div className="text-slate-500">none within 10 km</div> :
            e.neighbours.map((n) => <div key={n.station}>{n.station} · {n.distKm} km · {n.state}</div>)}
        </div>
      )}
      <div className="rounded border border-sky-200 bg-sky-50 p-2">
        <div className="text-[10px] uppercase font-mono text-sky-700 font-bold">Explanation · baseline rules · generated</div>
        <p className="mt-1 text-slate-800">{e.reason}</p>
      </div>
      <div className="rounded border border-dashed border-slate-300 p-2 text-slate-500">
        <div className="text-[10px] uppercase font-mono font-bold">AI narrator · NOT IMPLEMENTED</div>
        <p className="mt-1">Not connected. The teammate's narrator would appear here with an AI-generated badge, beside the evidence above.</p>
        <button disabled className="mt-1 px-2 py-1 rounded border border-slate-300 text-[11px] opacity-60 cursor-not-allowed">Explain</button>
      </div>
    </div>
  );
}
