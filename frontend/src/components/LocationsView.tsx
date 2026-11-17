import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { MapPin, Plus, RefreshCw, Trash2 } from 'lucide-react';
import {
  createLocation,
  deleteLocation,
  fetchLocations,
  fetchLocationSeries,
  fetchLocationStatus,
} from '../services/api';
import {
  LocationCellStatus,
  LocationItem,
  LocationSeriesResponse,
  LocationStatusResponse,
} from '../types';
import { StatusBadge, StatusBadgeVariant } from '../design-system/components/StatusBadge';

type VarKey = 'temperature' | 'humidity' | 'pressure' | 'precipitation';

const VARS: { key: VarKey; label: string; short: string; unit: string }[] = [
  { key: 'temperature', label: 'Temperature', short: 'Temp', unit: '°C' },
  { key: 'humidity', label: 'Humidity', short: 'RH', unit: '%' },
  { key: 'pressure', label: 'Pressure', short: 'Pres', unit: 'hPa' },
  { key: 'precipitation', label: 'Rainfall', short: 'Rain', unit: 'mm/h' },
];

const LABELS: Record<string, { text: string; variant: StatusBadgeVariant; help: string }> = {
  consistent: { text: 'Consistent', variant: 'nominal', help: 'No unusual weather and no data-quality findings.' },
  genuine_event_likely: { text: 'Likely real event', variant: 'info', help: 'Unusual weather seen by the cells of this place together.' },
  possible_data_fault: { text: 'Possible data fault', variant: 'critical', help: 'A data-quality check failed, or this cell disagrees with its neighbours.' },
  uncertain: { text: 'Uncertain', variant: 'warning', help: 'Unusual weather, but too few cells agree to decide.' },
};

const LEVEL_VARIANT: Record<string, StatusBadgeVariant> = {
  normal: 'nominal',
  dry: 'neutral',
  unusual: 'warning',
  heavy: 'warning',
  extreme: 'critical',
  very_heavy: 'critical',
  unavailable: 'neutral',
};

const fmt = (v: number | null | undefined, d = 1) => (v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(d));

function AnomalyRow({ label, a, unit }: { label: string; a: any; unit: string }) {
  if (!a) return null;
  const rain = 'wet_p95' in a;
  return (
    <div className="py-1 text-[11px]">
      <div className="flex items-center justify-between gap-2">
        <span className="text-slate-700 font-semibold">{label}</span>
        <StatusBadge size="sm" label={String(a.level).replace('_', ' ')} variant={LEVEL_VARIANT[a.level] || 'neutral'} />
      </div>
      {a.value !== null && a.value !== undefined && (
        <div className="font-mono text-slate-500 leading-snug">
          {fmt(a.value, 1)} {unit}
          {!rain && a.normal !== undefined && <> · normal {fmt(a.normal)} · z {a.z > 0 ? '+' : ''}{fmt(a.z)}</>}
          {rain && a.wet_p95 != null && <> · heavy from {fmt(a.wet_p95)} mm</>}
        </div>
      )}
    </div>
  );
}

