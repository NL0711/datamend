// The full-width timeline of layout D: one station's series on top, one lane per fired check underneath. A chart marker and a lane tick
// select the same row as a worklist item does.
import { useMemo } from 'react';
import { Area, CartesianGrid, ComposedChart, Line, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { VERDICT_COLOR, buildLanes, chartData, markerY, timeMs } from './lib';
import type { Series } from './types';

const LANE_W = 1200, LANE_H = 20, LABEL_W = 170;

export function Timeline({ series, selectedId, onSelect, profile }: { series: Series; selectedId: number | null; onSelect: (id: number) => void; profile: 'reading' | 'daily' }) {
  const data = useMemo(() => chartData(series.points), [series]);
  const t0 = series.points[0]?.time, t1 = series.points[series.points.length - 1]?.time;
  const lanes = useMemo(() => (t0 && t1 ? buildLanes(series.flagged, t0, t1) : []), [series, t0, t1]);
  const selected = series.flagged.find((f) => f.id === selectedId);
  const daily = profile === 'daily';

  if (series.points.length === 0) return <p className="text-xs text-slate-500 p-3">No rows with a usable time for this station.</p>;

  return (
    <div>
      <div className="text-[10px] uppercase font-mono text-slate-500 mb-1">
        {daily ? 'daily total (mm)' : 'intensity (area) · accumulation counter (line)'}
        {' · '}{series.n_total} rows{series.downsampled ? ` · reduced to ${series.points.length} points (every flagged row is still marked)` : ''}
      </div>
      <div style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
            <CartesianGrid stroke="#E2E8F2" strokeDasharray="3 3" />
            <XAxis dataKey="t" type="number" scale="time" domain={[timeMs(t0), timeMs(t1)]} tick={{ fontSize: 10 }}
                   tickFormatter={(v: number) => new Date(v).toISOString().slice(daily ? 0 : 5, daily ? 10 : 16).replace('T', ' ')} />
            <YAxis yAxisId="l" tick={{ fontSize: 10 }} />
            {!daily && <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 10 }} />}
            <Tooltip labelFormatter={(v: number) => new Date(v).toISOString()} />
            <Area yAxisId="l" type="stepAfter" dataKey={daily ? 'mm' : 'intensity'} stroke="#38BDF8" fill="#BAE6FD" isAnimationActive={false} connectNulls />
            {!daily && <Line yAxisId="r" dataKey="accumulation" stroke="#0369A1" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls />}
            {series.flagged.map((f) => (
              <ReferenceDot key={f.id} yAxisId="l" x={timeMs(f.time)} y={markerY(f)} r={5} fill={VERDICT_COLOR[f.verdict]} stroke="#fff"
                            onClick={() => onSelect(f.id)} style={{ cursor: 'pointer' }} />))}
            {selected && <ReferenceDot yAxisId="l" x={timeMs(selected.time)} y={markerY(selected)} r={10} fill="none" stroke="#0F172A" strokeWidth={2} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {lanes.length > 0 ? (
        <svg viewBox={`0 0 ${LANE_W} ${lanes.length * LANE_H + 4}`} className="w-full mt-1" role="img" aria-label="check lanes">
          {lanes.map((lane, li) => (
            <g key={lane.check} transform={`translate(0 ${li * LANE_H})`}>
              <rect x={LABEL_W} y={2} width={LANE_W - LABEL_W} height={LANE_H - 4} fill={li % 2 ? '#F4F6FA' : '#EDF1F7'} rx={3} />
              <text x={4} y={LANE_H / 2 + 3} fontSize={10} fontFamily="monospace" fill="#475569">{lane.check}</text>
              {lane.marks.map((m) => (
                <rect key={`${m.id}-${m.check}`} x={LABEL_W + m.x * (LANE_W - LABEL_W - 8)} y={4} width={8} height={LANE_H - 8}
                      fill={VERDICT_COLOR[m.verdict]} stroke={m.id === selectedId ? '#0F172A' : 'none'} className="cursor-pointer" onClick={() => onSelect(m.id)} />))}
            </g>))}
        </svg>
      ) : <p className="text-[11px] text-slate-500 mt-1">No check fired for this station.</p>}
    </div>
  );
}
