import { afterEach, describe, expect, it, vi } from 'vitest';
import { ADMIN_TOKEN_KEY, ApiError, generateLab, getExplorer, getFeed, getQueue, getRows, postReview, rememberToken, saveSettings, sendChat, storedToken, uploadRun } from './api';
import { ALL_CHECKS, DECISION_LABEL, PAGE_SIZE, asPlainText, buildLanes, buildSettingsUpdate, chartData, completenessText, explorerQuery, lanePosition, markerY, pct, queueQuery, rowsQuery } from './lib';
import type { SeriesPoint, SettingsState } from './types';

const pt = (id: number, time: string, over: Partial<SeriesPoint> = {}): SeriesPoint => ({
  id, time, intensity: 0, accumulation: 0, mm: null, verdict: 'SUSPECT', rule_score: 0.7, ...over,
});

describe('rowsQuery', () => {
  it('asks the server for a page of at most 50 and omits empty filters', () => {
    expect(rowsQuery({ page: 1 })).toBe(`page=1&page_size=${PAGE_SIZE}`);
    expect(PAGE_SIZE).toBe(50);
    expect(rowsQuery({ page: 3, verdict: 'ALL', check: '', station: '' })).toBe('page=3&page_size=50');
    expect(rowsQuery({ page: 2, verdict: 'UNCERTAIN', check: 'counter_jump', station: 'A 1' })).toBe(
      'page=2&page_size=50&verdict=UNCERTAIN&check=counter_jump&station=A+1');
  });
  it('never sends a page below 1', () => {
    expect(rowsQuery({ page: 0 })).toContain('page=1&');
    expect(rowsQuery({ page: -4 })).toContain('page=1&');
  });
});

describe('formatting', () => {
  it('shows n/a for a missing share and keeps tiny shares visible', () => {
    expect(pct(null)).toBe('n/a');
    expect(pct(0.075)).toBe('7.5%');
    expect(pct(0.0004)).toBe('0.04%');
  });
  it('says why completeness was not computed instead of guessing', () => {
    expect(completenessText({ value: null, reason: 'not computed: no interval_minutes declared' })).toContain('no interval_minutes');
    expect(completenessText({ value: 0.5, n: 5, expected: 10 })).toBe('50.0% (5 of 10 expected, derived)');
  });
  it('treats generated text as plain text only', () => {
    expect(asPlainText('<img src=x onerror=alert(1)>')).toBe('<img src=x onerror=alert(1)>');
    expect(asPlainText({ html: 1 })).toBe('');
  });
});

describe('timeline helpers', () => {
  it('positions ticks by time and clamps', () => {
    expect(lanePosition('2026-07-01T06:30:00+00:00', '2026-07-01T06:00:00+00:00', '2026-07-01T07:00:00+00:00')).toBeCloseTo(0.5);
    expect(lanePosition('2026-07-01T05:00:00Z', '2026-07-01T06:00:00Z', '2026-07-01T07:00:00Z')).toBe(0);
    expect(lanePosition('2026-07-01T09:00:00Z', '2026-07-01T06:00:00Z', '2026-07-01T07:00:00Z')).toBe(1);
    expect(lanePosition('2026-07-01T06:00:00Z', '2026-07-01T06:00:00Z', '2026-07-01T06:00:00Z')).toBe(0.5);
    expect(lanePosition('2026-07-02', '2026-07-01', '2026-07-03')).toBeCloseTo(0.5);
  });
  it('builds one lane per fired check, busiest first, with one tick per flagged row', () => {
    const flagged = [pt(1, '2026-07-01T06:00:00Z', { checks: ['counter_jump', 'negative_value'] }),
                     pt(2, '2026-07-01T07:00:00Z', { checks: ['counter_jump'] }), pt(3, '2026-07-01T07:00:00Z')];
    const lanes = buildLanes(flagged, '2026-07-01T06:00:00Z', '2026-07-01T07:00:00Z');
    expect(lanes.map((l) => [l.check, l.marks.length])).toEqual([['counter_jump', 2], ['negative_value', 1]]);
    expect(lanes[0].marks.map((m) => m.x)).toEqual([0, 1]);
  });
  it('plots on a numeric time axis and places a marker on the larger value', () => {
    expect(chartData([pt(1, '2026-07-01T06:00:00Z', { intensity: 2, accumulation: 5 })])[0]).toEqual({ t: Date.parse('2026-07-01T06:00:00Z'), intensity: 2, accumulation: 5, mm: null });
    expect(markerY(pt(1, 'x', { intensity: null, mm: 12 }))).toBe(12);
    expect(markerY(pt(1, 'x', { intensity: null, mm: null }))).toBe(0);
  });
});