function CellCard({ c, selected, onSelect }: { c: LocationCellStatus; selected: boolean; onSelect: () => void }) {
  const lab = c.classification ? LABELS[c.classification.label] : undefined;
  const w = c.weather_anomaly;
  return (
    <div
      onClick={onSelect}
      className={`cursor-pointer rounded-xl border bg-white p-3 shadow-sm transition-all ${selected ? 'border-sky-500 ring-2 ring-sky-200' : 'border-[#D3DCE7] hover:border-sky-300'}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-mono font-bold text-slate-800">{c.cell.lat.toFixed(2)}°N {c.cell.lon.toFixed(2)}°E</div>
          <div className="mt-1 flex flex-wrap gap-1">
            <StatusBadge size="sm" variant="neutral" label={c.cell.is_land === false ? 'sea' : c.cell.is_land ? 'land' : 'land: unknown'} />
            {c.cell.held_out && <StatusBadge size="sm" variant="info" label={`region ${c.cell.client}: unseen by training`} />}
          </div>
        </div>
        {lab && <StatusBadge label={lab.text} variant={lab.variant} />}
      </div>

      {c.status !== 'ok' ? (
        <div className="mt-3 text-xs text-slate-600">{c.status}</div>
      ) : (
        <>
          <div className="mt-3 grid grid-cols-4 gap-1 text-center">
            {VARS.map((v) => {
              const cur: any = c.current;
              const val = v.key === 'precipitation' ? cur?.precipitation_1h : cur?.[v.key];
              return (
                <div key={v.key} className="rounded-lg bg-[#F4F6FA] px-1 py-1.5">
                  <div className="text-sm font-mono font-bold text-slate-900">{fmt(val, v.key === 'pressure' ? 0 : 1)}</div>
                  <div className="text-[9px] text-slate-500">{v.short} {v.unit}</div>
                </div>
              );
            })}
          </div>
          <div className="mt-1 text-[10px] text-slate-500 font-mono">
            at {c.current?.time ?? '—'} UTC, grid point {c.grid_point ? `${c.grid_point.lat.toFixed(2)}, ${c.grid_point.lon.toFixed(2)}` : '—'}
          </div>

          <div className="mt-3 border-t border-[#EDF1F7] pt-2">
            <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">
              Weather anomaly {w?.status === 'ok' ? `(${w.date}, vs ${w.normals_period} normal)` : ''}
            </div>
            {w?.status === 'ok' ? (
              <>
                <AnomalyRow label="Temperature" a={w.temperature} unit="°C" />
                <AnomalyRow label="Humidity" a={w.humidity} unit="%" />
                <AnomalyRow label="Pressure" a={w.pressure} unit="hPa" />
                <AnomalyRow label="Rainfall (day)" a={w.precipitation} unit="mm" />
              </>
            ) : (
              <div className="text-[11px] text-slate-500">Unavailable: {w?.reason}</div>
            )}
          </div>

          <div className="mt-2 border-t border-[#EDF1F7] pt-2">
            <div className="text-[10px] font-bold uppercase tracking-wide text-slate-500">Data-QC ({c.qc?.method})</div>
            {c.classification?.reasons.map((r, i) => (
              <div key={i} className="text-[11px] text-slate-700 leading-snug">• {r}</div>
            ))}
            <div className="mt-1 text-[10px] text-slate-500">
              Trained model: {c.model?.status === 'ok' ? `${c.model.model} ${JSON.stringify(c.model.scores)}` : `not available (${c.model?.reason})`}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function LocationsView() {
  const [locations, setLocations] = useState<LocationItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [status, setStatus] = useState<LocationStatusResponse | null>(null);
  const [series, setSeries] = useState<LocationSeriesResponse | null>(null);
  const [selectedCell, setSelectedCell] = useState<string | null>(null);
  const [variable, setVariable] = useState<VarKey>('temperature');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({ name: '', latitude: '', longitude: '', radius: '15' });
  const [adding, setAdding] = useState(false);

  const loadLocations = useCallback(async (selectFirst = false) => {
    try {
      const res = await fetchLocations();
      setLocations(res.items);
      if (selectFirst && res.items.length) setSelectedId((prev) => prev ?? res.items[0].id);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  const loadStatus = useCallback(async (id: number) => {
    setLoading(true);
    setError(null);
    try {
      const [st, se] = await Promise.all([fetchLocationStatus(id), fetchLocationSeries(id, 7)]);
      setStatus(st);
      setSeries(se);
      setSelectedCell((prev) => prev ?? (st.cells[0] ? `${st.cells[0].cell.row}_${st.cells[0].cell.col}` : null));
    } catch (e: any) {
      setError(e.message);
      setStatus(null);
      setSeries(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLocations(true);
  }, [loadLocations]);

  useEffect(() => {
    if (selectedId !== null) {
      setSelectedCell(null);
      loadStatus(selectedId);
    }
  }, [selectedId, loadStatus]);

  const onAdd = async () => {
    setAdding(true);
    setError(null);
    try {
      const body: any = { name: form.name.trim(), radius_km: Number(form.radius) || 15 };
      if (form.latitude.trim() !== '' || form.longitude.trim() !== '') {
        body.latitude = Number(form.latitude);
        body.longitude = Number(form.longitude);
      }
      const loc = await createLocation(body);
      setForm({ name: '', latitude: '', longitude: '', radius: form.radius });
      await loadLocations();
      setSelectedId(loc.id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setAdding(false);
    }
  };

  const onDelete = async (id: number) => {
    await deleteLocation(id).catch((e) => setError(e.message));
    if (selectedId === id) {
      setSelectedId(null);
      setStatus(null);
      setSeries(null);
    }
    await loadLocations(true);
  };

  // Cells laid out like a map: north at the top, west on the left.
  const layout = useMemo(() => {
    if (!status) return { cols: 1, ordered: [] as LocationCellStatus[] };
    const lons = Array.from(new Set(status.cells.map((c) => c.cell.lon))).sort((a, b) => a - b);
    const ordered = [...status.cells].sort((a, b) => b.cell.lat - a.cell.lat || a.cell.lon - b.cell.lon);
    return { cols: Math.max(1, Math.min(lons.length, 4)), ordered };
  }, [status]);

  const chartData = useMemo(() => {
    const sc = series?.cells.find((c) => `${c.cell.row}_${c.cell.col}` === selectedCell);
    if (!sc) return [];
    return sc.time.map((t, i) => ({ t: t.replace('T', ' ').slice(5, 16), v: (sc as any)[variable][i] as number | null }));
  }, [series, selectedCell, variable]);

  const norm = selectedCell && series ? series.normals_today[selectedCell]?.[variable] : undefined;
  const varInfo = VARS.find((v) => v.key === variable)!;

  return (
    <div className="flex flex-col lg:flex-row gap-4">
      <aside className="lg:w-72 shrink-0 space-y-3">
        <div className="rounded-xl border border-[#D3DCE7] bg-white p-3 shadow-sm">
          <div className="text-xs font-bold text-slate-800 flex items-center gap-2 mb-2">
            <MapPin className="w-4 h-4 text-sky-600" /> Locations
          </div>
          <div className="space-y-1">
            {locations.map((l) => (
              <div
                key={l.id}
                onClick={() => setSelectedId(l.id)}
                className={`flex items-center justify-between rounded-lg px-2 py-1.5 cursor-pointer text-xs ${selectedId === l.id ? 'bg-sky-50 border border-sky-300' : 'hover:bg-[#EDF1F7] border border-transparent'}`}
              >
                <span className="truncate">
                  <span className="font-semibold text-slate-800">{l.name}</span>
                  <span className="text-slate-500 font-mono"> · {l.cells.length} cells</span>
                </span>
                <button
                  title="Remove location"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(l.id);
                  }}
                  className="text-slate-400 hover:text-red-600"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {locations.length === 0 && <div className="text-xs text-slate-500">No locations yet.</div>}
          </div>
        </div>

        <div className="rounded-xl border border-[#D3DCE7] bg-white p-3 shadow-sm space-y-2">
          <div className="text-xs font-bold text-slate-800">Add a location</div>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Place name (e.g. Pune)"
            className="w-full rounded-md border border-[#D3DCE7] px-2 py-1.5 text-xs"
          />
          <div className="grid grid-cols-2 gap-2">
            <input value={form.latitude} onChange={(e) => setForm({ ...form, latitude: e.target.value })} placeholder="Latitude (optional)" className="rounded-md border border-[#D3DCE7] px-2 py-1.5 text-xs" />
            <input value={form.longitude} onChange={(e) => setForm({ ...form, longitude: e.target.value })} placeholder="Longitude (optional)" className="rounded-md border border-[#D3DCE7] px-2 py-1.5 text-xs" />
          </div>
          <div className="flex items-center gap-2 text-xs text-slate-600">
            Radius
            <input value={form.radius} onChange={(e) => setForm({ ...form, radius: e.target.value })} className="w-16 rounded-md border border-[#D3DCE7] px-2 py-1 text-xs" /> km
          </div>
          <button
            disabled={adding || form.name.trim() === ''}
            onClick={onAdd}
            className="w-full flex items-center justify-center gap-1.5 rounded-md bg-sky-500 text-white text-xs font-bold py-1.5 disabled:opacity-50"
          >
            <Plus className="w-3.5 h-3.5" /> {adding ? 'Adding…' : 'Add'}
          </button>
          <div className="text-[10px] text-slate-500 leading-snug">
            Grid: 0.25° cells (about 28 km), India box 6.5–38.5°N, 66.5–100°E. Give a name, or coordinates for exact placement.
          </div>
        </div>
      </aside>

      <section className="flex-1 min-w-0 space-y-4">
        {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
        {status && (
          <>
            <div className="rounded-xl border border-[#D3DCE7] bg-white p-3 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="text-base font-bold text-slate-900">{status.location.name}</div>
                  <div className="text-[11px] text-slate-500 font-mono">
                    {status.location.latitude.toFixed(3)}°N {status.location.longitude.toFixed(3)}°E · {status.location.n_cells} cells · as of {status.as_of.slice(0, 16).replace('T', ' ')} UTC
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {status.stale && <StatusBadge variant="warning" label="stale: service unreachable" />}
                  {Object.entries(status.summary).map(([k, n]) => (
                    <StatusBadge key={k} variant={LABELS[k]?.variant || 'neutral'} label={`${n} ${LABELS[k]?.text || k}`} />
                  ))}
                  <button onClick={() => selectedId !== null && loadStatus(selectedId)} className="text-slate-500 hover:text-sky-600" title="Refresh">
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                  </button>
                </div>
              </div>
              <details className="mt-2 text-[11px] text-slate-600">
                <summary className="cursor-pointer font-semibold text-slate-700">What these values are, and what they are not</summary>
                <ul className="list-disc ml-5 mt-1 space-y-0.5">
                  <li>Source: {status.source.provider}, {status.source.kind}.</li>
                  {status.limitations.map((l, i) => (
                    <li key={i}>{l}</li>
                  ))}
                </ul>
              </details>
            </div>

            <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${layout.cols}, minmax(0, 1fr))` }}>
              {layout.ordered.map((c) => {
                const key = `${c.cell.row}_${c.cell.col}`;
                return <CellCard key={key} c={c} selected={selectedCell === key} onSelect={() => setSelectedCell(key)} />;
              })}
            </div>

            <div className="rounded-xl border border-[#D3DCE7] bg-white p-3 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div className="text-xs font-bold text-slate-800">
                  Last 7 days, hourly{selectedCell ? ` — cell ${selectedCell.replace('_', ',')}` : ''}
                </div>
                <div className="flex gap-1">
                  {VARS.map((v) => (
                    <button
                      key={v.key}
                      onClick={() => setVariable(v.key)}
                      className={`px-2 py-1 rounded-md text-[11px] font-semibold ${variable === v.key ? 'bg-sky-500 text-white' : 'bg-[#EDF1F7] text-slate-600'}`}
                    >
                      {v.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 5, right: 12, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                    <XAxis dataKey="t" tick={{ fontSize: 10 }} interval={Math.max(1, Math.floor(chartData.length / 6))} />
                    <YAxis tick={{ fontSize: 10 }} domain={['auto', 'auto']} unit={` ${varInfo.unit}`} width={64} />
                    <Tooltip />
                    {norm && variable !== 'precipitation' && (
                      <ReferenceArea y1={norm.mean - 2 * norm.sd} y2={norm.mean + 2 * norm.sd} fill="#0ea5e9" fillOpacity={0.08} />
                    )}
                    {norm && variable !== 'precipitation' && <ReferenceLine y={norm.mean} stroke="#0ea5e9" strokeDasharray="4 4" />}
                    <Line type="monotone" dataKey="v" stroke="#0f172a" dot={false} strokeWidth={1.5} connectNulls={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              {norm && variable !== 'precipitation' && (
                <div className="text-[10px] text-slate-500 mt-1">
                  Blue band: today's normal ± 2 standard deviations of the daily mean (1991–2020). Hourly values swing around it through the day; the band is a reference for the daily mean, not a limit for each hour.
                </div>
              )}
            </div>
          </>
        )}
        {!status && !error && <div className="text-xs text-slate-500">{loading ? 'Loading…' : 'Select or add a location.'}</div>}
      </section>
    </div>
  );
}
