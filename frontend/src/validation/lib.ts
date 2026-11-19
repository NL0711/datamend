// Pure helpers of the validation dashboard (unit-tested in lib.test.ts). No React, no network.
import type { Completeness, Headline, SeriesPoint, Verdict } from './types';

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

export function headlineLine(h: Headline | null | undefined): string {
  if (!h) return 'no headline';
  return `${h.rows} rows · ${h.stations} station(s) · SUSPECT ${pct(h.share_suspect)} · UNCERTAIN ${pct(h.share_uncertain)} · NO_DATA ${pct(h.share_no_data)}`;
}

/** Plain-text guard for generated text: the UI only ever renders it as text, never as HTML. */
export function asPlainText(s: unknown): string {
  return typeof s === 'string' ? s : '';
}
