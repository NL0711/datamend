// PROTOTYPE (throwaway, ticket t06). Variant B: TIMELINE-FIRST. One big series chart, a swimlane per check, an inspector on the right.
import { useMemo, useState } from 'react';
import { Bar, CartesianGrid, ComposedChart, Line, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ROWS, RUN, STATIONS, headline, pct } from './sample';
import { EvidenceCard, Panel, VERDICT_COLOR, VerdictBadge } from './Shared';

export const NAME = 'Timeline first';
const CHECKS = ['MISSING_READING', 'NEGATIVE_VALUE', 'ACCUMULATION_JUMP', 'FROZEN_INTENSITY', 'ISOLATED_WET', 'UNVERIFIED_EXTREME'];

export function VariantB() {
  const [station, setStation] = useState('A');
  const rows = useMemo(() => ROWS.filter((r) => r.station === station), [station]);
  const [sel, setSel] = useState<string | null>(null);
  const selected = rows.find((r) => r.id === sel) ?? rows.find((r) => r.verdict !== 'OK') ?? rows[0];
  const h = headline();
  const flagged = rows.filter((r) => r.verdict !== 'OK');
  const data = rows.map((r) => ({ i: r.i, time: r.time, intensity: r.intensity, accumulation: r.accumulation }));
  const W = 960, laneH = 22;
  return (
    <div className="grid lg:grid-cols-[1fr_360px] gap-4">
      <div className="space-y-3 min-w-0">
        <Panel className="p-3 flex items-center gap-2 flex-wrap">
          {STATIONS.map((s) => (
            <button key={s.id} onClick={() => { setStation(s.id); setSel(null); }}
              className={`px-2.5 py-1 rounded-full text-[11px] font-bold border ${station === s.id ? 'bg-sky-600 text-white border-sky-600' : 'border-[#D3DCE7] text-slate-600'}`}>{s.name}</button>))}
          <span className="ml-auto text-[10px] font-mono text-slate-500">{RUN.id} · {RUN.profile} · completeness {pct(h.completeness)} · SUSPECT {pct(h.suspect)} · UNCERTAIN {pct(h.uncertain)}</span>
        </Panel>

        <Panel className="p-3">
          <div className="text-[10px] uppercase font-mono text-slate-500 mb-1">Intensity (bars, assumed mm/h) and accumulation counter (line, units unconfirmed)</div>
          <div style={{ height: 280 }}>
            <ResponsiveContainer>
              <ComposedChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }} onClick={(e: any) => e?.activePayload && setSel(`${station}-${e.activePayload[0].payload.i}`)}>
                <CartesianGrid stroke="#E2E8F2" strokeDasharray="3 3" />
                <XAxis dataKey="time" tick={{ fontSize: 10 }} interval={11} />
                <YAxis yAxisId="l" tick={{ fontSize: 10 }} /><YAxis yAxisId="r" orientation="right" tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar yAxisId="l" dataKey="intensity" fill="#7DD3FC" isAnimationActive={false} />
                <Line yAxisId="r" dataKey="accumulation" stroke="#0369A1" dot={false} strokeWidth={1.5} isAnimationActive={false} />
                {flagged.map((r) => r.intensity !== null && (
                  <ReferenceDot key={r.id} yAxisId="l" x={r.time} y={Math.min(r.intensity, 8)} r={5} fill={VERDICT_COLOR[r.verdict]} stroke="#fff" />))}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel className="p-3">
          <div className="text-[10px] uppercase font-mono text-slate-500 mb-1">Check lanes · each tick is a fired check · click to inspect</div>
          <svg viewBox={`0 0 ${W} ${CHECKS.length * laneH + 4}`} className="w-full">
            {CHECKS.map((c, li) => (
              <g key={c} transform={`translate(0 ${li * laneH})`}>
                <rect x={150} y={2} width={W - 150} height={laneH - 4} fill={li % 2 ? '#F4F6FA' : '#EDF1F7'} rx={3} />
                <text x={4} y={laneH / 2 + 3} fontSize={9} fontFamily="monospace" fill="#475569">{c}</text>
                {rows.filter((r) => r.hits.some((x) => x.check === c)).map((r) => (
                  <rect key={r.id} x={150 + (r.i / 96) * (W - 150)} y={4} width={7} height={laneH - 8} fill={VERDICT_COLOR[r.verdict]} className="cursor-pointer" onClick={() => setSel(r.id)} />))}
              </g>))}
          </svg>
          <p className="text-[10px] text-slate-500 mt-1">Not run: {RUN.notRun.map((n) => n.check).join(' · ')}</p>
        </Panel>
      </div>

      <Panel className="p-3 h-fit lg:sticky lg:top-2">
        <div className="flex items-center justify-between mb-2">
          <div className="text-xs font-bold text-slate-900">{selected.time} · reading #{selected.i}</div><VerdictBadge v={selected.verdict} />
        </div>
        {selected.hits.length === 0
          ? <p className="text-xs text-slate-500">No check fired for this reading. Click a marker or a lane tick.</p>
          : selected.hits.map((hit) => <div key={hit.check} className="mb-3"><EvidenceCard row={selected} hit={hit} /></div>)}
      </Panel>
    </div>
  );
}
