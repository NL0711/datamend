// Tests of the pure helpers added in slice S2b: map pins, the two weather formulas, severity and verdict colours, the source words,
// "not built" detection for the service contract, and page ids.
import { describe, expect, it } from 'vitest';
import { buildPins, dewPoint, reading, vaporPressure } from './pins';
import { severityVariant, verdictVariant } from './severity';
import { sourceLabel } from './sourceLabel';
import { ServiceError, isNotBuilt } from '../services/api';
import { pageFromId } from '../validation/shell';
import type { GaugeStation, StationCycle } from '../validation/types';

const gauge = (id: string): GaugeStation => ({ station_id: id, city: 'Pune', place: `Place ${id}`, latitude: 18.5, longitude: 73.8, device: 'WU', cell: null, is_land: null });
const cyc = (over: Partial<StationCycle>): StationCycle => ({
  station_id: 'X', place: null, city: null, latitude: null, longitude: null, position_source: null, checked: 0, runs: 0, synthetic_rows: 0, last_run_at: null,
  latest_run_id: null, flagged: 0, suspect: 0, uncertain: 0, no_data: 0, audited: 0, unaudited: 0, decisions: {} as StationCycle['decisions'], top_checks: {}, ...over,
});

describe('buildPins', () => {
  it('draws every gauge, grey when nothing was checked, and carries the station cycle counts', () => {
    const pins = buildPins([gauge('A'), gauge('B')], [cyc({ station_id: 'A', checked: 10, suspect: 2, runs: 1 })]);
    expect(pins.map((p) => p.station_id)).toEqual(['A', 'B']);
    expect(pins[0]).toMatchObject({ state: 'SUSPECT', checked: 10, suspect: 2, runs: 1, positionSource: 'catalogue' });
    expect(pins[1]).toMatchObject({ state: 'NO_DATA', checked: 0 });
  });
  it('adds an uploaded-file station only when it brings its own coordinates', () => {
    const pins = buildPins([gauge('A')], [
      cyc({ station_id: 'U1', latitude: 10, longitude: 20, position_source: 'upload', checked: 3 }),
      cyc({ station_id: 'U2', checked: 3 }),                 // no position: never placed anywhere
      cyc({ station_id: 'A', checked: 1 }),                  // already a gauge: not drawn twice
    ]);
    expect(pins.map((p) => p.station_id)).toEqual(['A', 'U1']);
    expect(pins[1]).toMatchObject({ latitude: 10, longitude: 20, positionSource: 'upload' });
  });
});

describe('weather formulas', () => {
  it('dew point: 20 C at 50 % is about 9.3 C, and 100 % gives the temperature itself', () => {
    expect(dewPoint(20, 50)).toBeCloseTo(9.3, 1);
    expect(dewPoint(25, 100)).toBeCloseTo(25, 5);
  });
  it('returns null, never a made-up number, when an input is missing or the humidity is not above 0', () => {
    expect(dewPoint(null, 50)).toBeNull();
    expect(dewPoint(20, undefined)).toBeNull();
    expect(dewPoint(20, 0)).toBeNull();
    expect(vaporPressure(null, 50)).toBeNull();
  });
  it('vapour pressure: 20 C at 100 % is about 23.4 hPa', () => {
    expect(vaporPressure(20, 100)).toBeCloseTo(23.4, 1);
  });
  it('reading shows a dash for a missing value and the unit otherwise', () => {
    expect(reading(null, 1, '°C')).toBe('—');
    expect(reading(undefined, 1, '°C')).toBe('—');
    expect(reading(NaN, 1, '°C')).toBe('—');
    expect(reading(12.345, 1, ' hPa')).toBe('12.3 hPa');
  });
});

describe('severity, verdict and source words', () => {
  it('maps severities onto badge variants, unknown to nominal', () => {
    expect(severityVariant('CRITICAL')).toBe('critical');
    expect(severityVariant('high')).toBe('warning');
    expect(severityVariant('LOW')).toBe('info');
    expect(severityVariant(undefined)).toBe('nominal');
  });
  it('maps verdicts onto variants; "not checked" is neutral, never green', () => {
    expect(verdictVariant('SUSPECT')).toBe('critical');
    expect(verdictVariant('UNCERTAIN')).toBe('warning');
    expect(verdictVariant('OK')).toBe('nominal');
    expect(verdictVariant('NOT CHECKED')).toBe('neutral');
    expect(verdictVariant('NO_DATA')).toBe('neutral');
  });
  it('says "no live source" when nothing answered', () => {
    expect(sourceLabel(null)).toBe('NO LIVE SOURCE CONNECTED');
    expect(sourceLabel('EXTERNAL_API', 'Pune')).toBe('OPEN-METEO: PUNE');
    expect(sourceLabel('WEATHER_UNION')).toBe('WEATHER UNION');
  });
});

describe('isNotBuilt', () => {
  it('is true for the answers of an endpoint that is not there yet', () => {
    for (const s of [404, 405, 501, 502, 503]) expect(isNotBuilt(new ServiceError(s, 'x'))).toBe(true);
  });
  it('is false for real failures and for other errors', () => {
    for (const s of [400, 401, 422, 500]) expect(isNotBuilt(new ServiceError(s, 'x'))).toBe(false);
    expect(isNotBuilt(new Error('network'))).toBe(false);
    expect(isNotBuilt(undefined)).toBe(false);
  });
});

describe('pageFromId', () => {
  it('opens the named page and falls back to the Overview', () => {
    expect(pageFromId('live')).toBe('live');
    expect(pageFromId('alerts')).toBe('alerts');
    expect(pageFromId('settings')).toBe('settings');
    expect(pageFromId('health')).toBe('overview');
    expect(pageFromId('')).toBe('overview');
  });
});
