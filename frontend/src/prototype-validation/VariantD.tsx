// PROTOTYPE (throwaway, ticket t06). Variant D: the owner's pick. B's TIMELINE across the full width on top, C's DATA (live strip, worklist, decision pane) below.
import { useMemo, useState } from 'react';
import { Radio } from 'lucide-react';
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { FLAGGED, ROWS, RUN, Row, STATIONS, Verdict, headline, pct, stationName } from './sample';
import { EvidenceCard, Panel, SeverityPill, VERDICT_COLOR, VerdictBadge } from './Shared';

export const NAME = 'Timeline over queue';
const CHECKS = ['MISSING_READING', 'NEGATIVE_VALUE', 'ACCUMULATION_JUMP', 'FROZEN_INTENSITY', 'ISOLATED_WET', 'UNVERIFIED_EXTREME'];

export function VariantD() {
  const [station, setStation] = useState('A');
  const [filter, setFilter] = useState<Verdict | 'ALL'>('ALL');
  const [everyStation, setEveryStation] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const h = headline();

  const rows = useMemo(() => ROWS.filter((r) => r.station === station), [station]);
  const flaggedHere = rows.filter((r) => r.verdict !== 'OK');
  const list = useMemo(
    () => FLAGGED.filter((r) => (everyStation || r.station === station) && (filter === 'ALL' || r.verdict === filter)).sort((a, b) => b.ruleScore - a.ruleScore),
    [station, filter, everyStation]);
  const cur = ROWS.find((r) => r.id === sel) ?? list[0];
  const pick = (r: Row) => { setStation(r.station); setSel(r.id); };
  const data = rows.map((r) => ({ i: r.i, time: r.time, intensity: r.intensity, accumulation: r.accumulation }));
  const W = 1200, laneH = 20, labelW = 150;

  return (
    <div className="space-y-3">
      <Panel className="px-4 py-2 flex items-center gap-4 flex-wrap text-[11px] font-mono">
        <span className="flex items-center gap-1.5 font-bold text-emerald-700"><Radio className="w-3.5 h-3.5" />LIVE · Weather Union</span>
        <span>9/900 calls today</span><span>poll 15 min</span><span>time basis: received</span><span>open run: live-2026-11-19</span>
        <span className="text-slate-500">all gauges dry right now → OK</span>
        <span className="ml-auto text-slate-500">{RUN.id} · completeness {pct(h.completeness)} · SUSPECT {pct(h.suspect)} · UNCERTAIN {pct(h.uncertain)} · {FLAGGED.length} flagged of {h.total}</span>
      </Panel>

      {/* B: timeline, full width */}
      <Panel className="p-3">
        <div className="flex items-center gap-2 flex-wrap mb-2">
          {STATIONS.map((s) => (
            <button key={s.id} onClick={() => { setStation(s.id); setSel(null); }}
              className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${station === s.id ? 'bg-sky-600 text-white border-sky-600' : 'border-[#D3DCE7] text-slate-600'}`}>{s.name}</button>))}
          <span className="ml-auto text-[10px] uppercase font-mono text-slate-500">intensity (bars, assumed mm/h) · accumulation counter (line, units unconfirmed)</span>
        </div>
        <div style={{ height: 300 }}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}
              onClick={(e: any) => e?.activePayload && setSel(`${station}-${e.activePayload[0].payload.i}`)}>
              <CartesianGrid stroke="#E2E8F2" strokeDasharray="3 3" />
              <XAxis dataKey="time" tick={{ fontSize: 10 }} interval={5} />
              <YAxis yAxisId="l" tick={{ fontSize: 10 }} /><YAxis yAxisId="r" orientation="right" tick={{ fontSize: 10 }} />
              <Tooltip />
              <Bar yAxisId="l" dataKey="intensity" fill="#7DD3FC" isAnimationActive={false} />
              <Line yAxisId="r" dataKey="accumulation" stroke="#0369A1" dot={false} strokeWidth={1.5} isAnimationActive={false} />
              {flaggedHere.map((r) => r.intensity !== null && (
                <ReferenceDot key={r.id} yAxisId="l" x={r.time} y={Math.min(r.intensity, 8)} r={5} fill={VERDICT_COLOR[r.verdict]} stroke="#fff" />))}
              {cur && cur.station === station && cur.intensity !== null && (
                <ReferenceDot yAxisId="l" x={cur.time} y={Math.min(cur.intensity, 8)} r={10} fill="none" stroke="#0F172A" strokeWidth={2} />)}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <svg viewBox={`0 0 ${W} ${CHECKS.length * laneH + 4}`} className="w-full mt-1">
          {CHECKS.map((c, li) => (
            <g key={c} transform={`translate(0 ${li * laneH})`}>
              <rect x={labelW} y={2} width={W - labelW} height={laneH - 4} fill={li % 2 ? '#F4F6FA' : '#EDF1F7'} rx={3} />
              <text x={4} y={laneH / 2 + 3} fontSize={10} fontFamily="monospace" fill="#475569">{c}</text>
              {rows.filter((r) => r.hits.some((x) => x.check === c)).map((r) => (
                <rect key={r.id} x={labelW + (r.i / 96) * (W - labelW)} y={4} width={8} height={laneH - 8} fill={VERDICT_COLOR[r.verdict]} className="cursor-pointer" onClick={() => setSel(r.id)} />))}
            </g>))}
        </svg>
        <p className="text-[10px] text-slate-500 mt-1">Each tick is a fired check; click a marker or tick to open it below. Not run: {RUN.notRun.map((n) => n.check).join(' · ')}</p>
      </Panel>

      {/* C: the data, below */}
      <div className="grid lg:grid-cols-[360px_1fr] gap-3">
        <Panel className="p-2 h-[560px] flex flex-col">
          <div className="flex gap-1 flex-wrap p-1 items-center">
            {(['ALL', 'SUSPECT', 'UNCERTAIN', 'NO_DATA'] as const).map((f) => (
              <button key={f} onClick={() => setFilter(f)} className={`px-2 py-0.5 rounded text-[10px] font-bold border ${filter === f ? 'bg-slate-900 text-white border-slate-900' : 'border-[#D3DCE7] text-slate-600'}`}>{f}</button>))}
            <label className="ml-auto text-[10px] text-slate-600 flex items-center gap-1"><input type="checkbox" checked={everyStation} onChange={(e) => setEveryStation(e.target.checked)} />all stations</label>
          </div>
          <div className="text-[10px] font-mono text-slate-500 px-2 pb-1">{list.length} flagged · highest rule score first · {everyStation ? 'all stations' : stationName(station)}</div>
          <ul className="overflow-y-auto flex-1">{list.map((r) => (
            <li key={r.id} onClick={() => pick(r)} className={`px-2 py-2 border-t border-[#E2E8F2] cursor-pointer ${cur?.id === r.id ? 'bg-sky-50' : 'hover:bg-[#F4F6FA]'}`}>
              <div className="flex items-center gap-2"><VerdictBadge v={r.verdict} /><span className="text-xs font-mono">{r.time}</span><span className="ml-auto text-[10px] font-mono">{r.ruleScore.toFixed(2)}</span></div>
              <div className="text-[11px] text-slate-700 mt-0.5">{stationName(r.station)} · <span className="font-mono">{r.hits.map((x) => x.check).join(', ')}</span></div>
            </li>))}
            {list.length === 0 && <li className="p-3 text-xs text-slate-500">Nothing flagged for this filter.</li>}
          </ul>
        </Panel>

        <Panel className="p-4 min-h-[560px]">
          {!cur ? <p className="text-xs text-slate-500">Select a marker, a tick or a queue item.</p> : (
            <>
              <div className="flex items-center gap-3 flex-wrap">
                <VerdictBadge v={cur.verdict} />
                <h2 className="text-lg font-bold text-slate-900">{stationName(cur.station)} · {cur.time}</h2>
                {cur.hits.map((x) => <SeverityPill key={x.check} s={x.severity} />)}
              </div>
              <p className="text-[11px] font-mono text-slate-500 mt-1">
                raw: intensity {cur.intensity ?? 'null'} · accumulation {cur.accumulation ?? 'null'} (original row, untouched) · reading #{cur.i} · cell {STATIONS.find((s) => s.id === cur.station)?.cell} · {STATIONS.find((s) => s.id === cur.station)?.region}
              </p>
              {cur.hits.length === 0
                ? <p className="mt-4 text-xs text-slate-500">No check fired for this reading.</p>
                : <div className="mt-4 grid md:grid-cols-2 gap-4">{cur.hits.map((hit) => <EvidenceCard key={hit.check} row={cur} hit={hit} />)}</div>}
            </>)}
        </Panel>
      </div>
    </div>
  );
}
