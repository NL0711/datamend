// Station network: every gauge and IMD station on a flat India map, and for each station where it is in the check -> flag -> audit cycle.
// Reads the stored runs and reviews (nothing is invented): a gauge with no rows checked is drawn grey. "IMD stations" are NOAA's list of
// Indian synoptic stations (IMD's own AWS/ARG list is not public). Regions are the RF25 client regions, not IMD's own boundaries.
import { useEffect, useMemo, useState } from 'react';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { getAllGauges, getImdStations, getMapLayers, getReplayStatus, getStationCycle, locate, startReplay, storedToken } from './api';
import { IndiaMap, MapPoint, MapShow } from './IndiaMap';
import { CYCLE_COLOR, CYCLE_LABEL, DECISION_LABEL, cycleState, distanceKm, networkTotals, regionColor } from './lib';
import type { CycleState } from './lib';
import type { Tab } from './OverviewView';
import type { GaugeStation, ImdStation, MapLayers, PlaceInfo, ReplayStatus, StationCycle, StationCycleResponse } from './types';
import { Notice, Panel, ReplayBadge, SyntheticBadge, formatError } from './ui';

interface Props { onAudit: (station: string) => void; onOpenRun: (id: number) => void; go: (t: Tab) => void }
type Selection = { key: string; kind: 'gauge' | 'imd' | 'upload' | 'cycle'; id: string };

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
      <p className="text-[10px] text-slate-500">State: <StateBadge s={state} />. An audit is one reviewer's judgement, not ground truth, and never changes a verdict, score or evidence.</p>
    </div>);
}

