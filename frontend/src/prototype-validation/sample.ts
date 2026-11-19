// PROTOTYPE (throwaway, ticket t06): deterministic SYNTHETIC sample run for the validation-platform dashboard variants.
// Nothing here is real gauge data. Verdicts and hits are hand-placed to show every state; headline numbers are computed from the rows.

export type Verdict = 'OK' | 'SUSPECT' | 'UNCERTAIN' | 'NO_DATA';
export type Severity = 'high' | 'medium' | 'low';

export interface Evidence {
  observed: { value: number | null; unit: string; basis: 'measured' | 'assumed' | 'derived' };
  threshold: { value: string; why: string };
  window: { i: number; intensity: number | null; accumulation: number | null }[];
  neighbours?: { station: string; distKm: number; state: string }[];
  timeBasis: 'received' | 'observed';
  reason: string;
}
export interface Hit { check: string; layer: 'input' | 'rule' | 'neighbour'; severity: Severity; weight: number; evidence: Evidence }
export interface Row {
  id: string; station: string; i: number; time: string;
  intensity: number | null; accumulation: number | null;
  verdict: Verdict; ruleScore: number; hits: Hit[];
}
export interface Station { id: string; name: string; lat: number; lon: number; cell: string; region: string; hasNeighbours: boolean }

export const STATIONS: Station[] = [
  { id: 'A', name: 'Goregaon East', lat: 19.166, lon: 72.865, cell: 'r52 c24', region: 'client 6', hasNeighbours: true },
  { id: 'B', name: 'Goregaon West', lat: 19.162, lon: 72.846, cell: 'r52 c24', region: 'client 6', hasNeighbours: true },
  { id: 'D', name: 'Andheri West', lat: 19.136, lon: 72.828, cell: 'r52 c24', region: 'client 6', hasNeighbours: true },
  { id: 'E', name: 'Malad West', lat: 19.186, lon: 72.835, cell: 'r52 c24', region: 'client 6', hasNeighbours: true },
  { id: 'C', name: 'Remote gauge (no neighbours)', lat: 19.9, lon: 73.6, cell: 'r54 c27', region: 'client 6', hasNeighbours: false },
];

export const WEIGHTS: Record<string, number> = {
  NEGATIVE_VALUE: 0.95, ACCUMULATION_JUMP: 0.7, FROZEN_INTENSITY: 0.6, ISOLATED_WET: 0.3, UNVERIFIED_EXTREME: 0.2,
};
export const LAYER: Record<string, Hit['layer']> = {
  MISSING_READING: 'input', NEGATIVE_VALUE: 'rule', ACCUMULATION_JUMP: 'rule', FROZEN_INTENSITY: 'rule',
  ISOLATED_WET: 'neighbour', UNVERIFIED_EXTREME: 'neighbour',
};
export const severityOf = (score: number): Severity => (score >= 0.7 ? 'high' : score >= 0.3 ? 'medium' : 'low');

const N = 96; // one rain day of 15-minute readings
const t0 = Date.UTC(2026, 10, 19, 3, 0, 0);
const time = (i: number) => new Date(t0 + i * 15 * 60000).toISOString().substring(11, 16) + 'Z';

function base(station: string): { intensity: number | null; accumulation: number | null }[] {
  const peak = { A: 6, B: 5.5, D: 6.2, E: 5.8, C: 6.5 }[station] as number;
  let acc = 0;
  return Array.from({ length: N }, (_, i) => {
    const v = peak * Math.exp(-(((i - 48) / 6) ** 2));
    const intensity = v < 0.05 ? 0 : Math.round(v * 10) / 10;
    acc += intensity * 0.25; // ASSUMED mm/h; units are unconfirmed on the live feed
    return { intensity, accumulation: Math.round(acc * 100) / 100 };
  });
}

