// Stations: every gauge on a flat India map or the 3D globe, a point lookup, and for each station where it is in the
// check -> flag -> audit cycle. Reads the stored runs and reviews (nothing is invented): a gauge with no rows checked is drawn grey.
// Regions are the RF25 client regions, not IMD's own boundaries.
import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, Globe2, Map as MapIcon, ShieldCheck } from 'lucide-react';
import { getAllGauges, getMapLayers, getStationCycle, locate } from './api';
import { IndiaMap, MapPoint, MapShow } from './IndiaMap';
import { CYCLE_COLOR, CYCLE_LABEL, DECISION_LABEL, cycleState, globeState, networkTotals, regionColor } from './lib';
import type { CycleState } from './lib';
import { StationGlobe3D } from '../globe/StationGlobe3D';
import type { GlobeStation } from '../globe/StationGlobe3D';
import type { Tab } from './OverviewView';
import type { GaugeStation, MapLayers, PlaceInfo, StationCycle, StationCycleResponse } from './types';
import { Notice, Panel, SyntheticBadge, formatError } from './ui';

// `selectedStationId` and `onSelectStation` tie the pin and table selection to the shell's one selected station.
interface Props { onAudit: (station: string) => void; onOpenRun: (id: number) => void; go: (t: Tab) => void; selectedStationId?: string | null; onSelectStation?: (id: string) => void }
type Selection = { key: string; kind: 'gauge' | 'upload' | 'cycle'; id: string };

const STATE_ORDER: CycleState[] = ['flagged', 'audited', 'clean', 'nodata', 'unchecked'];

function StateBadge({ s }: { s: CycleState }) {
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border border-[#D3DCE7] bg-white">
      <span className="w-2 h-2 rounded-full" style={{ background: CYCLE_COLOR[s] }} />{CYCLE_LABEL[s]}
    </span>);
}

function Step({ n, title, children, tone }: { n: number; title: string; children: React.ReactNode; tone: string }) {
  return (
    <div className="rounded border border-[#D3DCE7] bg-[#F4F6FA] p-2 text-[11px] flex-1 min-w-0">
      <div className="flex items-center gap-1.5 mb-1"><span className="w-4 h-4 rounded-full text-white text-[10px] font-bold flex items-center justify-center" style={{ background: tone }}>{n}</span><span className="font-bold text-slate-900 text-xs">{title}</span></div>
      {children}
    </div>);
}

function CyclePanel({ c, onAudit, onOpenRun }: { c: StationCycle; onAudit: (s: string) => void; onOpenRun: (id: number) => void }) {
  const state = cycleState(c);
  return (
    <div className="space-y-2">
      <div className="flex items-stretch gap-1">
        <Step n={1} title="Check" tone="#0284C7">
          <div><b className="font-mono">{c.checked}</b> rows checked</div>
          <div className="text-slate-500">{c.runs} run(s)</div>
          {c.synthetic_rows > 0 && <div className="mt-0.5"><SyntheticBadge /> <span className="font-mono">{c.synthetic_rows}</span></div>}
        </Step>
        <ArrowRight className="w-3 h-3 self-center text-slate-400 shrink-0" />
        <Step n={2} title="Flag" tone="#EF4444">
          <div><b className="font-mono">{c.suspect}</b> SUSPECT</div>
          <div><b className="font-mono">{c.uncertain}</b> UNCERTAIN</div>
          <div className="text-slate-500">{c.no_data} NO_DATA</div>
        </Step>
        <ArrowRight className="w-3 h-3 self-center text-slate-400 shrink-0" />
        <Step n={3} title="Audit" tone="#2563EB">
          <div><b className="font-mono">{Math.min(c.audited, c.flagged)}</b> of <b className="font-mono">{c.flagged}</b> flagged</div>
          <div className={c.unaudited > 0 ? 'text-red-700 font-bold' : 'text-slate-500'}>{c.unaudited} awaiting</div>
        </Step>
      </div>
      {Object.keys(c.top_checks).length > 0 && (
        <div className="text-[11px]"><div className="text-[10px] uppercase font-mono text-slate-500">Checks that fired</div>
          <div className="flex flex-wrap gap-1 mt-0.5">{Object.entries(c.top_checks).map(([k, v]) => <span key={k} className="px-1.5 py-0.5 rounded bg-[#EDF1F7] font-mono">{k} {v}</span>)}</div></div>)}
      {c.audited > 0 && (
        <div className="text-[11px]"><div className="text-[10px] uppercase font-mono text-slate-500">Reviewer decisions (latest per row)</div>
          <div className="flex flex-wrap gap-1 mt-0.5">{Object.entries(c.decisions).filter(([, n]) => n > 0).map(([d, n]) => <span key={d} className="px-1.5 py-0.5 rounded bg-blue-50 border border-blue-200 font-mono">{DECISION_LABEL[d] ?? d} {n}</span>)}</div></div>)}
      <div className="flex gap-2 flex-wrap pt-1">
        <button disabled={c.flagged === 0} onClick={() => onAudit(c.station_id)} className="flex items-center gap-1 px-3 py-1.5 rounded bg-sky-600 text-white text-xs font-bold disabled:opacity-40"><ShieldCheck className="w-3.5 h-3.5" />Audit this station's flags</button>
        {c.latest_run_id !== null && <button onClick={() => onOpenRun(c.latest_run_id as number)} className="px-3 py-1.5 rounded border border-[#D3DCE7] bg-white text-xs font-bold">Open latest run</button>}
      </div>
      <p className="text-[10px] text-slate-500">State: <StateBadge s={state} /></p>
    </div>);
}