describe('explorer and review queries', () => {
  it('asks for every row in time order, 50 per page, with only the filters that are set', () => {
    expect(explorerQuery({ page: 1 })).toBe('scope=all&sort=time&page=1&page_size=50');
    expect(explorerQuery({ page: 2, station: 'A', verdict: 'OK', check: 'counter_jump', from: '2026-07-01', to: '2026-07-31' }))
      .toBe('scope=all&sort=time&page=2&page_size=50&station=A&verdict=OK&check=counter_jump&time_from=2026-07-01&time_to=2026-07-31');
    expect(explorerQuery({ page: 0, verdict: 'ALL', station: '' })).toBe('scope=all&sort=time&page=1&page_size=50');
  });
  it('builds the review queue query: unreviewed by default, data filter mapped to the synthetic flag', () => {
    expect(queueQuery({ page: 1, status: 'unreviewed' })).toBe('status=unreviewed&page=1&page_size=50');
    expect(queueQuery({ page: 3, status: 'all', verdict: 'SUSPECT', check: 'frozen_intensity', runId: 7, synthetic: 'synthetic' }))
      .toBe('status=all&page=3&page_size=50&verdict=SUSPECT&check=frozen_intensity&run_id=7&synthetic=true');
    expect(queueQuery({ page: 1, status: 'reviewed', synthetic: 'real' })).toContain('synthetic=false');
    expect(queueQuery({ page: 1, status: 'reviewed', synthetic: 'all' })).not.toContain('synthetic');
  });
  it('labels every decision and lists every check once', () => {
    expect(Object.keys(DECISION_LABEL).sort()).toEqual(['confirmed_fault', 'false_alarm', 'genuine_extreme', 'needs_followup']);
    expect(new Set(ALL_CHECKS).size).toBe(ALL_CHECKS.length);
    expect(ALL_CHECKS).toContain('neighbour_isolated_wet');
  });
});

describe('settings update', () => {
  const current = {
    editing_enabled: true, cities: ['Mumbai', 'Pune'], accumulation_modes: ['cumulative', 'per_reading'], interval_limits_seconds: [60, 86400],
    weather_union: { api_key_set: true, api_key_source: 'runtime', city: 'Mumbai', city_source: 'runtime', poll_interval_seconds: 900,
      poll_interval_source: 'environment', accumulation_mode: 'cumulative', accumulation_mode_source: 'environment', enabled: true },
    narrator: { url: '', url_source: 'unset', token_set: false, token_source: 'unset', connected: false }, feed_running: true,
  } as const as unknown as SettingsState;
  const unchanged = { apiKey: '', city: 'Mumbai', intervalMinutes: '15', mode: 'cumulative', narratorUrl: '', narratorToken: '' };

  it('sends nothing when nothing changed, so an empty secret box never overwrites a saved key', () => {
    expect(buildSettingsUpdate(unchanged, current)).toBeNull();
  });
  it('sends only what changed and converts minutes to seconds', () => {
    expect(buildSettingsUpdate({ ...unchanged, city: 'Pune', intervalMinutes: '30' }, current)).toEqual({ weather_union_city: 'Pune', weather_union_poll_interval_seconds: 1800 });
  });
  it('sends a secret only when one was typed, trimmed', () => {
    expect(buildSettingsUpdate({ ...unchanged, apiKey: '  new-key-12345  ', narratorToken: ' tok-1234567 ' }, current))
      .toEqual({ weather_union_api_key: 'new-key-12345', narrator_token: 'tok-1234567' });
  });
  it('sends the narrator URL only when it differs, and passes clear requests through', () => {
    expect(buildSettingsUpdate({ ...unchanged, narratorUrl: 'https://n.example/x' }, current)).toEqual({ narrator_url: 'https://n.example/x' });
    expect(buildSettingsUpdate(unchanged, current, ['narrator_url'])).toEqual({ clear: ['narrator_url'] });
  });
  it('ignores a blank or non-numeric interval instead of sending garbage', () => {
    expect(buildSettingsUpdate({ ...unchanged, intervalMinutes: '' }, current)).toBeNull();
    expect(buildSettingsUpdate({ ...unchanged, intervalMinutes: 'abc' }, current)).toBeNull();
  });
});

