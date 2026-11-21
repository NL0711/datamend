import { describe, expect, it, vi } from 'vitest';
import {
  RAIL, SELECTED_KEY, UPLOAD_GROUP, buildStationList, createSelectionStore, filterStations, groupByCity, hashForPage, moveActive, pageForKey, pageForTab, pageFromHash,
} from './shell';
import type { GaugeStation } from './types';

const g = (station_id: string, place: string, city: string): GaugeStation =>
  ({ station_id, place, city, latitude: 1, longitude: 2, device: 'WU', cell: null, is_land: true });

const gauges = [g('ZWL_1', 'Andheri', 'Mumbai'), g('ZWL_2', 'Bandra East', 'Mumbai'), g('ZWL_3', 'Koramangala', 'Bengaluru')];
const list = buildStationList(gauges, [
  { station_id: 'ZWL_1', place: 'Andheri', city: 'Mumbai' },        // already in the catalogue: not added twice
  { station_id: 'FILE_A', place: null, city: null },
]);

describe('route mapping', () => {
  it('maps hashes to pages and back', () => {
    expect(pageFromHash('#/app')).toBe('overview');
    expect(pageFromHash('#/app/live')).toBe('live');
    expect(pageFromHash('#/app/import')).toBe('import');
    expect(pageFromHash('#/app/settings')).toBe('settings');
    expect(pageFromHash('#/app/nonsense')).toBe('overview');
    expect(pageFromHash('#/app/')).toBe('overview');
    for (const p of [...RAIL.map((r) => r.id), 'import', 'settings'] as const) expect(pageFromHash(hashForPage(p))).toBe(p);
    expect(hashForPage('overview')).toBe('#/app');
  });
  it('keeps every dashboard hash under #/app so the sign-in guard still sees it', () => {
    for (const r of RAIL) expect(hashForPage(r.id).startsWith('#/app')).toBe(true);
  });
  it('has the eight rail pages in the agreed order', () => {
    expect(RAIL.map((r) => r.label)).toEqual(['Overview', 'Live', 'Alerts', 'Events', 'Explorer', 'Review', 'Injector', 'Agent']);
  });
  it('keys 1 to 8 pick the rail page, other keys nothing', () => {
    expect(pageForKey('1')).toBe('overview');
    expect(pageForKey('4')).toBe('events');
    expect(pageForKey('8')).toBe('agent');
    for (const k of ['0', '9', 'a', '12', '', 's']) expect(pageForKey(k)).toBeNull();
  });
  it('maps the old step names onto pages', () => {
    expect(pageForTab('runs')).toBe('import');
    expect(pageForTab('run')).toBe('events');
    expect(pageForTab('stations')).toBe('overview');
    expect(pageForTab('review')).toBe('review');
    expect(pageForTab('settings')).toBe('settings');
    expect(pageForTab('whatever')).toBe('overview');
  });
});

describe('station list', () => {
  it('adds uploaded-file stations once, after sorting by city then place', () => {
    expect(list.map((s) => s.id)).toEqual(['ZWL_3', 'FILE_A', 'ZWL_1', 'ZWL_2']);
    expect(list).toHaveLength(4);
    expect(list.filter((s) => s.id === 'ZWL_1')).toHaveLength(1);
    const file = list.find((s) => s.id === 'FILE_A')!;
    expect(file).toMatchObject({ place: 'FILE_A', city: UPLOAD_GROUP, source: 'upload' });
    expect(list[0].city).toBe('Bengaluru');
  });
});

describe('filterStations and groupByCity', () => {
  it('matches every word against place, city and id, ignoring case', () => {
    expect(filterStations(list, 'andheri').map((s) => s.id)).toEqual(['ZWL_1']);
    expect(filterStations(list, 'mumbai band').map((s) => s.id)).toEqual(['ZWL_2']);
    expect(filterStations(list, 'zwl_3').map((s) => s.id)).toEqual(['ZWL_3']);
    expect(filterStations(list, 'mumbai').map((s) => s.id).sort()).toEqual(['ZWL_1', 'ZWL_2']);
    expect(filterStations(list, 'nowhere')).toEqual([]);
    expect(filterStations(list, '   ')).toHaveLength(4);
  });
  it('limits to one city when asked and combines with the text', () => {
    expect(filterStations(list, '', 'Mumbai')).toHaveLength(2);
    expect(filterStations(list, 'koram', 'Mumbai')).toEqual([]);
    expect(filterStations(list, 'koram', 'Bengaluru')).toHaveLength(1);
  });
  it('groups neighbours of the same city in order', () => {
    const groups = groupByCity(list);
    expect(groups.map((x) => x.city)).toEqual(['Bengaluru', UPLOAD_GROUP, 'Mumbai']);
    expect(groups.find((x) => x.city === 'Mumbai')!.stations).toHaveLength(2);
    expect(groupByCity([])).toEqual([]);
  });
  it('moves the highlighted row without leaving the list', () => {
    expect(moveActive(0, -1, 5)).toBe(0);
    expect(moveActive(4, 1, 5)).toBe(4);
    expect(moveActive(1, 1, 5)).toBe(2);
    expect(moveActive(0, 1, 0)).toBe(-1);
  });
});

describe('selection store', () => {
  const memory = () => {
    const m = new Map<string, string>();
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k), m };
  };
  it('starts empty, holds one id and tells subscribers once per change', () => {
    const s = createSelectionStore();
    const fn = vi.fn();
    const off = s.subscribe(fn);
    expect(s.get()).toBeNull();
    s.set('ZWL_1'); s.set('ZWL_1');
    expect(s.get()).toBe('ZWL_1');
    expect(fn).toHaveBeenCalledTimes(1);
    s.set('ZWL_2');
    expect(fn).toHaveBeenCalledTimes(2);
    s.set('  '); expect(s.get()).toBeNull();
    off(); s.set('ZWL_3');
    expect(fn).toHaveBeenCalledTimes(3);
  });
  it('remembers the choice in the tab and clears it', () => {
    const st = memory();
    const a = createSelectionStore(st);
    a.set('ZWL_9');
    expect(st.m.get(SELECTED_KEY)).toBe('ZWL_9');
    expect(createSelectionStore(st).get()).toBe('ZWL_9');
    a.set(null);
    expect(st.m.has(SELECTED_KEY)).toBe(false);
  });
});
