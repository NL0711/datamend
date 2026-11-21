// Insights: five live views of the stored rain days (anomaly, station similarity, climate bands, verdict mix, heavy rain against the verdict).
// Every number is measured or derived from the runs database; the server says which bands and thresholds are assumed. Nothing is forecast,
// and a view that lacks data says so instead of drawing a guess.
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Bar, CartesianGrid, Cell, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis, BarChart, AreaChart, Area } from 'recharts';
import { Download } from 'lucide-react';
import { getInsights, getStationCycle, listRuns } from './api';
import { BAND_COLOR, corrColor, insightsQuery, shareOf, toCsv } from './insights';
import type { Granularity, InsightsData, Unavailable } from './insights';
import { VERDICT_COLOR } from './lib';
import type { RunSummary, StationCycle } from './types';
import { Notice, Panel, SyntheticBadge, formatError } from './ui';

const VERDICTS = ['OK', 'SUSPECT', 'UNCERTAIN', 'NO_DATA'] as const;
const field = 'border border-[#D3DCE7] rounded px-2 py-1 text-xs bg-white';

function download(name: string, rows: readonly object[]) {
  const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: 'text/csv' }));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

function Card({ title, what, counts, csv, file, children }: { title: string; what: string; counts?: string; csv?: readonly object[]; file: string; children: ReactNode }) {
  return (
    <Panel className="p-3 space-y-2">
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-bold">{title}</h3>
          <p className="text-[11px] text-slate-600">{what}</p>
          {counts && <p className="text-[10px] font-mono text-slate-500">{counts}</p>}
        </div>
        {csv && csv.length > 0 && (
          <button onClick={() => download(file, csv)} className="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded border border-[#D3DCE7] text-[11px] font-bold text-slate-700 hover:bg-[#F4F6FA]">
            <Download className="w-3.5 h-3.5" />CSV</button>)}
      </div>
      {children}
    </Panel>
  );
}

const Empty = ({ v }: { v: Unavailable }) => <Notice tone="info">Not enough data: {v.reason}.</Notice>;