/** A stateless point lookup: the RF25 cell, land or sea, and region of a latitude and longitude. */
function Locate() {
  const [lat, setLat] = useState('');
  const [lon, setLon] = useState('');
  const [place, setPlace] = useState<PlaceInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = async () => {
    setError(null); setPlace(null);
    const a = Number(lat), b = Number(lon);
    if (!lat.trim() || !lon.trim() || !Number.isFinite(a) || !Number.isFinite(b)) { setError('Enter a latitude and a longitude.'); return; }
    try { setPlace(await locate(a, b)); } catch (e) { setError(formatError(e)); }
  };
  const field = 'text-xs border border-[#D3DCE7] rounded px-2 py-1.5 w-full';
  return (
    <div className="space-y-2 text-xs">
      <h3 className="text-xs font-bold text-slate-900">Locate a point</h3>
      <form className="grid grid-cols-[1fr_1fr_auto] gap-2" onSubmit={(e) => { e.preventDefault(); void run(); }}>
        <input value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" placeholder="Latitude" className={field} aria-label="latitude" />
        <input value={lon} onChange={(e) => setLon(e.target.value)} inputMode="decimal" placeholder="Longitude" className={field} aria-label="longitude" />
        <button type="submit" className="px-3 rounded bg-sky-600 text-white font-bold">Locate</button>
      </form>
      {error && <Notice tone="error">{error}</Notice>}
      {place && (
        <dl className="grid grid-cols-2 gap-2 text-[11px]">
          {[['RF25 cell', `${place.cell.row}, ${place.cell.col}`], ['Land or sea', place.is_land === null ? 'unknown' : place.is_land ? 'land' : 'sea'],
            ['Cell centre', `${place.cell.lat}, ${place.cell.lon}`], ['Region', place.client_region ?? 'none (sea)']].map(([k, v]) => (
            <div key={k} className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-2 py-1"><dt className="text-[10px] uppercase font-mono text-slate-500">{k}</dt><dd className="font-mono">{String(v)}</dd></div>))}
        </dl>)}
    </div>);
}

export function StationsView({ onAudit, onOpenRun, go, selectedStationId, onSelectStation }: Props) {
  const [view, setView] = useState<'map' | 'globe'>('map');
  const [layers, setLayers] = useState<MapLayers | null>(null);
  const [gauges, setGauges] = useState<GaugeStation[]>([]);
  const [cycle, setCycle] = useState<StationCycleResponse | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [show, setShow] = useState<MapShow>({ regions: true, gauges: true, dataOnly: false });
  const [sel, setSel] = useState<Selection | null>(null);
  const [place, setPlace] = useState<PlaceInfo | null>(null);

  useEffect(() => {
    const fail = (what: string) => (e: unknown) => setErrors((x) => [...x, `${what}: ${formatError(e)}`]);
    getMapLayers().then(setLayers).catch(fail('Land mask'));
    getAllGauges().then((g) => setGauges(g.stations)).catch(fail('Gauge catalogue'));
    getStationCycle().then(setCycle).catch(fail('Station cycle'));
  }, []);

  const byId = useMemo(() => new Map((cycle?.stations ?? []).map((s) => [s.station_id, s])), [cycle]);
  const gaugeById = useMemo(() => new Map(gauges.map((g) => [g.station_id, g])), [gauges]);

  // one selected station for the whole shell: a pin or row chosen here is reported up, a station chosen in the header is shown here
  useEffect(() => { if (sel && sel.id !== selectedStationId) onSelectStation?.(sel.id); }, [sel?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!selectedStationId) return;
    const kind: Selection['kind'] = gaugeById.has(selectedStationId) ? 'gauge' : byId.get(selectedStationId)?.position_source === 'upload' ? 'upload' : 'cycle';
    const key = `${kind}:${selectedStationId}`;
    setSel((cur) => (cur?.key === key ? cur : { key, kind, id: selectedStationId }));
  }, [selectedStationId, gaugeById, byId]);

  const points = useMemo<MapPoint[]>(() => {
    const out: MapPoint[] = [];
    const onlySynthetic = (c: StationCycle | undefined) => !!c && c.checked > 0 && c.synthetic_rows >= c.checked;
    for (const g of gauges) {
      const c = byId.get(g.station_id);
      const st = cycleState(c);
      out.push({ key: `gauge:${g.station_id}`, kind: 'gauge', id: g.station_id, label: `${g.place} · ${CYCLE_LABEL[st]}${onlySynthetic(c) ? ' · SYNTHETIC rows only' : ''}`,
                 lat: g.latitude, lon: g.longitude, state: st, synthetic: onlySynthetic(c) });
    }
    for (const c of cycle?.stations ?? []) {
      if (c.position_source === 'upload' && c.latitude !== null && c.longitude !== null) {
        out.push({ key: `upload:${c.station_id}`, kind: 'upload', id: c.station_id, label: `${c.station_id} · from an uploaded file · ${CYCLE_LABEL[cycleState(c)]}${onlySynthetic(c) ? ' · SYNTHETIC rows only' : ''}`,
                   lat: c.latitude, lon: c.longitude, state: cycleState(c), synthetic: onlySynthetic(c) });
      }
    }
    return out;
  }, [gauges, cycle, byId]);

  const pins = useMemo<GlobeStation[]>(() => {
    const out: GlobeStation[] = gauges.map((g) => {
      const c = byId.get(g.station_id);
      return { station_id: g.station_id, label: g.place, latitude: g.latitude, longitude: g.longitude, state: globeState(c),
               checked: c?.checked ?? 0, suspect: c?.suspect ?? 0, uncertain: c?.uncertain ?? 0, runs: c?.runs ?? 0, positionSource: 'catalogue' };
    });
    const known = new Set(gauges.map((g) => g.station_id));
    for (const c of cycle?.stations ?? []) {                  // stations from uploads that carry their own coordinates
      if (known.has(c.station_id) || c.latitude === null || c.longitude === null) continue;
      out.push({ station_id: c.station_id, label: c.station_id, latitude: c.latitude, longitude: c.longitude, state: globeState(c),
                 checked: c.checked, suspect: c.suspect, uncertain: c.uncertain, runs: c.runs, positionSource: c.position_source });
    }
    return out;
  }, [gauges, cycle, byId]);

  const totals = useMemo(() => networkTotals(cycle?.stations ?? []), [cycle]);
  const selGauge = sel && (sel.kind === 'gauge') ? gaugeById.get(sel.id) : undefined;
  const selCycle = sel ? byId.get(sel.id) : undefined;
  const selPos = selGauge ? { lat: selGauge.latitude, lon: selGauge.longitude } : selCycle && selCycle.latitude !== null && selCycle.longitude !== null ? { lat: selCycle.latitude, lon: selCycle.longitude } : null;

  useEffect(() => {
    setPlace(null);
    let current = true;                                  // a slower answer for an earlier selection must not overwrite a newer one
    if (selPos) locate(selPos.lat, selPos.lon).then((p) => { if (current) setPlace(p); }).catch(() => { if (current) setPlace(null); });
    return () => { current = false; };
  }, [selPos?.lat, selPos?.lon]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = (k: keyof MapShow) => setShow((s) => ({ ...s, [k]: !s[k] }));
  const selectByKey = (kind: Selection['kind'], id: string) => setSel({ key: `${kind}:${id}`, kind, id });

  return (
    <div className="space-y-3">
      {errors.map((e) => <Notice key={e} tone="error">{e}</Notice>)}

      <Panel className="p-3">
        <div className="flex items-center gap-x-5 gap-y-1 flex-wrap text-[11px] font-mono">
          <span className="font-bold text-slate-900 font-sans text-xs">Check → Flag → Audit</span>
          <span><b>{totals.stations}</b> stations with rows</span><span><b>{totals.checked}</b> rows checked</span>
          <span className="text-red-700"><b>{totals.flagged}</b> flagged</span><span className="text-blue-700"><b>{totals.audited}</b> audited</span>
          <span className={totals.unaudited > 0 ? 'text-red-700 font-bold' : ''}><b>{totals.unaudited}</b> awaiting audit</span>
          {cycle && <span className="text-slate-500">{cycle.storage}</span>}
        </div>
        {cycle?.truncated_reviews && <p className="text-[10px] text-amber-700 mt-1">Only the newest reviews were counted (cap reached), so audit counts may be low.</p>}
        {cycle?.truncated && <p className="text-[10px] text-amber-700 mt-1">Showing {cycle.shown} of {cycle.count} stations (those awaiting audit first); the totals above cover only these.</p>}
        {cycle?.positions_truncated && <p className="text-[10px] text-amber-700 mt-1">Some stations from uploaded files were not placed on the map (limit reached); they are listed in the table without a position.</p>}
      </Panel>

      <div className="grid xl:grid-cols-[1fr_380px] gap-3 items-start">
        <div className="space-y-2 min-w-0">
          <Panel className="p-2 flex items-center gap-x-4 gap-y-1 flex-wrap text-[11px]">
            <div className="inline-flex rounded border border-[#D3DCE7] overflow-hidden" role="group" aria-label="view">
              {([['map', 'Map', MapIcon], ['globe', 'Globe', Globe2]] as const).map(([k, label, Icon]) => (
                <button key={k} onClick={() => setView(k)} aria-pressed={view === k} className={`px-3 py-1 text-xs font-bold flex items-center gap-1 ${view === k ? 'bg-sky-600 text-white' : 'bg-white text-slate-600'}`}><Icon className="w-3.5 h-3.5" />{label}</button>))}
            </div>
            {view === 'map' && ([['regions', 'RF25 regions'], ['gauges', `Weather Union gauges (${gauges.length})`], ['dataOnly', 'Gauges with data only']] as const).map(([k, label]) => (
              <label key={k} className="flex items-center gap-1 font-bold text-slate-700"><input type="checkbox" checked={show[k]} onChange={() => toggle(k)} />{label}</label>))}
            <span className="ml-auto flex items-center gap-2 font-mono text-[10px] text-slate-600 flex-wrap">
              {STATE_ORDER.map((s) => <span key={s} className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: CYCLE_COLOR[s] }} />{CYCLE_LABEL[s]} ({totals.byState[s]})</span>)}
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ border: '2px dashed #7C3AED' }} />synthetic rows only</span>
            </span>
          </Panel>
          {view === 'map' ? (<>
            <IndiaMap layers={layers} points={points} show={show} selected={sel?.key ?? null} onSelect={(p) => setSel(p ? { key: p.key, kind: p.kind, id: p.id } : null)} />
            {show.regions && layers && (
              <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono text-slate-600">
                {layers.regions.map((r) => (
                  <span key={r} className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm border border-slate-300" style={{ background: regionColor(r) }} />region {r}{layers.held_out_regions.includes(r) ? ' (held out)' : ''}</span>))}
              </div>)}
          </>) : (
            <StationGlobe3D stations={pins} selectedStationId={sel?.id} onSelectStation={(id) => selectByKey(gaugeById.has(id) ? 'gauge' : byId.get(id)?.position_source === 'upload' ? 'upload' : 'cycle', id)}
                            className="rounded-xl overflow-hidden border border-[#D3DCE7]" />)}
        </div>

        <Panel className="p-3 space-y-3 xl:sticky xl:top-2">
          {!sel && (
            <div className="space-y-3 text-xs">
              <p className="text-slate-600">Select a station to see where it is in the cycle.{(cycle?.stations.length ?? 0) === 0 && <> Nothing is checked yet: <button className="font-bold text-sky-700" onClick={() => go('runs')}>add a run</button>.</>}</p>
              <Locate />
            </div>)}

          {sel && (
            <div className="space-y-3">
              <div>
                <div className="flex items-center gap-2 flex-wrap"><h3 className="text-sm font-bold text-slate-900">{selGauge?.place ?? selCycle?.place ?? sel.id}</h3><StateBadge s={cycleState(selCycle)} /></div>
                <p className="font-mono text-[10px] text-slate-500">{sel.id}{selGauge ? ` · ${selGauge.city} · ${selGauge.device}` : ''}{selCycle?.position_source === 'upload' ? ' · position from the uploaded file' : ''}</p>
              </div>
              {selPos
                ? (
                  <dl className="grid grid-cols-2 gap-2 text-[11px]">
                    {[['Position', `${selPos.lat.toFixed(4)}, ${selPos.lon.toFixed(4)}`],
                      ['RF25 cell', place ? `${place.cell.row}, ${place.cell.col} (${place.is_land === null ? '?' : place.is_land ? 'land' : 'sea'})` : '…'],
                      ['RF25 region', place ? (place.client_region !== null ? `region ${place.client_region}` : 'none (sea)') : '…']].map(([k, v]) => (
                      <div key={k} className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-2 py-1"><dt className="text-[10px] uppercase font-mono text-slate-500">{k}</dt><dd className="font-mono">{v}</dd></div>))}
                  </dl>)
                : <Notice tone="warn">No position: the id is not in the gauge catalogue and its file has no latitude and longitude columns.</Notice>}
              {selCycle
                ? <CyclePanel c={selCycle} onAudit={onAudit} onOpenRun={onOpenRun} />
                : <Notice tone="info">No rows checked for this station yet. <button className="font-bold text-sky-700" onClick={() => go('runs')}>Add a run</button>.</Notice>}
            </div>)}
        </Panel>
      </div>

      {cycle && cycle.stations.length > 0 && (
        <Panel className="p-3">
          <h3 className="text-xs font-bold text-slate-900 mb-1">Stations with rows ({cycle.count}) · awaiting audit first</h3>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-[11px]">
              <thead className="text-left bg-[#EDF1F7] sticky top-0"><tr><th className="px-2">Station</th><th className="px-2">State</th><th className="px-2 text-right">Checked</th><th className="px-2 text-right">Flagged</th><th className="px-2 text-right">Audited</th><th className="px-2 text-right">Awaiting</th></tr></thead>
              <tbody>{cycle.stations.map((s) => (
                <tr key={s.station_id} onClick={() => selectByKey(s.position_source === 'catalogue' ? 'gauge' : s.position_source === 'upload' ? 'upload' : 'cycle', s.station_id)}
                    className={`border-t border-[#E2E8F2] cursor-pointer hover:bg-[#F4F6FA] ${sel?.id === s.station_id ? 'bg-sky-50' : ''}`}>
                  <td className="px-2 font-bold">{s.place ?? s.station_id}<div className="font-mono text-[10px] text-slate-400">{s.station_id}{s.synthetic_rows > 0 ? ' · has synthetic rows' : ''}</div></td>
                  <td className="px-2"><StateBadge s={cycleState(s)} /></td><td className="px-2 text-right font-mono">{s.checked}</td><td className="px-2 text-right font-mono">{s.flagged}</td>
                  <td className="px-2 text-right font-mono">{Math.min(s.audited, s.flagged)}</td><td className={`px-2 text-right font-mono ${s.unaudited > 0 ? 'text-red-700 font-bold' : ''}`}>{s.unaudited}</td></tr>))}</tbody>
            </table>
          </div>
        </Panel>)}
    </div>
  );
}
