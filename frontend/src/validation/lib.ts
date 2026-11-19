// Pure helpers of the validation dashboard (unit-tested in lib.test.ts). No React, no network.
import type { Completeness, Headline, SeriesPoint, SettingsState, SettingsUpdate, Verdict } from './types';

export const PAGE_SIZE = 50;

export const VERDICT_COLOR: Record<Verdict, string> = { OK: '#10B981', SUSPECT: '#EF4444', UNCERTAIN: '#F59E0B', NO_DATA: '#94A3B8' };

export function pct(v: number | null | undefined): string {
  return v === null || v === undefined ? 'n/a' : `${(v * 100).toFixed(v > 0 && v < 0.001 ? 2 : 1)}%`;
}

export function completenessText(c: Completeness | undefined): string {
  if (!c) return 'n/a';
  if (c.value === null) return c.reason ?? 'not computed';
  return `${pct(c.value)} (${c.n} of ${c.expected} expected, derived)`;
}

/** Query string for the server-side page of flagged rows. Empty filters are omitted. */
export function rowsQuery(opts: { page: number; verdict?: Verdict | 'ALL'; check?: string; station?: string }): string {
  const q = new URLSearchParams();
  q.set('page', String(Math.max(1, Math.floor(opts.page))));
  q.set('page_size', String(PAGE_SIZE));
  if (opts.verdict && opts.verdict !== 'ALL') q.set('verdict', opts.verdict);
  if (opts.check) q.set('check', opts.check);
  if (opts.station) q.set('station', opts.station);
  return q.toString();
}

/** Data Explorer query: every row (not only flagged), in time order, server-side pages of 50, with optional filters. */
export function explorerQuery(o: { page: number; station?: string; verdict?: Verdict | 'ALL'; check?: string; from?: string; to?: string }): string {
  const q = new URLSearchParams({ scope: 'all', sort: 'time', page: String(Math.max(1, Math.floor(o.page))), page_size: String(PAGE_SIZE) });
  if (o.station) q.set('station', o.station);
  if (o.verdict && o.verdict !== 'ALL') q.set('verdict', o.verdict);
  if (o.check) q.set('check', o.check);
  if (o.from) q.set('time_from', o.from);
  if (o.to) q.set('time_to', o.to);
  return q.toString();
}

/** Review queue query across runs. status unreviewed is the default work list. */
export function queueQuery(o: { page: number; status: 'unreviewed' | 'reviewed' | 'all'; verdict?: 'SUSPECT' | 'UNCERTAIN' | ''; check?: string; runId?: number | null; synthetic?: 'all' | 'synthetic' | 'real'; station?: string }): string {
  const q = new URLSearchParams({ status: o.status, page: String(Math.max(1, Math.floor(o.page))), page_size: String(PAGE_SIZE) });
  if (o.verdict) q.set('verdict', o.verdict);
  if (o.check) q.set('check', o.check);
  if (o.station) q.set('station', o.station);
  if (o.runId) q.set('run_id', String(o.runId));
  if (o.synthetic === 'synthetic') q.set('synthetic', 'true');
  if (o.synthetic === 'real') q.set('synthetic', 'false');
  return q.toString();
}

/** Every check in the catalogue (backend/app/validation/checks.py), for filters. */
export const ALL_CHECKS = [
  'negative_value', 'intensity_above_ceiling', 'counter_jump', 'counter_reset', 'frozen_intensity', 'intensity_counter_mismatch',
  'neighbour_isolated_wet', 'neighbour_isolated_dry', 'impossible_value', 'repeated_value', 'climatology_upper_tail', 'duplicate_row',
];

export const DECISION_LABEL: Record<string, string> = {
  confirmed_fault: 'Confirmed fault', false_alarm: 'False alarm', genuine_extreme: 'Genuine extreme', needs_followup: 'Needs follow-up',
};

export function timeMs(t: string): number {
  return Date.parse(t.length === 10 ? `${t}T00:00:00Z` : t);
}

