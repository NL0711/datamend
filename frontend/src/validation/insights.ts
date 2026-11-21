// Types and pure helpers of the Insights page (unit-tested in insights.test.ts). No React, no network.
export type Granularity = 'month' | 'year';
export interface Unavailable { enough: false; reason: string }

export interface Selection {
  rows: number; rows_used: number; rows_without_mm: number; stations: number; first_day: string | null; last_day: string | null;
  truncated: boolean; synthetic: boolean; run_id: number | null; scope: string; granularity: Granularity; start: string | null; end: string | null;
  note?: string;
}
export interface AnomalyPoint { period: string; total_mm: number; normal_mm: number; anomaly_mm: number; z: number | null; flagged_days: number; history: number }
export type Anomaly = Unavailable | { enough: true; granularity: Granularity; min_history: number; series: { station: string; points: AnomalyPoint[] }[]; skipped: Record<string, string>; note: string };
export type Correlation = Unavailable | { enough: true; stations: string[]; matrix: (number | null)[][]; common_days: number[][]; min_common_days: number; truncated: boolean; total_stations: number; note: string };
export interface ClimateStation { station: string; days: number; annual_mm: number; wet_day_share: number; band: string }
export type Climate = Unavailable | { enough: true; stations: ClimateStation[]; too_short: string[]; wet_day_mm: number; bands: { name: string; from_mm: number; to_mm: number | null }[]; note: string };
export interface MixPeriod { period: string; rows: number; OK: number; SUSPECT: number; UNCERTAIN: number; NO_DATA: number; share_OK: number; share_SUSPECT: number; share_UNCERTAIN: number; share_NO_DATA: number }
export type VerdictMixData = Unavailable | { enough: true; granularity: Granularity; periods: MixPeriod[]; note: string };
export interface HeavyPoint { station: string; day: string; mm: number; verdict: string; heavy: boolean }
export type Heavy = Unavailable | {
  enough: true; stations: { station: string; threshold_mm: number; heavy_days: number; flagged: number; not_flagged: number }[]; too_short: string[];
  percentile: number; wet_day_mm: number; heavy_verdicts: Record<string, number>; other_wet_verdicts: Record<string, number>;
  points: HeavyPoint[]; points_truncated: boolean; note: string;
};
export interface InsightsData { selection: Selection; anomaly: Anomaly; correlation: Correlation; climate: Climate; verdict_mix: VerdictMixData; heavy_rain: Heavy }

export const BAND_COLOR: Record<string, string> = { dry: '#D97706', moderate: '#0EA5E9', wet: '#1D4ED8' };

/** The query string of GET /insights. Empty values are left out. */
export function insightsQuery(o: { runId?: number | null; includeSynthetic?: boolean; station?: string; start?: string; end?: string; granularity: Granularity }): string {
  const q = new URLSearchParams();
  if (o.runId) q.set('run_id', String(o.runId));
  else if (o.includeSynthetic) q.set('include_synthetic', 'true');
  if (o.station) q.append('station', o.station);
  if (o.start) q.set('start', o.start);
  if (o.end) q.set('end', o.end);
  q.set('granularity', o.granularity);
  return q.toString();
}

/** CSV of exactly the rows drawn. Values with a comma, quote or newline are quoted; null and undefined are empty cells. */
export function toCsv(rows: readonly object[]): string {
  if (!rows.length) return '';
  const cols = Object.keys(rows[0]);
  const cell = (v: unknown) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(','), ...rows.map((r) => cols.map((c) => cell((r as Record<string, unknown>)[c])).join(','))].join('\n');
}

/** A diverging colour for a correlation in [-1, 1]: blue for positive, orange for negative, grey for no value. */
export function corrColor(r: number | null): string {
  if (r === null) return '#E2E8F0';
  const a = Math.min(1, Math.abs(r));
  const [from, to] = r >= 0 ? [[241, 245, 249], [29, 78, 216]] : [[241, 245, 249], [217, 119, 6]];
  return `rgb(${from.map((f, i) => Math.round(f + (to[i] - f) * a)).join(',')})`;
}

/** Heavy-rain verdict shares as percentages that sum to 100 (or all zero when the group is empty). */
export function shareOf(v: Record<string, number>): Record<string, number> {
  const n = Object.values(v).reduce((a, b) => a + b, 0);
  return Object.fromEntries(Object.entries(v).map(([k, c]) => [k, n ? Math.round((c / n) * 1000) / 10 : 0]));
}