describe('api client', () => {
  afterEach(() => { vi.unstubAllGlobals(); });
  const respond = (status: number, body: unknown) => vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));

  it('surfaces the server reason for a rejected upload', async () => {
    vi.stubGlobal('fetch', respond(422, { detail: { rejected: true, reason: 'missing required column(s) for the reading profile: station_id', run_id: 4 } }));
    const file = new File(['x'], 'a.csv');
    await expect(uploadRun({ file, profile: 'reading', synthetic: false })).rejects.toMatchObject({ status: 422, message: expect.stringContaining('station_id') });
  });
  it('sends upload options as a form and only the ones that were set', async () => {
    const f = respond(201, { id: 1 });
    vi.stubGlobal('fetch', f);
    await uploadRun({ file: new File(['x'], 'a.csv'), profile: 'reading', accumulationMode: 'cumulative', intervalMinutes: '15', synthetic: true });
    const fd = (f.mock.calls[0][1] as RequestInit).body as FormData;
    expect([...fd.keys()].sort()).toEqual(['accumulation_mode', 'file', 'interval_minutes', 'profile', 'synthetic']);
    expect(fd.get('synthetic')).toBe('true');
  });
  it('requests a page with the server-side query', async () => {
    const f = respond(200, { page: 1, page_size: 50, total: 0, pages: 0, rows: [] });
    vi.stubGlobal('fetch', f);
    await getRows(7, rowsQuery({ page: 1, verdict: 'SUSPECT' }));
    expect(f.mock.calls[0][0]).toBe('/api/validation/runs/7/rows?page=1&page_size=50&verdict=SUSPECT');
  });
  it('posts a review with the admin token and surfaces a refusal without one', async () => {
    const f = respond(401, { detail: 'the admin token is missing or wrong' });
    vi.stubGlobal('fetch', f);
    await expect(postReview(3, 9, { decision: 'false_alarm', note: 'n' }, '')).rejects.toMatchObject({ status: 401 });
    const [url, init] = f.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/validation/runs/3/rows/9/review');
    expect(init.method).toBe('POST');
    expect((init.headers as Record<string, string>)['X-Admin-Token']).toBe('');
    expect(JSON.parse(init.body as string)).toEqual({ decision: 'false_alarm', note: 'n' });
  });
  it('requests the queue, the explorer page and the lab with the right URLs', async () => {
    const f = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ rows: [] }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', f);
    await getQueue(queueQuery({ page: 1, status: 'unreviewed' }));
    await getExplorer(4, explorerQuery({ page: 1, station: 'A' }));
    await generateLab({ profile: 'daily', n_stations: 6, length: 60, faults: ['repeated_value'], seed: 5 });
    expect(f.mock.calls.map((c) => c[0])).toEqual([
      '/api/validation/review/queue?status=unreviewed&page=1&page_size=50',
      '/api/validation/runs/4/rows?scope=all&sort=time&page=1&page_size=50&station=A',
      '/api/validation/lab/generate']);
    expect(JSON.parse((f.mock.calls[2][1] as RequestInit).body as string)).toEqual({ profile: 'daily', n_stations: 6, length: 60, faults: ['repeated_value'], seed: 5 });
  });
  it('keeps the admin token for this tab only', () => {
    const store: Record<string, string> = {};
    vi.stubGlobal('sessionStorage', { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => { store[k] = v; } });
    expect(storedToken()).toBe('');
    rememberToken('abc');
    expect(storedToken()).toBe('abc');
    expect(store[ADMIN_TOKEN_KEY]).toBe('abc');
  });
  it('sends the admin token as a header and surfaces a refusal', async () => {
    const f = respond(401, { detail: 'the admin token is missing or wrong' });
    vi.stubGlobal('fetch', f);
    await expect(saveSettings({ weather_union_city: 'Pune' }, 'tok')).rejects.toMatchObject({ status: 401, message: expect.stringContaining('admin token') });
    const init = f.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('PUT');
    expect((init.headers as Record<string, string>)['X-Admin-Token']).toBe('tok');
    expect(JSON.parse(init.body as string)).toEqual({ weather_union_city: 'Pune' });
  });
  it('treats a disabled live feed (503) as a state, not an error', async () => {
    vi.stubGlobal('fetch', respond(503, { detail: 'Rainfall feed is not enabled: set WEATHER_UNION_API_KEY and WEATHER_UNION_CITY in the environment' }));
    const feed = await getFeed();
    expect(feed.enabled).toBe(false);
    expect(feed.enabled === false && feed.reason).toContain('not enabled');
  });
  it('chat with no narrator comes back as an ApiError carrying the 503 message, never an invented reply', async () => {
    vi.stubGlobal('fetch', respond(503, { detail: 'AI narrator not connected' }));
    const err = await sendChat(1, 'why?', 3).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 503, message: 'AI narrator not connected' });
  });
});