export function InsightsView() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [scope, setScope] = useState('real');                      // real | synthetic | a run id
  const [station, setStation] = useState('');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [gran, setGran] = useState<Granularity>('month');
  const [data, setData] = useState<InsightsData | null>(null);
  const [places, setPlaces] = useState<StationCycle[]>([]);
  const [anomalyStation, setAnomalyStation] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listRuns().then((r) => setRuns(r.runs.filter((x) => x.status !== 'failed' && x.profile === 'daily'))).catch(() => undefined);
    getStationCycle().then((r) => setPlaces(r.stations)).catch(() => undefined);
  }, []);

  useEffect(() => {
    let alive = true;
    setBusy(true);
    const runId = /^\d+$/.test(scope) ? Number(scope) : null;
    getInsights(insightsQuery({ runId, includeSynthetic: scope === 'synthetic', station, start, end, granularity: gran }))
      .then((d) => { if (alive) { setData(d); setError(null); } })
      .catch((e) => { if (alive) setError(formatError(e)); })
      .finally(() => { if (alive) setBusy(false); });
    return () => { alive = false; };
  }, [scope, station, start, end, gran]);

  const sel = data?.selection;
  const anomalySeries = data && data.anomaly.enough ? data.anomaly.series : [];
  useEffect(() => { if (anomalySeries.length && !anomalySeries.some((s) => s.station === anomalyStation)) setAnomalyStation(anomalySeries[0].station); }, [anomalySeries, anomalyStation]);
  const chosen = anomalySeries.find((s) => s.station === anomalyStation);
  const stationNames = useMemo(() => places.map((p) => p.station_id).sort(), [places]);
  const pos = useMemo(() => new Map(places.filter((p) => p.latitude !== null && p.longitude !== null).map((p) => [p.station_id, p])), [places]);

  return (
    <div className="space-y-3">
      <Panel className="p-3 space-y-2">
        <div className="flex items-end gap-3 flex-wrap text-xs">
          <label className="space-y-0.5"><span className="block text-[10px] font-mono uppercase text-slate-500">Data</span>
            <select className={field} value={scope} onChange={(e) => setScope(e.target.value)} aria-label="data scope">
              <option value="real">Every real run</option>
              <option value="synthetic">Every run, synthetic included</option>
              {runs.map((r) => <option key={r.id} value={String(r.id)}>Run #{r.id} · {r.label ?? r.source}{r.synthetic ? ' (synthetic)' : ''}</option>)}
            </select></label>
          <label className="space-y-0.5"><span className="block text-[10px] font-mono uppercase text-slate-500">Station</span>
            <select className={field} value={station} onChange={(e) => setStation(e.target.value)} aria-label="station">
              <option value="">All stations</option>{stationNames.map((s) => <option key={s} value={s}>{s}</option>)}
            </select></label>
          <label className="space-y-0.5"><span className="block text-[10px] font-mono uppercase text-slate-500">From</span>
            <input type="date" className={field} value={start} onChange={(e) => setStart(e.target.value)} aria-label="from date" /></label>
          <label className="space-y-0.5"><span className="block text-[10px] font-mono uppercase text-slate-500">To</span>
            <input type="date" className={field} value={end} onChange={(e) => setEnd(e.target.value)} aria-label="to date" /></label>
          <div className="space-y-0.5"><span className="block text-[10px] font-mono uppercase text-slate-500">Group by</span>
            <div className="inline-flex rounded border border-[#D3DCE7] overflow-hidden" role="group" aria-label="granularity">
              {(['month', 'year'] as const).map((g) => (
                <button key={g} onClick={() => setGran(g)} aria-pressed={gran === g} className={`px-3 py-1 text-xs font-bold ${gran === g ? 'bg-sky-600 text-white' : 'bg-white text-slate-600'}`}>{g}</button>))}
            </div></div>
          {(start || end || station) && <button className="text-xs text-sky-700 font-bold" onClick={() => { setStart(''); setEnd(''); setStation(''); }}>Clear filters</button>}
        </div>
        {sel && (
          <div className="flex items-center gap-3 flex-wrap text-[11px] font-mono text-slate-600">
            <span>{busy ? 'updating…' : sel.scope}</span>
            <span>{sel.rows_used.toLocaleString()} daily rows · {sel.stations} stations · {sel.first_day ?? 'no day'} to {sel.last_day ?? 'no day'}</span>
            {sel.synthetic && <SyntheticBadge />}
          </div>)}
        {sel?.synthetic && <Notice tone="warn">This selection contains SYNTHETIC data (the Anomaly lab or a declared synthetic upload). These charts show the generator, not weather.</Notice>}
        {sel && sel.rows_without_mm > 0 && <Notice tone="info">{sel.rows_without_mm.toLocaleString()} rows have no daily total in mm (reading-type rows) and are not used here.</Notice>}
        {sel?.truncated && <Notice tone="warn">More rows than the page can aggregate: the oldest runs were cut. Narrow the dates or pick one run.</Notice>}
      </Panel>

      {error && <Notice tone="error">{error}</Notice>}
      {!data && !error && <p className="text-xs text-slate-500">Loading…</p>}

      {data && (<>
        <Card title="Rainfall anomaly" file="insights_anomaly.csv"
              what={`Each ${gran}'s rain against the station's own normal for the same ${gran === 'month' ? 'calendar month' : 'year'}, complete periods only. Red days on the line are days the checks flagged.`}
              counts={data.anomaly.enough ? `${data.anomaly.series.length} stations with at least ${data.anomaly.min_history} complete ${gran}s` : undefined}
              csv={anomalySeries.flatMap((s) => s.points.map((p) => ({ station: s.station, ...p })))}>
          {!data.anomaly.enough ? <Empty v={data.anomaly} /> : (<>
            <select className={field} value={anomalyStation} onChange={(e) => setAnomalyStation(e.target.value)} aria-label="anomaly station">
              {anomalySeries.map((s) => <option key={s.station} value={s.station}>{s.station}</option>)}</select>
            <div className="h-64">
              <ResponsiveContainer>
                <ComposedChart data={chosen?.points ?? []} margin={{ left: 0, right: 8, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F2" />
                  <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                  <YAxis yAxisId="mm" tick={{ fontSize: 10 }} label={{ value: 'mm vs normal', angle: -90, position: 'insideLeft', fontSize: 10 }} />
                  <YAxis yAxisId="n" orientation="right" allowDecimals={false} tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v: number, n: string) => [v, n]} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar yAxisId="mm" dataKey="anomaly_mm" name="anomaly (mm)">
                    {(chosen?.points ?? []).map((p) => <Cell key={p.period} fill={p.anomaly_mm >= 0 ? '#1D4ED8' : '#D97706'} />)}
                  </Bar>
                  <Line yAxisId="n" type="monotone" dataKey="flagged_days" name="flagged days" stroke="#EF4444" dot={{ r: 2 }} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <p className="text-[10px] text-slate-500">Normal = the station's own mean for that {gran === 'month' ? 'calendar month' : 'year'} over complete periods (derived). Blue is wetter, orange drier.</p>
            {Object.keys(data.anomaly.skipped).length > 0 && <p className="text-[10px] text-slate-500">Not drawn: {Object.entries(data.anomaly.skipped).map(([s, w]) => `${s} (${w})`).join('; ')}.</p>}
          </>)}
        </Card>

        <Card title="Station similarity" file="insights_correlation.csv"
              what="How closely two stations' daily rain move together over the days both reported. This is the picture behind the neighbour check."
              counts={data.correlation.enough ? `${data.correlation.stations.length} stations${data.correlation.truncated ? ` of ${data.correlation.total_stations} (most days first)` : ''}` : undefined}
              csv={data.correlation.enough ? data.correlation.stations.flatMap((a, i) => data.correlation.enough ? data.correlation.stations.map((b, j) => ({ a, b, r: data.correlation.enough ? data.correlation.matrix[i][j] : null, shared_days: data.correlation.enough ? data.correlation.common_days[i][j] : null })) : []) : undefined}>
          {!data.correlation.enough ? <Empty v={data.correlation} /> : (() => {
            const c = data.correlation;
            return (<>
              <div className="overflow-auto">
                <table className="text-[10px] font-mono border-separate border-spacing-0.5" aria-label="correlation matrix">
                  <thead><tr><th />{c.stations.map((s) => <th key={s} className="px-1 font-normal text-slate-500 max-w-16 truncate" title={s}>{s.slice(-6)}</th>)}</tr></thead>
                  <tbody>{c.stations.map((a, i) => (
                    <tr key={a}><th className="pr-1 font-normal text-right text-slate-500" title={a}>{a.slice(-6)}</th>
                      {c.matrix[i].map((r, j) => (
                        <td key={c.stations[j]} title={`${a} vs ${c.stations[j]}: ${r === null ? 'not enough shared days' : `r = ${r}`} (${c.common_days[i][j]} shared days)`}
                            className="w-7 h-7 text-center rounded-sm" style={{ background: corrColor(r), color: r !== null && Math.abs(r) > 0.6 ? '#fff' : '#334155' }}>
                          {r === null ? '' : r.toFixed(1)}</td>))}
                    </tr>))}</tbody>
                </table>
              </div>
              <p className="text-[10px] text-slate-500">Grey: fewer than {c.min_common_days} shared days.</p>
            </>);
          })()}
        </Card>

        <Card title="Station climate groups" file="insights_climate.csv"
              what="Each station's rain per year against its share of wet days. The groups are fixed bands we chose, not learned from the data."
              counts={data.climate.enough ? `${data.climate.stations.length} stations${data.climate.too_short.length ? `, ${data.climate.too_short.length} with too few days` : ''}` : undefined}
              csv={data.climate.enough ? data.climate.stations : undefined}>
          {!data.climate.enough ? <Empty v={data.climate} /> : (() => {
            const c = data.climate;
            const located = c.stations.filter((s) => pos.has(s.station)).map((s) => ({ ...s, lat: pos.get(s.station)!.latitude as number, lon: pos.get(s.station)!.longitude as number }));
            return (<>
              <div className="grid md:grid-cols-2 gap-3">
                <div className="h-64">
                  <ResponsiveContainer>
                    <ScatterChart margin={{ left: 0, right: 8, top: 8, bottom: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F2" />
                      <XAxis type="number" dataKey="wet_day_share" name="wet-day share" domain={[0, 1]} tick={{ fontSize: 10 }} label={{ value: `share of days at or above ${c.wet_day_mm} mm`, position: 'insideBottom', offset: -8, fontSize: 10 }} />
                      <YAxis type="number" dataKey="annual_mm" name="mm per year" tick={{ fontSize: 10 }} />
                      <ZAxis range={[60, 60]} />
                      <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                      <Legend verticalAlign="top" wrapperStyle={{ fontSize: 11 }} />
                      {c.bands.map((b) => <Scatter key={b.name} name={b.name} data={c.stations.filter((s) => s.band === b.name)} fill={BAND_COLOR[b.name] ?? '#64748B'} />)}
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
                <div className="h-64">
                  {located.length === 0 ? <p className="text-[11px] text-slate-500 p-3">No station here has a known position.</p> : (
                    <ResponsiveContainer>
                      <ScatterChart margin={{ left: 0, right: 8, top: 8, bottom: 16 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F2" />
                        <XAxis type="number" dataKey="lon" name="longitude" domain={['dataMin - 1', 'dataMax + 1']} tick={{ fontSize: 10 }} />
                        <YAxis type="number" dataKey="lat" name="latitude" domain={['dataMin - 1', 'dataMax + 1']} tick={{ fontSize: 10 }} />
                        <ZAxis range={[70, 70]} />
                        <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                        {c.bands.map((b) => <Scatter key={b.name} name={b.name} data={located.filter((s) => s.band === b.name)} fill={BAND_COLOR[b.name] ?? '#64748B'} />)}
                      </ScatterChart>
                    </ResponsiveContainer>)}
                </div>
              </div>
              <p className="text-[10px] text-slate-500">Bands (assumed, mm per year): {c.bands.map((b) => `${b.name} ${b.from_mm}${b.to_mm === null ? '+' : ` to ${b.to_mm}`}`).join(', ')}. Right: longitude and latitude, no base map.</p>
            </>);
          })()}
        </Card>

        <Card title="Verdict mix over time" file="insights_verdict_mix.csv"
              what={`Share of stored rows by check verdict, per ${gran}. A rising SUSPECT share means the data looks worse, not that the weather changed.`}
              counts={data.verdict_mix.enough ? `${data.verdict_mix.periods.length} ${gran}s` : undefined}
              csv={data.verdict_mix.enough ? data.verdict_mix.periods : undefined}>
          {!data.verdict_mix.enough ? <Empty v={data.verdict_mix} /> : (
            <div className="h-64">
              <ResponsiveContainer>
                <AreaChart data={data.verdict_mix.periods.map((p) => ({ period: p.period, rows: p.rows, ...Object.fromEntries(VERDICTS.map((v) => [v, Math.round(p[`share_${v}` as const] * 1000) / 10])) }))} margin={{ left: 0, right: 8, top: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F2" />
                  <XAxis dataKey="period" tick={{ fontSize: 10 }} />
                  <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 10 }} />
                  <Tooltip formatter={(v: number, n: string) => [`${v}%`, n]} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  {VERDICTS.map((v) => <Area key={v} type="monotone" dataKey={v} stackId="1" stroke={VERDICT_COLOR[v]} fill={VERDICT_COLOR[v]} fillOpacity={0.75} />)}
                </AreaChart>
              </ResponsiveContainer>
            </div>)}
        </Card>

        <Card title="Heavy rain against the verdict" file="insights_heavy_rain.csv"
              what="Heavy days are the top 5% of a station's own wet days. The bars show how the checks judged them next to every other wet day."
              counts={data.heavy_rain.enough ? `${data.heavy_rain.stations.length} stations, heavy = ${data.heavy_rain.percentile}th percentile of wet days` : undefined}
              csv={data.heavy_rain.enough ? data.heavy_rain.points : undefined}>
          {!data.heavy_rain.enough ? <Empty v={data.heavy_rain} /> : (() => {
            const h = data.heavy_rain;
            const bars = [{ group: 'heavy days', ...shareOf(h.heavy_verdicts) }, { group: 'other wet days', ...shareOf(h.other_wet_verdicts) }];
            const unflagged = h.points.filter((p) => p.heavy && p.verdict === 'OK').slice(0, 8);
            return (<>
              <div className="grid md:grid-cols-2 gap-3">
                <div className="h-48">
                  <ResponsiveContainer>
                    <BarChart data={bars} layout="vertical" margin={{ left: 20, right: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F2" />
                      <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 10 }} />
                      <YAxis type="category" dataKey="group" tick={{ fontSize: 11 }} width={100} />
                      <Tooltip formatter={(v: number, n: string) => [`${v}%`, n]} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      {VERDICTS.map((v) => <Bar key={v} dataKey={v} stackId="a" fill={VERDICT_COLOR[v]} />)}
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="text-[11px] space-y-1">
                  <p className="font-bold">Heavy days that were not flagged (largest first)</p>
                  {unflagged.length === 0 ? <p className="text-slate-500">None in this selection.</p> : (
                    <table className="w-full font-mono text-[10px]"><thead><tr className="text-left text-slate-500"><th>Station</th><th>Day</th><th>mm</th></tr></thead>
                      <tbody>{unflagged.map((p) => <tr key={`${p.station}${p.day}`} className="border-t border-[#E2E8F2]"><td>{p.station}</td><td>{p.day}</td><td>{p.mm}</td></tr>)}</tbody></table>)}
                  <p className="text-slate-500">"Not flagged" is not "confirmed": nobody has said these days are genuine. A big value alone is never a fault.</p>
                </div>
              </div>
              {h.points_truncated && <p className="text-[10px] text-slate-500">The CSV holds the largest 1,500 wet days.</p>}
            </>);
          })()}
        </Card>
      </>)}
    </div>
  );
}
