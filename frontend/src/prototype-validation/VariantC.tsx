// PROTOTYPE (throwaway, ticket t06). Variant C: TRIAGE QUEUE. A live strip on top, a worklist of flagged readings on the left, a decision pane on the right.
import { useMemo, useState } from 'react';
import { Radio } from 'lucide-react';
import { FLAGGED, RUN, STATIONS, Verdict, headline, pct, stationName } from './sample';
import { EvidenceCard, Panel, SeverityPill, VerdictBadge } from './Shared';

export const NAME = 'Triage queue';

export function VariantC() {
  const [filter, setFilter] = useState<Verdict | 'ALL'>('ALL');
  const [station, setStation] = useState('ALL');
  const list = useMemo(() => FLAGGED.filter((r) => (filter === 'ALL' || r.verdict === filter) && (station === 'ALL' || r.station === station))
    .sort((a, b) => b.ruleScore - a.ruleScore), [filter, station]);
  const [sel, setSel] = useState<string | null>(null);
  const cur = list.find((r) => r.id === sel) ?? list[0];
  const h = headline();
  return (
    <div className="space-y-3">
      <Panel className="px-4 py-2 flex items-center gap-4 flex-wrap text-[11px] font-mono">
        <span className="flex items-center gap-1.5 font-bold text-emerald-700"><Radio className="w-3.5 h-3.5" />LIVE · Weather Union</span>
        <span>9/900 calls today</span><span>poll 15 min</span><span>time basis: received</span><span>open run: live-2026-11-19</span>
        <span className="text-slate-500">{STATIONS.length} gauges · all dry right now → OK</span>
        <span className="ml-auto text-slate-500">{RUN.id} · completeness {pct(h.completeness)} · {FLAGGED.length} flagged of {h.total}</span>
      </Panel>

      <div className="grid lg:grid-cols-[340px_1fr] gap-3">
        <Panel className="p-2 h-[640px] flex flex-col">
          <div className="flex gap-1 flex-wrap p-1">
            {(['ALL', 'SUSPECT', 'UNCERTAIN', 'NO_DATA'] as const).map((f) => (
              <button key={f} onClick={() => setFilter(f)} className={`px-2 py-0.5 rounded text-[10px] font-bold border ${filter === f ? 'bg-slate-900 text-white border-slate-900' : 'border-[#D3DCE7] text-slate-600'}`}>{f}</button>))}
            <select value={station} onChange={(e) => setStation(e.target.value)} className="ml-auto text-[10px] border border-[#D3DCE7] rounded px-1">
              <option value="ALL">all stations</option>{STATIONS.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          </div>
          <div className="text-[10px] font-mono text-slate-500 px-2 pb-1">{list.length} items · highest rule score first</div>
          <ul className="overflow-y-auto flex-1">{list.map((r) => (
            <li key={r.id} onClick={() => setSel(r.id)} className={`px-2 py-2 border-t border-[#E2E8F2] cursor-pointer ${cur?.id === r.id ? 'bg-sky-50' : 'hover:bg-[#F4F6FA]'}`}>
              <div className="flex items-center gap-2"><VerdictBadge v={r.verdict} /><span className="text-xs font-mono">{r.time}</span><span className="ml-auto text-[10px] font-mono">{r.ruleScore.toFixed(2)}</span></div>
              <div className="text-[11px] text-slate-700 mt-0.5">{stationName(r.station)} · <span className="font-mono">{r.hits.map((x) => x.check).join(', ')}</span></div>
            </li>))}</ul>
        </Panel>

        <Panel className="p-4 min-h-[640px]">
          {!cur ? <p className="text-xs text-slate-500">Nothing in this filter.</p> : (
            <>
              <div className="flex items-center gap-3 flex-wrap">
                <VerdictBadge v={cur.verdict} />
                <h2 className="text-lg font-bold text-slate-900">{stationName(cur.station)} · {cur.time}</h2>
                {cur.hits.map((x) => <SeverityPill key={x.check} s={x.severity} />)}
              </div>
              <p className="text-[11px] font-mono text-slate-500 mt-1">
                raw: intensity {cur.intensity ?? 'null'} · accumulation {cur.accumulation ?? 'null'} (original row, untouched) · reading #{cur.i} · cell {STATIONS.find((s) => s.id === cur.station)?.cell}
              </p>
              <div className="mt-4 grid md:grid-cols-2 gap-4">{cur.hits.map((hit) => <EvidenceCard key={hit.check} row={cur} hit={hit} />)}</div>
              <div className="mt-4 flex gap-2">
                <button disabled className="px-3 py-1.5 text-[11px] border border-slate-300 rounded text-slate-400 cursor-not-allowed">Mark reviewed (reviewer loop, outside this map)</button>
              </div>
            </>)}
        </Panel>
      </div>
    </div>
  );
}