/** Horizontal position 0..1 of a time inside [t0, t1] (0.5 when the range is empty), used by the check lanes. */
export function lanePosition(t: string, t0: string, t1: string): number {
  const a = timeMs(t0), b = timeMs(t1), x = timeMs(t);
  if (!Number.isFinite(a) || !Number.isFinite(b) || !Number.isFinite(x) || b <= a) return 0.5;
  return Math.min(1, Math.max(0, (x - a) / (b - a)));
}

export interface LaneMark { id: number; check: string; x: number; verdict: Verdict }

/** One lane per check that fired on this station, ticks positioned by time; ordered by how many ticks the check has. */
export function buildLanes(flagged: SeriesPoint[], t0: string, t1: string): { check: string; marks: LaneMark[] }[] {
  const by = new Map<string, LaneMark[]>();
  for (const f of flagged) {
    for (const c of f.checks ?? []) {
      const arr = by.get(c) ?? [];
      arr.push({ id: f.id, check: c, x: lanePosition(f.time, t0, t1), verdict: f.verdict });
      by.set(c, arr);
    }
  }
  return [...by.entries()].map(([check, marks]) => ({ check, marks })).sort((a, b) => b.marks.length - a.marks.length || a.check.localeCompare(b.check));
}

/** Chart rows: a numeric time axis, so markers of rows the server dropped from the line still sit at the right time. */
export function chartData(points: SeriesPoint[]): { t: number; intensity: number | null; accumulation: number | null; mm: number | null }[] {
  return points.map((p) => ({ t: timeMs(p.time), intensity: p.intensity, accumulation: p.accumulation, mm: p.mm }));
}

export function markerY(p: SeriesPoint): number {
  return p.intensity ?? p.mm ?? 0;
}

export interface SettingsForm {
  apiKey: string; city: string; intervalMinutes: string; mode: string; narratorUrl: string; narratorToken: string;
}

/** The settings request: only what the user changed. Secrets are sent only when typed (an empty box means "keep"); the interval is
 *  entered in minutes and sent in seconds. Returns null when nothing changed. */
export function buildSettingsUpdate(form: SettingsForm, current: SettingsState, clear: string[] = []): SettingsUpdate | null {
  const u: SettingsUpdate = {};
  if (form.apiKey.trim()) u.weather_union_api_key = form.apiKey.trim();
  if (form.narratorToken.trim()) u.narrator_token = form.narratorToken.trim();
  if (form.city && form.city !== current.weather_union.city) u.weather_union_city = form.city;
  if (form.mode && form.mode !== current.weather_union.accumulation_mode) u.weather_union_accumulation_mode = form.mode;
  const minutes = Number(form.intervalMinutes);
  if (form.intervalMinutes.trim() !== '' && Number.isFinite(minutes) && minutes * 60 !== current.weather_union.poll_interval_seconds) {
    u.weather_union_poll_interval_seconds = minutes * 60;
  }
  const url = form.narratorUrl.trim();
  if (url && url !== current.narrator.url) u.narrator_url = url;
  if (clear.length) u.clear = clear;
  return Object.keys(u).length ? u : null;
}

export function headlineLine(h: Headline | null | undefined): string {
  if (!h) return 'no headline';
  return `${h.rows} rows · ${h.stations} station(s) · SUSPECT ${pct(h.share_suspect)} · UNCERTAIN ${pct(h.share_uncertain)} · NO_DATA ${pct(h.share_no_data)}`;
}

/** Plain-text guard for generated text: the UI only ever renders it as text, never as HTML. */
export function asPlainText(s: unknown): string {
  return typeof s === 'string' ? s : '';
}

// ---------------------------------------------------------------- station map (flat, equirectangular) and the check -> flag -> audit cycle
export interface MapView { cx: number; cy: number; scale: number }          // centre latitude and longitude; scale = pixels per degree
export const INDIA_BOUNDS = { lonMin: 66, lonMax: 100, latMin: 5.5, latMax: 38.5 };
export const MIN_SCALE = 4;
export const MAX_SCALE = 400;

