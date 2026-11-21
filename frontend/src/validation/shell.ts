// Pure helpers of the station-first shell: the pages and their hash routes, the keys 1-8, the station list (the gauge catalogue plus
// stations that only exist in an uploaded file), search and grouping for the picker, and the one selected-station store.
// No React in here, so all of it is tested without a browser.
import type { GaugeStation, StationCycle } from './types';

export type PageId = 'overview' | 'live' | 'alerts' | 'events' | 'explorer' | 'review' | 'injector' | 'agent' | 'import' | 'settings';

/** The rail, in order. Keys 1 to 8 follow this order. Import and Settings live in the header, not here. */
export const RAIL: { id: PageId; label: string }[] = [
  { id: 'overview', label: 'Overview' }, { id: 'live', label: 'Live' }, { id: 'alerts', label: 'Alerts' }, { id: 'events', label: 'Events' },
  { id: 'explorer', label: 'Explorer' }, { id: 'review', label: 'Review' }, { id: 'injector', label: 'Injector' }, { id: 'agent', label: 'Agent' },
];
const HEADER_PAGES: PageId[] = ['import', 'settings'];
const ALL_PAGES = new Set<string>([...RAIL.map((p) => p.id), ...HEADER_PAGES]);

/** `#/app` is the Overview, `#/app/live` the Live page, and so on. An unknown page falls back to the Overview. */
export function pageFromHash(hash: string): PageId {
  const m = /^#\/app\/([a-z]+)/.exec(hash);
  return m && ALL_PAGES.has(m[1]) ? (m[1] as PageId) : 'overview';
}
export const hashForPage = (p: PageId): string => (p === 'overview' ? '#/app' : `#/app/${p}`);

/** Key 1 to 8 opens that rail page; anything else (including 0 and 9) opens nothing. */
export function pageForKey(key: string): PageId | null {
  if (!/^[1-8]$/.test(key)) return null;
  return RAIL[Number(key) - 1].id;
}

/** Older pages ask to go to a step by its old name; this maps those names onto the new pages. */
export function pageForTab(tab: string): PageId {
  switch (tab) {
    case 'live': return 'live';
    case 'run': return 'events';
    case 'review': return 'review';
    case 'runs': return 'import';
    case 'settings': return 'settings';
    default: return 'overview';                  // overview, stations, insights
  }
}

/** A page named by its id (the restored views pass "live", "alerts" and so on); an unknown name opens the Overview. */
export const pageFromId = (id: string): PageId => (ALL_PAGES.has(id) ? (id as PageId) : 'overview');

export interface StationEntry { id: string; place: string; city: string; source: 'catalogue' | 'upload' | 'stream' }
export const UPLOAD_GROUP = 'From uploaded files';
export const STREAM_GROUP = 'Other stations';

/** A station the stream API lists (GET /api/stations): id, name, optional position. */
export interface StreamStationInfo { station_id: string; name: string; latitude?: number | null; longitude?: number | null }

/** The 580 catalogue gauges, then any station that only exists in stored rows (an uploaded file), then stations only the stream API
 *  lists (the simulator's, an ESP32's), once each. */
export function buildStationList(gauges: GaugeStation[], cycle: Pick<StationCycle, 'station_id' | 'place' | 'city'>[], streamStations: StreamStationInfo[] = []): StationEntry[] {
  const out: StationEntry[] = gauges.map((g) => ({ id: g.station_id, place: g.place, city: g.city, source: 'catalogue' as const }));
  const known = new Set(out.map((s) => s.id));
  for (const c of cycle) {
    if (known.has(c.station_id)) continue;
    known.add(c.station_id);
    out.push({ id: c.station_id, place: c.place ?? c.station_id, city: c.city ?? UPLOAD_GROUP, source: 'upload' });
  }
  for (const s of streamStations) {
    if (known.has(s.station_id)) continue;
    known.add(s.station_id);
    out.push({ id: s.station_id, place: s.name || s.station_id, city: STREAM_GROUP, source: 'stream' });
  }
  return out.sort((a, b) => a.city.localeCompare(b.city) || a.place.localeCompare(b.place) || a.id.localeCompare(b.id));
}

/** Every word typed must appear in the place, the city or the id (case ignored). A city name limits the list to that city. */
export function filterStations(list: StationEntry[], query: string, city = ''): StationEntry[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return list.filter((s) => {
    if (city && s.city !== city) return false;
    const hay = `${s.place} ${s.city} ${s.id}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}

export function groupByCity(list: StationEntry[]): { city: string; stations: StationEntry[] }[] {
  const groups: { city: string; stations: StationEntry[] }[] = [];
  for (const s of list) {
    const last = groups[groups.length - 1];
    if (last && last.city === s.city) last.stations.push(s); else groups.push({ city: s.city, stations: [s] });
  }
  return groups;
}

export const stationTitle = (s: StationEntry | undefined, id: string | null): string => (s ? s.place : id ?? 'No station selected');

/** Keep the highlighted picker row inside the list as the arrow keys move it. */
export const moveActive = (current: number, delta: number, length: number): number => (length === 0 ? -1 : Math.min(length - 1, Math.max(0, current + delta)));

// ---- the one selected station -----------------------------------------------------------------------------------------------
export const SELECTED_KEY = 'datamend-selected-station';
export interface KeyValueStorage { getItem(k: string): string | null; setItem(k: string, v: string): void; removeItem(k: string): void }
export interface SelectionStore { get(): string | null; set(id: string | null): void; subscribe(fn: () => void): () => void }

/** Holds `selectedStationId` for the whole shell. Setting the same value again does not notify; a blank id means "none". */
export function createSelectionStore(storage?: KeyValueStorage): SelectionStore {
  let current: string | null = storage?.getItem(SELECTED_KEY) || null;
  const listeners = new Set<() => void>();
  return {
    get: () => current,
    set(id) {
      const next = id && id.trim() ? id : null;
      if (next === current) return;
      current = next;
      if (storage) { if (next) storage.setItem(SELECTED_KEY, next); else storage.removeItem(SELECTED_KEY); }
      listeners.forEach((l) => l());
    },
    subscribe(fn) { listeners.add(fn); return () => { listeners.delete(fn); }; },
  };
}

/** A row opened from the Alerts list (or a run opened from Overview or Import) for the Events page to show. */
export interface EventFocus { runId: number; rowId: number | null }
