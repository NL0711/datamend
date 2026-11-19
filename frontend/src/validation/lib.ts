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
export function queueQuery(o: { page: number; status: 'unreviewed' | 'reviewed' | 'all'; verdict?: 'SUSPECT' | 'UNCERTAIN' | ''; check?: string; runId?: number | null; synthetic?: 'all' | 'synthetic' | 'real' }): string {
  const q = new URLSearchParams({ status: o.status, page: String(Math.max(1, Math.floor(o.page))), page_size: String(PAGE_SIZE) });
  if (o.verdict) q.set('verdict', o.verdict);
  if (o.check) q.set('check', o.check);
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
