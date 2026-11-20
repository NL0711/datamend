// Step 3, Stations: the stations the imported data identified, drawn on the India map where the data placed them. Select one for its RF25
// cell and region, its nearest IMD station, counts and first and last time. The RF25 region layer can be toggled; the NOAA list of IMD
// stations is an optional layer, off by default. Regions are RF25 client regions, not IMD's own boundaries.
import { useEffect, useMemo, useState } from 'react';
import { getExploreStations, getImdStations, getMapLayers } from './api';
import { IndiaMap, MapShow } from './IndiaMap';
import { regionColor } from './lib';
import { isPlaceable, stationPoints } from './stationpoints';
import type { ExploreStation, ExploreStations, ImdStation, MapLayers } from './types';
import { NextButton, Notice, Panel, formatError } from './ui';

const Cell = ({ k, v }: { k: string; v: string }) => (
  <div className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-2 py-1"><dt className="text-[10px] uppercase font-mono text-slate-500">{k}</dt><dd className="font-mono break-words">{v}</dd></div>);

export function StationsView({ onNext }: { onNext: () => void }) {
  const [data, setData] = useState<ExploreStations | null>(null);
  const [layers, setLayers] = useState<MapLayers | null>(null);
  const [imd, setImd] = useState<ImdStation[]>([]);
  const [show, setShow] = useState<MapShow>({ regions: true, imd: false });
  const [sel, setSel] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => {
    const fail = (what: string) => (e: unknown) => setErrors((x) => [...x, `${what}: ${formatError(e)}`]);
    getExploreStations().then(setData).catch(fail('Stations'));
    getMapLayers().then(setLayers).catch(fail('Land mask'));
  }, []);
  useEffect(() => {      // the optional layer is fetched only when it is switched on
    if (show.imd && imd.length === 0) getImdStations().then((r) => setImd(r.stations)).catch((e) => setErrors((x) => [...x, `IMD station list: ${formatError(e)}`]));
  }, [show.imd, imd.length]);

  const points = useMemo(() => {
    const own = stationPoints(data?.stations ?? []);
    const extra = show.imd ? imd.map((i) => ({ key: `imd:${i.id}`, kind: 'imd' as const, id: i.id, lat: i.latitude, lon: i.longitude, label: `${i.name} · IMD station (NOAA list)` })) : [];
    return [...extra, ...own];
  }, [data, imd, show.imd]);

  const stations = data?.stations ?? [];
  const selected: ExploreStation | undefined = stations.find((s) => s.station_key === sel);
  const placed = stations.filter(isPlaceable).length;

  return (
    <div className="space-y-3 max-w-[1300px]">
      {errors.map((e) => <Notice key={e} tone="error">{e}</Notice>)}
      <Panel className="p-3 flex items-center gap-x-5 gap-y-1 flex-wrap text-[11px] font-mono">
        <span><b>{data?.located ?? '…'}</b> located</span><span className={data && data.unlocated > 0 ? 'text-amber-800' : ''}><b>{data?.unlocated ?? '…'}</b> not located</span>
        <span><b>{placed}</b> drawn on the map</span>
        {data?.note && <span className="font-sans text-slate-600">{data.note}</span>}
      </Panel>
      {data && stations.length === 0 && <Notice tone="info">No stations yet: import a dataset (step 1) and the stations it names will appear here.</Notice>}

      <div className="grid xl:grid-cols-[1fr_360px] gap-3 items-start">
        <div className="space-y-2 min-w-0">
          <Panel className="p-2 flex items-center gap-x-4 gap-y-1 flex-wrap text-[11px]">
            <label className="flex items-center gap-1 font-bold text-slate-700"><input type="checkbox" checked={show.regions} onChange={() => setShow((s) => ({ ...s, regions: !s.regions }))} />RF25 regions</label>
            <label className="flex items-center gap-1 font-bold text-slate-700"><input type="checkbox" checked={show.imd} onChange={() => setShow((s) => ({ ...s, imd: !s.imd }))} />IMD stations (NOAA list)</label>
            <span className="ml-auto flex items-center gap-3 font-mono text-[10px] text-slate-600">
              <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full bg-[#0E7490]" />station in your data</span>
              {show.imd && <span className="flex items-center gap-1"><span style={{ width: 0, height: 0, borderLeft: '4px solid transparent', borderRight: '4px solid transparent', borderBottom: '7px solid #1E3A52', display: 'inline-block' }} />IMD station</span>}
            </span>
          </Panel>
          <IndiaMap layers={layers} points={points} show={show} selected={sel ? `station:${sel}` : null}
                    onSelect={(p) => setSel(p && p.kind === 'station' ? p.id : null)} />
          <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono text-slate-600">
            {show.regions && layers && layers.regions.map((r) => (
              <span key={r} className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm border border-slate-300" style={{ background: regionColor(r) }} />region {r}{layers.held_out_regions.includes(r) ? ' (held out)' : ''}</span>))}
          </div>
          <p className="text-[10px] text-slate-500">{layers?.note ?? 'Regions are the RF25 client regions, not IMD boundaries.'}</p>
        </div>

        <Panel className="p-3 space-y-3 xl:sticky xl:top-2">
          {!selected ? (
            <div className="space-y-2 text-xs"><h3 className="text-sm font-bold text-slate-900">Select a station</h3>
              <p className="text-slate-600">Click a circle on the map, or pick a station from the list below.</p></div>) : (
            <div className="space-y-2">
              <div><h3 className="text-sm font-bold text-slate-900">{selected.name ?? selected.station_key}</h3>
                <p className="font-mono text-[10px] text-slate-500">{selected.station_key}{[selected.state, selected.district].filter(Boolean).length ? ` · ${[selected.state, selected.district].filter(Boolean).join(', ')}` : ''}</p></div>
              {!selected.located && <Notice tone="warn">Not located: the data gave no usable position for this station, so it is listed but not drawn.</Notice>}
              <dl className="grid grid-cols-2 gap-2 text-[11px]">
                <Cell k="Position" v={selected.latitude !== null && selected.longitude !== null ? `${selected.latitude.toFixed(4)}, ${selected.longitude.toFixed(4)}` : 'none'} />
                <Cell k="RF25 cell" v={selected.rf25 ? `${selected.rf25.row}, ${selected.rf25.col} (${selected.rf25.is_land === null ? '?' : selected.rf25.is_land ? 'land' : 'sea'})` : 'none'} />
                <Cell k="RF25 region" v={selected.rf25 ? (selected.rf25.client_region !== null ? `region ${selected.rf25.client_region}` : 'none (sea)') : 'none'} />
                <Cell k="Nearest IMD station" v={selected.nearest_imd ? `${selected.nearest_imd.name} · ${selected.nearest_imd.km} km` : 'none'} />
                <Cell k="Observations" v={selected.n_observations.toLocaleString('en-IN')} />
                <Cell k="First, last time" v={`${selected.first ?? '?'} to ${selected.last ?? '?'}`} />
              </dl>
              <p className="text-[10px] text-slate-500">The IMD station is the nearest one in NOAA's list, not IMD's own list. Region and cell come from the RF25 grid.</p>
            </div>)}
        </Panel>
      </div>

      {stations.length > 0 && (
        <Panel className="p-3">
          <h3 className="text-xs font-bold text-slate-900 mb-1">Stations in the data ({stations.length})</h3>
          <div className="max-h-72 overflow-auto">
            <table className="w-full text-[11px]">
              <thead className="text-left bg-[#EDF1F7] sticky top-0"><tr><th className="px-2">Station</th><th className="px-2">State</th><th className="px-2 text-right">Observations</th><th className="px-2">Placed</th></tr></thead>
              <tbody>{stations.map((s) => (
                <tr key={s.station_key} tabIndex={0} onClick={() => setSel(s.station_key)} onKeyDown={(e) => { if (e.key === 'Enter') setSel(s.station_key); }}
                    className={`border-t border-[#E2E8F2] cursor-pointer hover:bg-[#F4F6FA] ${sel === s.station_key ? 'bg-sky-50' : ''}`}>
                  <td className="px-2 font-bold">{s.name ?? s.station_key}</td><td className="px-2">{s.state ?? '-'}</td>
                  <td className="px-2 text-right font-mono">{s.n_observations.toLocaleString('en-IN')}</td>
                  <td className={`px-2 font-mono font-bold ${isPlaceable(s) ? 'text-emerald-700' : 'text-amber-800'}`}>{isPlaceable(s) ? 'on map' : 'not located'}</td></tr>))}</tbody>
            </table>
          </div>
        </Panel>)}
      <NextButton label="Validate" onClick={onNext} />
    </div>);
}
