import { afterEach, describe, expect, it, vi } from 'vitest';
import { getAllGauges, getImdStations, getMapLayers, getQueue, getStationCycle } from './api';
import {
  CYCLE_COLOR, INDIA_BOUNDS, MAX_SCALE, MIN_SCALE, cycleState, distanceKm, fitView, nearestPoint, networkTotals, panBy, project, queueQuery, regionColor,
  unproject, zoomAt,
} from './lib';

const W = 800, H = 560;
const counts = (o: Partial<{ checked: number; flagged: number; no_data: number; unaudited: number; audited: number }> = {}) =>
  ({ checked: 10, flagged: 0, no_data: 0, unaudited: 0, audited: 0, ...o });

describe('flat map projection', () => {
  it('fits India with a margin and round-trips a point', () => {
    const v = fitView(W, H);
    const sw = project(INDIA_BOUNDS.latMin, INDIA_BOUNDS.lonMin, v, W, H);
    const ne = project(INDIA_BOUNDS.latMax, INDIA_BOUNDS.lonMax, v, W, H);
    expect(sw.x).toBeGreaterThanOrEqual(0); expect(ne.x).toBeLessThanOrEqual(W);
    expect(ne.y).toBeGreaterThanOrEqual(0); expect(sw.y).toBeLessThanOrEqual(H);
    const p = project(19.076, 72.877, v, W, H);
    const back = unproject(p.x, p.y, v, W, H);
    expect(back.lat).toBeCloseTo(19.076, 6); expect(back.lon).toBeCloseTo(72.877, 6);
  });
  it('draws north up and east right', () => {
    const v = fitView(W, H);
    expect(project(30, 80, v, W, H).y).toBeLessThan(project(10, 80, v, W, H).y);
    expect(project(20, 90, v, W, H).x).toBeGreaterThan(project(20, 70, v, W, H).x);
  });
  it('zooms around the cursor: the point under it does not move, and the scale is clamped', () => {
    const v = fitView(W, H);
    const before = unproject(300, 200, v, W, H);
    const z = zoomAt(v, 2, 300, 200, W, H);
    const after = unproject(300, 200, z, W, H);
    expect(after.lat).toBeCloseTo(before.lat, 6); expect(after.lon).toBeCloseTo(before.lon, 6);
    expect(z.scale).toBeCloseTo(v.scale * 2, 6);
    expect(zoomAt(v, 1e9, 10, 10, W, H).scale).toBe(MAX_SCALE);
    expect(zoomAt(v, 1e-9, 10, 10, W, H).scale).toBe(MIN_SCALE);
  });
  it('pans with the drag: dragging right moves the map right', () => {
    const v = fitView(W, H);
    const p0 = project(20, 78, v, W, H);
    const p1 = project(20, 78, panBy(v, 40, -25), W, H);
    expect(p1.x - p0.x).toBeCloseTo(40, 6); expect(p1.y - p0.y).toBeCloseTo(-25, 6);
  });
});

describe('picking a station', () => {
  const pts = [{ id: 'a', x: 10, y: 10 }, { id: 'b', x: 14, y: 10 }, { id: 'c', x: 200, y: 200 }];
  it('returns the closest point within the radius, else null', () => {
    expect(nearestPoint(pts, 13, 10, 9)?.id).toBe('b');
    expect(nearestPoint(pts, 100, 100, 9)).toBeNull();
    expect(nearestPoint([], 1, 1, 9)).toBeNull();
  });
  it('breaks a tie in favour of the earlier point', () => {
    expect(nearestPoint([{ id: 'x', x: 0, y: 0 }, { id: 'y', x: 2, y: 0 }], 1, 0, 5)?.id).toBe('x');
  });
});

describe('the check -> flag -> audit state of a station', () => {
  it('is unchecked without rows, clean without flags, flagged while any flag is unaudited, audited when all are', () => {
    expect(cycleState(undefined)).toBe('unchecked');
    expect(cycleState(null)).toBe('unchecked');
    expect(cycleState(counts({ checked: 0 }))).toBe('unchecked');
    expect(cycleState(counts())).toBe('clean');
    expect(cycleState(counts({ checked: 5, no_data: 5 }))).toBe('nodata');
    expect(cycleState(counts({ flagged: 3, unaudited: 1, audited: 2 }))).toBe('flagged');
    expect(cycleState(counts({ flagged: 3, unaudited: 0, audited: 3 }))).toBe('audited');
  });
  it('has a colour for every state', () => {
    for (const s of ['unchecked', 'nodata', 'clean', 'flagged', 'audited'] as const) expect(CYCLE_COLOR[s]).toMatch(/^#[0-9A-F]{6}$/);
  });
  it('totals the network without counting audits beyond the flags', () => {
    const t = networkTotals([counts({ flagged: 3, unaudited: 1, audited: 2 }), counts({ flagged: 1, unaudited: 0, audited: 4 }), counts(), counts({ checked: 0 })]);
    expect(t).toMatchObject({ stations: 4, checked: 30, flagged: 4, audited: 3, unaudited: 1 });
    expect(t.byState).toEqual({ unchecked: 1, nodata: 0, clean: 1, flagged: 1, audited: 1 });
    expect(networkTotals([]).stations).toBe(0);
  });
});

describe('small helpers', () => {
  it('measures great-circle distance in km', () => {
    expect(distanceKm(19.076, 72.877, 19.076, 72.877)).toBe(0);
    expect(distanceKm(0, 0, 0, 1)).toBeCloseTo(111.2, 0);
    expect(distanceKm(28.61, 77.21, 19.07, 72.88)).toBeGreaterThan(1100);       // Delhi to Mumbai is about 1,150 km
    expect(distanceKm(28.61, 77.21, 19.07, 72.88)).toBeLessThan(1200);
  });
  it('colours the eight regions distinctly', () => {
    expect(new Set([1, 2, 3, 4, 5, 6, 7, 8].map(regionColor)).size).toBe(8);
  });
  it('lets the audit queue be limited to a station', () => {
    expect(queueQuery({ page: 1, status: 'unreviewed', station: 'ZWL001' })).toBe('status=unreviewed&page=1&page_size=50&station=ZWL001');
    expect(queueQuery({ page: 1, status: 'all', station: '' })).toBe('status=all&page=1&page_size=50');
  });
});

describe('network API calls', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('asks for the whole gauge catalogue, the IMD list, the map layers and the station cycle', async () => {
    const f = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ stations: [], rows: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', f);
    await getAllGauges(); await getImdStations(); await getMapLayers(); await getStationCycle();
    await getQueue(queueQuery({ page: 1, status: 'unreviewed', station: 'S 1' }));
    expect(f.mock.calls.map((c) => c[0])).toEqual([
      '/api/places/stations?limit=600', '/api/places/imd-stations', '/api/places/map', '/api/validation/stations',
      '/api/validation/review/queue?status=unreviewed&page=1&page_size=50&station=S+1',
    ]);
  });
  it('surfaces the server reason when the land mask is missing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'the RF25 land mask asset is not available on this server' }), { status: 503, headers: { 'Content-Type': 'application/json' } })));
    await expect(getMapLayers()).rejects.toMatchObject({ status: 503, message: 'the RF25 land mask asset is not available on this server' });
  });
});
