// The global station picker in the header: a button showing the selected station's place and city, and a searchable list grouped by city.
import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, MapPin, Search, X } from 'lucide-react';
import { useStation } from './StationContext';
import { filterStations, groupByCity, moveActive } from './shell';
import { OPEN_PICKER_EVENT } from './guide';

export function StationPicker() {
  const { stationId, select, stations, entry, loading, error } = useStation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [city, setCity] = useState('');
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const cities = useMemo(() => [...new Set(stations.map((s) => s.city))], [stations]);
  const shown = useMemo(() => filterStations(stations, query, city), [stations, query, city]);
  const groups = useMemo(() => groupByCity(shown), [shown]);
  useEffect(() => { setActive(0); }, [query, city]);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);
  useEffect(() => {                                    // the Start here guide and the empty states open the picker from outside
    const on = () => setOpen(true);
    window.addEventListener(OPEN_PICKER_EVENT, on);
    return () => window.removeEventListener(OPEN_PICKER_EVENT, on);
  }, []);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', away);
    return () => document.removeEventListener('mousedown', away);
  }, [open]);
  useEffect(() => { document.getElementById(`pick-${active}`)?.scrollIntoView({ block: 'nearest' }); }, [active, open]);

  const choose = (id: string | null) => { select(id); setOpen(false); setQuery(''); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => moveActive(a, 1, shown.length)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => moveActive(a, -1, shown.length)); }
    else if (e.key === 'Enter' && shown[active]) { e.preventDefault(); choose(shown[active].id); }
    else if (e.key === 'Escape') setOpen(false);
  };

  let index = -1;
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="listbox" aria-expanded={open} aria-label="Station"
              className="flex items-center gap-2 h-8 px-3 bg-[#F4F6FA] hover:bg-[#EDF1F7] border border-sky-500/50 rounded-lg text-xs font-mono shadow-sm min-w-[13rem] max-w-[22rem] text-left transition-all">
        <MapPin className="w-3.5 h-3.5 text-sky-600 shrink-0" />
        <span className="truncate flex-1">
          {stationId
            ? <><b className="text-sky-800">{entry?.place ?? stationId}</b>{entry && <span className="text-slate-500"> · {entry.city}</span>}</>
            : <span className="text-slate-500">{loading ? 'Loading stations…' : `Select a station (${stations.length})`}</span>}
        </span>
        <ChevronDown className="w-3.5 h-3.5 text-slate-500 shrink-0" />
      </button>
      {open && (
        <div className="absolute left-0 top-full mt-1 w-[26rem] max-w-[90vw] rounded-lg border border-[#D3DCE7] bg-white shadow-lg z-50">
          <div className="p-2 border-b border-[#E2E8F2] space-y-1.5">
            <div className="flex items-center gap-1.5 border border-[#D3DCE7] rounded px-2">
              <Search className="w-3.5 h-3.5 text-slate-400" />
              <input ref={input} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={onKey} placeholder="Search place, city or id"
                     aria-label="Search stations" className="flex-1 text-xs py-1.5 outline-none bg-transparent" />
            </div>
            <div className="flex items-center gap-2">
              <select value={city} onChange={(e) => setCity(e.target.value)} aria-label="City" className="flex-1 text-[11px] border border-[#D3DCE7] rounded px-1 py-1 bg-white">
                <option value="">All cities ({cities.length})</option>
                {cities.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <span className="text-[10px] font-mono text-slate-500">{shown.length} of {stations.length}</span>
              {stationId && <button onClick={() => choose(null)} className="text-[11px] text-slate-600 flex items-center gap-0.5" aria-label="Clear the station"><X className="w-3 h-3" />Clear</button>}
            </div>
          </div>
          <ul role="listbox" aria-label="Stations" className="max-h-80 overflow-y-auto py-1">
            {error && <li className="px-3 py-2 text-[11px] text-red-700">Could not load the catalogue: {error}</li>}
            {shown.length === 0 && !error && <li className="px-3 py-2 text-xs text-slate-500">{stations.length === 0 ? 'No stations loaded.' : 'No station matches.'}</li>}
            {groups.map((g) => (
              <li key={g.city} role="presentation">
                <div className="px-3 pt-1.5 pb-0.5 text-[10px] font-mono uppercase text-slate-500 sticky top-0 bg-white">{g.city} · {g.stations.length}</div>
                <ul role="group">
                  {g.stations.map((s) => {
                    index += 1;
                    const i = index;
                    return (
                      <li key={s.id} id={`pick-${i}`} role="option" aria-selected={s.id === stationId} onClick={() => choose(s.id)} onMouseEnter={() => setActive(i)}
                          className={`px-3 py-1 text-xs cursor-pointer flex items-baseline gap-2 ${i === active ? 'bg-sky-500/15' : ''} ${s.id === stationId ? 'font-bold' : ''}`}>
                        <span className="truncate">{s.place}</span><span className="ml-auto font-mono text-[10px] text-slate-400 shrink-0">{s.id}</span>
                      </li>);
                  })}
                </ul>
              </li>))}
          </ul>
        </div>)}
    </div>
  );
}