function build(): Row[] {
  const rows: Row[] = [];
  const series: Record<string, ReturnType<typeof base>> = {};
  for (const s of STATIONS) series[s.id] = base(s.id);

  // faults (hand-placed)
  const A = series.A;
  for (let i = 5; i <= 8; i++) A[i] = { intensity: null, accumulation: null };                    // dropout
  for (let i = 20; i < N; i++) if (A[i].accumulation !== null) A[i].accumulation = Math.round(((A[i].accumulation as number) + 80) * 100) / 100; // counter jump
  for (let i = 70; i <= 77; i++) A[i].intensity = 2.4;                                             // frozen intensity
  A[84].intensity = -1.2;                                                                          // negative value
  for (let i = 12; i <= 14; i++) series.B[i].intensity = 3.0;                                      // isolated wet (neighbours dry)
  series.C[50].intensity = 120;                                                                    // heavy, nobody to confirm

  const win = (st: string, i: number) =>
    Array.from({ length: 6 }, (_, k) => i - 5 + k).filter((j) => j >= 0)
      .map((j) => ({ i: j, intensity: series[st][j].intensity, accumulation: series[st][j].accumulation }));
  const mk = (st: string, i: number, check: string, observed: Evidence['observed'], th: Evidence['threshold'], reason: string,
              neighbours?: Evidence['neighbours']): Hit => ({
    check, layer: LAYER[check], weight: WEIGHTS[check] ?? 0, severity: severityOf(WEIGHTS[check] ?? 0),
    evidence: { observed, threshold: th, window: win(st, i), neighbours, timeBasis: 'received', reason },
  });

  for (const s of STATIONS) {
    for (let i = 0; i < N; i++) {
      const r = series[s.id][i];
      const hits: Hit[] = [];
      let verdict: Verdict = 'OK';
      if (r.intensity === null) {
        verdict = 'NO_DATA';
        hits.push({ check: 'MISSING_READING', layer: 'input', weight: 0, severity: 'low', evidence: {
          observed: { value: null, unit: 'mm/h', basis: 'measured' }, threshold: { value: 'reading expected every 15 min', why: 'declared poll interval' },
          window: win(s.id, i), timeBasis: 'received', reason: 'No reading arrived for this 15-minute slot.' } });
      }
      if (s.id === 'A' && i === 20) {
        verdict = 'SUSPECT';
        hits.push(mk('A', i, 'ACCUMULATION_JUMP', { value: 80, unit: 'mm', basis: 'assumed' }, { value: '> 50 mm in one reading', why: 'design choice, uncalibrated' },
          'The accumulation counter rose by 80 mm between two consecutive readings while intensity was 0.'));
      }
      if (s.id === 'A' && i >= 75 && i <= 77) {
        verdict = 'SUSPECT';
        hits.push(mk('A', i, 'FROZEN_INTENSITY', { value: 2.4, unit: 'mm/h', basis: 'assumed' }, { value: 'same non-zero value 6 readings in a row', why: 'design choice, uncalibrated' },
          'Intensity has been exactly 2.4 for 6 consecutive readings.'));
      }
      if (s.id === 'A' && i === 84) {
        verdict = 'SUSPECT';
        hits.push(mk('A', i, 'NEGATIVE_VALUE', { value: -1.2, unit: 'mm/h', basis: 'measured' }, { value: '< 0', why: 'physical impossibility' },
          'A rain intensity cannot be negative.'));
      }
      if (s.id === 'B' && i >= 12 && i <= 14) {
        verdict = 'UNCERTAIN';
        hits.push(mk('B', i, 'ISOLATED_WET', { value: 3.0, unit: 'mm/h', basis: 'assumed' }, { value: '>= 75% of >= 3 neighbours dry', why: 'design choice, uncalibrated' },
          'Wet here while all 3 neighbours within 10 km are dry. Local convective rain is possible, so this is not called a fault.',
          [{ station: 'Goregaon East', distKm: 2.0, state: 'dry' }, { station: 'Andheri West', distKm: 4.1, state: 'dry' }, { station: 'Malad West', distKm: 4.3, state: 'dry' }]));
      }
      if (s.id === 'C' && i === 50) {
        verdict = 'UNCERTAIN';
        hits.push(mk('C', i, 'UNVERIFIED_EXTREME', { value: 120, unit: 'mm/h', basis: 'assumed' }, { value: 'heavy value, no neighbours within 10 km', why: 'cannot be confirmed or refuted' },
          'A heavy value with no neighbours or grid to confirm it. Judged uncertain, never suspect on magnitude alone.', []));
      }
      const ruleScore = Math.round((1 - hits.reduce((p, h) => p * (1 - h.weight), 1)) * 1000) / 1000;
      rows.push({ id: `${s.id}-${i}`, station: s.id, i, time: time(i), intensity: r.intensity, accumulation: r.accumulation, verdict, ruleScore, hits });
    }
  }
  return rows;
}

export const ROWS: Row[] = build();
export const FLAGGED: Row[] = ROWS.filter((r) => r.verdict !== 'OK');

export const RUN = {
  id: 'run-sample-0001',
  profile: 'reading',
  source: 'upload (SAMPLE)',
  inputHash: 'sha256:synthetic-sample',
  interval: 15,
  mode: 'cumulative (declared)',
  version: 'prototype',
  storage: 'demo storage, resets on restart',
  notRun: [
    { check: 'Own-climatology upper tail', why: 'daily profile only' },
    { check: 'Neighbour check at station C', why: 'needs at least 3 stations within 10 km, found 0' },
    { check: 'Trained score provider layer', why: 'NOT IMPLEMENTED: no trained model has run on real data' },
  ],
};

export function headline() {
  const total = ROWS.length;
  const present = ROWS.filter((r) => r.verdict !== 'NO_DATA').length;
  const count = (v: Verdict) => ROWS.filter((r) => r.verdict === v).length;
  const perCheck: Record<string, { rows: number; severity: Severity; layer: string }> = {};
  for (const r of ROWS) for (const h of r.hits) {
    perCheck[h.check] ??= { rows: 0, severity: h.severity, layer: h.layer };
    perCheck[h.check].rows++;
  }
  return {
    total, completeness: present / total, suspect: count('SUSPECT') / total, uncertain: count('UNCERTAIN') / total,
    nSuspect: count('SUSPECT'), nUncertain: count('UNCERTAIN'), nNoData: count('NO_DATA'), perCheck,
  };
}

export const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
export const stationName = (id: string) => STATIONS.find((s) => s.id === id)?.name ?? id;