export function NetworkView({ onAudit, onOpenRun, go }: Props) {
  const [layers, setLayers] = useState<MapLayers | null>(null);
  const [gauges, setGauges] = useState<GaugeStation[]>([]);
  const [imd, setImd] = useState<ImdStation[]>([]);
  const [imdNote, setImdNote] = useState('');
  const [cycle, setCycle] = useState<StationCycleResponse | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [show, setShow] = useState<MapShow>({ regions: true, gauges: true, imd: true, dataOnly: false });
  const [sel, setSel] = useState<Selection | null>(null);
  const [place, setPlace] = useState<PlaceInfo | null>(null);
  const [replay, setReplay] = useState<ReplayStatus | null>(null);
  const [replayError, setReplayError] = useState('');

  useEffect(() => {
    const fail = (what: string) => (e: unknown) => setErrors((x) => [...x, `${what}: ${formatError(e)}`]);
    getMapLayers().then(setLayers).catch(fail('Land mask'));
    getAllGauges().then((g) => setGauges(g.stations)).catch(fail('Gauge catalogue'));
    getImdStations().then((r) => { setImd(r.stations); setImdNote(r.note); }).catch(fail('IMD station list'));
    getStationCycle().then(setCycle).catch(fail('Station cycle'));
    getReplayStatus().then(setReplay).catch(() => setReplay(null));
  }, []);

  // while the replay downloads, ask for its state every few seconds; when it finishes, reload the cycle so the map fills
  const replayState = replay?.state;
  useEffect(() => {
    if (replayState !== 'running') return;
    const t = window.setInterval(() => {
      getReplayStatus().then((r) => {
        setReplay(r);
        if (r.state !== 'running') getStationCycle().then(setCycle).catch(() => undefined);
      }).catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(t);
  }, [replayState]);

  const loadReplay = () => {
    setReplayError('');
    startReplay(storedToken()).then(setReplay).catch((e) => setReplayError(formatError(e)));
  };

  const byId = useMemo(() => new Map((cycle?.stations ?? []).map((s) => [s.station_id, s])), [cycle]);
  const gaugeById = useMemo(() => new Map(gauges.map((g) => [g.station_id, g])), [gauges]);

  const points = useMemo<MapPoint[]>(() => {
    const out: MapPoint[] = [];
    const onlySynthetic = (c: StationCycle | undefined) => !!c && c.checked > 0 && c.synthetic_rows >= c.checked;
    for (const i of imd) {
      const c = byId.get(i.id);
      const st = cycleState(c);
      out.push({ key: `imd:${i.id}`, kind: 'imd', id: i.id, lat: i.latitude, lon: i.longitude, state: st, synthetic: onlySynthetic(c),
                 label: `${i.name} · IMD station (NOAA list) · ${st === 'unchecked' ? `data to ${i.last_data ?? '?'}` : `${CYCLE_LABEL[st]}${c && c.replay_rows > 0 ? ' · REPLAY' : ''}`}` });
    }
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
  }, [imd, gauges, cycle, byId]);

  const totals = useMemo(() => networkTotals(cycle?.stations ?? []), [cycle]);
  const selGauge = sel && (sel.kind === 'gauge') ? gaugeById.get(sel.id) : undefined;
  const selCycle = sel && sel.kind !== 'imd' ? byId.get(sel.id) : undefined;
  const selImd = sel && sel.kind === 'imd' ? imd.find((i) => i.id === sel.id) : undefined;
  const selPos = selGauge ? { lat: selGauge.latitude, lon: selGauge.longitude } : selCycle && selCycle.latitude !== null && selCycle.longitude !== null ? { lat: selCycle.latitude, lon: selCycle.longitude } : null;

  useEffect(() => {
    setPlace(null);
    let current = true;                                  // a slower answer for an earlier selection must not overwrite a newer one
    if (selPos) locate(selPos.lat, selPos.lon).then((p) => { if (current) setPlace(p); }).catch(() => { if (current) setPlace(null); });
    return () => { current = false; };
  }, [selPos?.lat, selPos?.lon]); // eslint-disable-line react-hooks/exhaustive-deps

  const nearbyGauges = useMemo(() => {
    if (!selImd) return [];
    return gauges.map((g) => ({ g, km: distanceKm(selImd.latitude, selImd.longitude, g.latitude, g.longitude) })).filter((x) => x.km <= 30).sort((a, b) => a.km - b.km).slice(0, 8);
  }, [selImd, gauges]);

  const toggle = (k: keyof MapShow) => setShow((s) => ({ ...s, [k]: !s[k] }));
  const nearest = selGauge?.nearest_imd ?? selCycle?.nearest_imd ?? null;
  const selectByKey = (kind: Selection['kind'], id: string) => setSel({ key: `${kind}:${id}`, kind, id });

  return (
    <div className="space-y-3">
      <p className="text-[11px] font-mono text-slate-500">flat map from the RF25 land mask · {gauges.length} gauges · {imd.length} IMD stations</p>
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

      <Panel className="p-3">
        <div className="flex items-center gap-3 flex-wrap">
          <ReplayBadge />
          <div className="flex-1 min-w-[16rem] text-xs">
            <div className="font-bold text-slate-900">NOAA ISD India replay</div>
            <p className="text-slate-600">
              {replay === null ? 'Replay status is not available.'
                : replay.state === 'running' ? 'Downloading station files from NOAA…'
                : replay.stored_run_id !== null ? `Loaded: ${replay.stored_run_label ?? `run ${replay.stored_run_id}`}.`
                : `Not loaded. Real daily rainfall of up to ${replay.default_stations} Indian stations for ${replay.year}; a replay, never live.`}
            </p>
          </div>
          {replay && replay.stored_run_id !== null && <button onClick={() => onOpenRun(replay.stored_run_id as number)} className="px-3 py-1.5 rounded border border-[#D3DCE7] bg-white text-xs font-bold">Open run</button>}
          <button onClick={loadReplay} disabled={replay === null || replay.state === 'running'} className="px-3 py-1.5 rounded bg-teal-700 text-white text-xs font-bold disabled:opacity-40">
            {replay?.stored_run_id !== null && replay?.stored_run_id !== undefined ? 'Reload replay' : 'Load replay'}</button>
        </div>
        {replay?.state === 'failed' && <p className="text-[11px] text-red-700 mt-1">{replay.message ?? 'The replay failed.'}</p>}
        {replay?.state === 'done' && replay.stations_ok < replay.stations.length && <p className="text-[11px] text-amber-700 mt-1">{replay.stations_ok} of {replay.stations.length} stations downloaded.</p>}
        {replayError && <p className="text-[11px] text-red-700 mt-1">{replayError} (loading needs the admin token set in Settings)</p>}
        <p className="text-[10px] text-slate-500 mt-1">{replay?.note}</p>
      </Panel>

      <div className="grid xl:grid-cols-[1fr_380px] gap-3 items-start">
        <div className="space-y-2 min-w-0">
          <Panel className="p-2 flex items-center gap-x-4 gap-y-1 flex-wrap text-[11px]">
            {([['regions', 'RF25 regions'], ['gauges', `Weather Union gauges (${gauges.length})`], ['imd', `IMD stations (${imd.length})`], ['dataOnly', 'Gauges with data only']] as const).map(([k, label]) => (
              <label key={k} className="flex items-center gap-1 font-bold text-slate-700"><input type="checkbox" checked={show[k]} onChange={() => toggle(k)} />{label}</label>))}
            <span className="ml-auto flex items-center gap-2 font-mono text-[10px] text-slate-600 flex-wrap">
              {STATE_ORDER.map((s) => <span key={s} className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: CYCLE_COLOR[s] }} />{CYCLE_LABEL[s]} ({totals.byState[s]})</span>)}
              <span className="flex items-center gap-1"><span style={{ width: 0, height: 0, borderLeft: '4px solid transparent', borderRight: '4px solid transparent', borderBottom: '7px solid #111827', display: 'inline-block' }} />IMD station</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 rounded-full" style={{ border: '2px dashed #334155' }} />synthetic rows only</span>
            </span>
          </Panel>
          <IndiaMap layers={layers} points={points} show={show} selected={sel?.key ?? null} onSelect={(p) => setSel(p ? { key: p.key, kind: p.kind, id: p.id } : null)} />
          <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono text-slate-600">
            {show.regions && layers && layers.regions.map((r) => (
              <span key={r} className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm border border-slate-300" style={{ background: regionColor(r) }} />region {r}{layers.held_out_regions.includes(r) ? ' (held out)' : ''}</span>))}
          </div>
          <p className="text-[10px] text-slate-500">{layers?.note ?? 'Regions are the RF25 client regions.'} {imdNote}</p>
        </div>

        <Panel className="p-3 space-y-3 xl:sticky xl:top-2">
          {!sel && (
            <div className="space-y-2 text-xs">
              <h3 className="text-xs font-bold text-slate-900">Select a station on the map</h3>
              <p className="text-slate-600">Click a gauge, an IMD station or a diamond (a station from an uploaded file) to see where it is in the cycle.</p>
              {(cycle?.stations.length ?? 0) === 0
                ? <Notice tone="info">No rows have been checked yet, so every station is grey. Load the replay above, upload a file in <button className="font-bold text-sky-700" onClick={() => go('runs')}>Runs</button> whose station ids match a gauge, or turn on the live feed in <button className="font-bold text-sky-700" onClick={() => go('settings')}>Settings</button>.</Notice>
                : <p className="text-[11px] text-slate-600">{cycle?.positioned} of {cycle?.count} stations with rows have a position on the map.</p>}
            </div>)}

          {sel && selImd && (
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2"><span style={{ width: 0, height: 0, borderLeft: '5px solid transparent', borderRight: '5px solid transparent', borderBottom: '9px solid #111827', display: 'inline-block' }} /><h3 className="text-sm font-bold text-slate-900">{selImd.name}</h3></div>
              <p className="font-mono text-[10px] text-slate-500">IMD station (NOAA list) · id {selImd.id}{selImd.icao ? ` · ICAO ${selImd.icao}` : ''}</p>
              <dl className="grid grid-cols-2 gap-2 text-[11px]">
                {[['Position', `${selImd.latitude.toFixed(3)}, ${selImd.longitude.toFixed(3)}`], ['Elevation', selImd.elevation_m !== null ? `${selImd.elevation_m} m` : 'unknown'],
                  ['First data', selImd.first_data ?? 'unknown'], ['Last data', selImd.last_data ?? 'unknown']].map(([k, v]) => (
                  <div key={k} className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-2 py-1"><dt className="text-[10px] uppercase font-mono text-slate-500">{k}</dt><dd className="font-mono">{v}</dd></div>))}
              </dl>
              <div><div className="text-[10px] uppercase font-mono text-slate-500 mb-1">Weather Union gauges within 30 km</div>
                {nearbyGauges.length === 0 ? <p className="text-slate-500">none</p> : (
                  <ul className="space-y-0.5">{nearbyGauges.map(({ g, km }) => (
                    <li key={g.station_id}><button onClick={() => selectByKey('gauge', g.station_id)} className="text-left w-full flex items-center gap-2 hover:bg-[#F4F6FA] rounded px-1 py-0.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: CYCLE_COLOR[cycleState(byId.get(g.station_id))] }} /><span className="font-bold">{g.place}</span><span className="ml-auto font-mono text-[10px] text-slate-500">{km.toFixed(1)} km</span></button></li>))}</ul>)}
              </div>
              {byId.get(selImd.id)
                ? (<div className="space-y-1"><div className="flex items-center gap-2"><span className="text-[10px] uppercase font-mono text-slate-500">Rows checked for this station</span>{(byId.get(selImd.id)?.replay_rows ?? 0) > 0 && <ReplayBadge />}</div>
                    <CyclePanel c={byId.get(selImd.id) as StationCycle} onAudit={onAudit} onOpenRun={onOpenRun} /></div>)
                : <p className="text-slate-500">No rows checked for this station yet.</p>}
              <p className="text-[10px] text-slate-500">Name and position come from NOAA's archive; this is not IMD's own station list.</p>
            </div>)}

          {sel && !selImd && (
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
                    <div className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-2 py-1"><dt className="text-[10px] uppercase font-mono text-slate-500">Nearest IMD station</dt>
                      <dd>{nearest ? <button onClick={() => selectByKey('imd', nearest.id)} className="text-left text-sky-700 font-bold hover:underline">{nearest.name} · {nearest.km} km</button> : <span className="font-mono">none</span>}</dd></div>
                  </dl>)
                : <Notice tone="warn">No position: this station id is not in the gauge catalogue and its file has no latitude and longitude columns, so it is listed but not drawn.</Notice>}
              {selCycle
                ? <CyclePanel c={selCycle} onAudit={onAudit} onOpenRun={onOpenRun} />
                : <Notice tone="info">No rows checked for this station yet. Upload a file with this station id in <button className="font-bold text-sky-700" onClick={() => go('runs')}>Runs</button>, or enable the live feed in <button className="font-bold text-sky-700" onClick={() => go('settings')}>Settings</button>.</Notice>}
            </div>)}
        </Panel>
      </div>

      {cycle && cycle.stations.length > 0 && (
        <Panel className="p-3">
          <h3 className="text-xs font-bold text-slate-900 mb-1">Stations with rows ({cycle.count}) · awaiting audit first</h3>
          <div className="max-h-72 overflow-y-auto">
            <table className="w-full text-[11px]">
              <thead className="text-left bg-[#EDF1F7] sticky top-0"><tr><th className="px-2">Station</th><th className="px-2">State</th><th className="px-2 text-right">Checked</th><th className="px-2 text-right">Flagged</th><th className="px-2 text-right">Audited</th><th className="px-2 text-right">Awaiting</th><th className="px-2">Nearest IMD</th></tr></thead>
              <tbody>{cycle.stations.map((s) => (
                <tr key={s.station_id} onClick={() => selectByKey(s.position_source === 'catalogue' ? 'gauge' : s.position_source === 'upload' ? 'upload' : s.position_source === 'imd' ? 'imd' : 'cycle', s.station_id)}
                    className={`border-t border-[#E2E8F2] cursor-pointer hover:bg-[#F4F6FA] ${sel?.id === s.station_id ? 'bg-sky-50' : ''}`}>
                  <td className="px-2 font-bold">{s.place ?? s.station_id}<div className="font-mono text-[10px] text-slate-400">{s.station_id}{s.synthetic_rows > 0 ? ' · has synthetic rows' : ''}</div></td>
                  <td className="px-2"><StateBadge s={cycleState(s)} /></td><td className="px-2 text-right font-mono">{s.checked}</td><td className="px-2 text-right font-mono">{s.flagged}</td>
                  <td className="px-2 text-right font-mono">{Math.min(s.audited, s.flagged)}</td><td className={`px-2 text-right font-mono ${s.unaudited > 0 ? 'text-red-700 font-bold' : ''}`}>{s.unaudited}</td>
                  <td className="px-2 font-mono">{s.nearest_imd ? `${s.nearest_imd.name} · ${s.nearest_imd.km} km` : '—'}</td></tr>))}</tbody>
            </table>
          </div>
        </Panel>)}
    </div>
  );
}
