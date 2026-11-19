// Locations, trimmed to rainfall (spec: a stateless place lookup): the RF25 grid cell, land or sea, and client region for a point, plus the
// Weather Union gauge catalogue. It stores nothing and shows no weather: no model product is ever presented as an observation.
import { useEffect, useState } from 'react';
import { MapPin } from 'lucide-react';
import { getGauges, locate } from './api';
import type { GaugeStation, PlaceInfo } from './types';
import { Notice, Panel, formatError } from './ui';

const field = 'text-xs border border-[#D3DCE7] rounded px-2 py-1.5 w-full';

export function PlacesView() {
  const [lat, setLat] = useState('19.076');
  const [lon, setLon] = useState('72.8777');
  const [place, setPlace] = useState<PlaceInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [city, setCity] = useState('Mumbai');
  const [cities, setCities] = useState<string[]>([]);
  const [gauges, setGauges] = useState<GaugeStation[]>([]);
  const [count, setCount] = useState(0);

  const lookup = async (la = lat, lo = lon) => {
    setError(null); setPlace(null);
    const a = Number(la), b = Number(lo);
    if (la.trim() === '' || lo.trim() === '' || !Number.isFinite(a) || !Number.isFinite(b)) { setError('Enter a latitude and a longitude as numbers.'); return; }
    try { setPlace(await locate(a, b)); } catch (e) { setError(formatError(e)); }
  };
  useEffect(() => { getGauges(city).then((g) => { setGauges(g.stations); setCities(g.cities); setCount(g.count); }).catch((e) => setError(formatError(e))); }, [city]);
  useEffect(() => { void lookup(); /* the example point on first load */ }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3 max-w-5xl">
      <Panel className="p-4 space-y-3">
        <div className="flex items-center gap-2"><MapPin className="w-4 h-4 text-sky-600" /><h2 className="text-sm font-bold text-slate-900">Place lookup</h2></div>
        <div className="grid md:grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <label className="text-[11px] font-bold text-slate-700">Latitude<input value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" className={field} aria-label="latitude" /></label>
          <label className="text-[11px] font-bold text-slate-700">Longitude<input value={lon} onChange={(e) => setLon(e.target.value)} inputMode="decimal" className={field} aria-label="longitude" /></label>
          <button onClick={() => void lookup()} className="px-3 py-1.5 rounded bg-sky-600 text-white text-xs font-bold">Locate</button>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        {place && (
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {[['RF25 cell (row, col)', `${place.cell.row}, ${place.cell.col}`], ['Cell centre', `${place.cell.lat}, ${place.cell.lon}`],
              ['Land or sea', place.is_land === null ? 'unknown' : place.is_land ? 'land' : 'sea'], ['Client region', place.client_region ?? 'none (sea)']].map(([k, v]) => (
              <div key={k} className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-3 py-2"><dt className="text-[10px] uppercase font-mono text-slate-500">{k}</dt><dd className="font-mono font-bold">{String(v)}</dd></div>))}
          </dl>)}
        {place && <p className="text-[10px] text-slate-500">IMD sub-division: {place.imd_subdivision.status.replace('_', ' ')} (NOT IMPLEMENTED in the platform). The RF25 grid is 0.25 degrees; a cell is about 28 km across.</p>}
      </Panel>

      <Panel className="p-4 space-y-2">
        <div className="flex items-center gap-3 flex-wrap">
          <h2 className="text-sm font-bold text-slate-900">Weather Union gauges</h2>
          <select value={city} onChange={(e) => setCity(e.target.value)} className="text-xs border border-[#D3DCE7] rounded px-2 py-1" aria-label="city">
            {cities.map((c) => <option key={c} value={c}>{c}</option>)}</select>
          <span className="text-[10px] font-mono text-slate-500">{count} stations in the published catalogue · a static list, no reading</span>
        </div>
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead className="text-left bg-[#EDF1F7] sticky top-0"><tr><th className="px-2">Place</th><th className="px-2">Device</th><th className="px-2">Lat, lon</th><th className="px-2">RF25 cell</th><th className="px-2">Land</th></tr></thead>
            <tbody>{gauges.map((g) => (
              <tr key={g.station_id} onClick={() => { setLat(String(g.latitude)); setLon(String(g.longitude)); void lookup(String(g.latitude), String(g.longitude)); }}
                  className="border-t border-[#E2E8F2] cursor-pointer hover:bg-[#F4F6FA]">
                <td className="px-2 font-bold">{g.place}<div className="font-mono text-[10px] text-slate-400">{g.station_id}</div></td><td className="px-2">{g.device}</td>
                <td className="px-2 font-mono">{g.latitude.toFixed(4)}, {g.longitude.toFixed(4)}</td><td className="px-2 font-mono">{g.cell ? `${g.cell.row}, ${g.cell.col}` : '—'}</td>
                <td className="px-2">{g.is_land === null ? '?' : g.is_land ? 'land' : 'sea'}</td></tr>))}</tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