/** The view that shows all of India with a small margin. */
export function fitView(w: number, h: number): MapView {
  const b = INDIA_BOUNDS;
  const scale = Math.min(w / (b.lonMax - b.lonMin), h / (b.latMax - b.latMin)) * 0.96;
  return { cx: (b.lonMin + b.lonMax) / 2, cy: (b.latMin + b.latMax) / 2, scale: Math.max(MIN_SCALE, scale) };
}
export function project(lat: number, lon: number, v: MapView, w: number, h: number): { x: number; y: number } {
  return { x: w / 2 + (lon - v.cx) * v.scale, y: h / 2 - (lat - v.cy) * v.scale };
}
export function unproject(x: number, y: number, v: MapView, w: number, h: number): { lat: number; lon: number } {
  return { lat: v.cy - (y - h / 2) / v.scale, lon: v.cx + (x - w / 2) / v.scale };
}
/** Zoom by ``factor`` keeping the geographic point under (x, y) fixed. The scale is clamped. */
export function zoomAt(v: MapView, factor: number, x: number, y: number, w: number, h: number): MapView {
  const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale * factor));
  const p = unproject(x, y, v, w, h);
  return { scale, cx: p.lon - (x - w / 2) / scale, cy: p.lat + (y - h / 2) / scale };
}
/** Pan by a pixel drag. */
export function panBy(v: MapView, dx: number, dy: number): MapView {
  return { ...v, cx: v.cx - dx / v.scale, cy: v.cy + dy / v.scale };
}
/** The closest point to (x, y) within ``maxPx`` pixels, or null. Ties go to the earlier point. */
export function nearestPoint<T extends { x: number; y: number }>(points: T[], x: number, y: number, maxPx: number): T | null {
  let best: T | null = null;
  let bd = maxPx * maxPx;
  for (const p of points) {
    const d = (p.x - x) ** 2 + (p.y - y) ** 2;
    if (d <= bd && (best === null || d < bd)) { best = p; bd = d; }
  }
  return best;
}

// Eight calm, rain-toned tints (blues, greens and sand; no violet), distinct enough to tell regions apart on a grey-blue sea.
export const REGION_COLORS = ['#BBD8EC', '#BFE4D6', '#E6E0B8', '#F0D3C4', '#C4DFE6', '#D7E3B9', '#CCD8E6', '#E9D5B8'];
export const regionColor = (id: number): string => REGION_COLORS[(Math.max(1, id) - 1) % REGION_COLORS.length];

export type CycleState = 'unchecked' | 'nodata' | 'clean' | 'flagged' | 'audited';
export const CYCLE_LABEL: Record<CycleState, string> = {
  unchecked: 'not checked yet', nodata: 'no data in the rows checked', clean: 'checked, nothing flagged', flagged: 'flagged, audit pending', audited: 'flagged and audited',
};
export const CYCLE_COLOR: Record<CycleState, string> = { unchecked: '#94A3B8', nodata: '#64748B', clean: '#10B981', flagged: '#EF4444', audited: '#2563EB' };

type CycleCounts = { checked: number; flagged: number; no_data: number; unaudited: number };
/** Where a station is in the cycle: checked, flagged, audited. A station with any unaudited flag stays "flagged". */
export function cycleState(c: CycleCounts | null | undefined): CycleState {
  if (!c || c.checked <= 0) return 'unchecked';
  if (c.flagged > 0) return c.unaudited > 0 ? 'flagged' : 'audited';
  return c.no_data >= c.checked ? 'nodata' : 'clean';
}

export interface NetworkTotals { stations: number; checked: number; flagged: number; audited: number; unaudited: number; byState: Record<CycleState, number> }
export function networkTotals(list: (CycleCounts & { audited: number })[]): NetworkTotals {
  const byState: Record<CycleState, number> = { unchecked: 0, nodata: 0, clean: 0, flagged: 0, audited: 0 };
  let checked = 0, flagged = 0, audited = 0, unaudited = 0;
  for (const c of list) {
    byState[cycleState(c)]++;
    checked += c.checked; flagged += c.flagged; audited += Math.min(c.audited, c.flagged); unaudited += c.unaudited;
  }
  return { stations: list.length, checked, flagged, audited, unaudited, byState };
}

/** Great-circle distance in km (haversine), for "gauges near this IMD station". */
export function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * r) / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(((lon2 - lon1) * r) / 2) ** 2;
  return 2 * 6371.0088 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}
