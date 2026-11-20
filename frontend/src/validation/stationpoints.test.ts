import { describe, expect, it } from 'vitest';
import { isPlaceable, stationPoints } from './stationpoints';
import type { ExploreStation } from './types';

const st = (o: Partial<ExploreStation>): ExploreStation => ({
  station_key: 'S1', name: 'Alpha', state: 'Kerala', district: null, latitude: 9.9, longitude: 76.3, located: true, rf25: null, nearest_imd: null, n_observations: 1200, first: null, last: null, ...o,
});

describe('stations on the map', () => {
  it('places a located station at the position the data gave', () => {
    const [p] = stationPoints([st({})]);
    expect(p).toMatchObject({ key: 'station:S1', kind: 'station', id: 'S1', lat: 9.9, lon: 76.3 });
    expect(p.label).toContain('Alpha'); expect(p.label).toContain('1,200');
  });
  it('never draws a station that has no position or is not located', () => {
    expect(isPlaceable(st({ latitude: null }))).toBe(false);
    expect(isPlaceable(st({ located: false }))).toBe(false);
    expect(isPlaceable(st({ longitude: Number.NaN }))).toBe(false);
    expect(stationPoints([st({ located: false }), st({ station_key: 'S2', latitude: null }), st({ station_key: 'S3' })]).map((p) => p.id)).toEqual(['S3']);
  });
  it('falls back to the key when the station has no name', () => {
    expect(stationPoints([st({ name: null, state: null })])[0].label.startsWith('S1')).toBe(true);
  });
});
