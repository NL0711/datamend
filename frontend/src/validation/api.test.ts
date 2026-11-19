import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from './api';
import { ADMIN_TOKEN_KEY, ApiError } from './api';

const store = new Map<string, string>();
let fetchMock: ReturnType<typeof vi.fn>;
let win: { location: { hash: string } };

const reply = (body: unknown, status = 200) =>
  ({ ok: status >= 200 && status < 300, status, json: async () => body, blob: async () => new Blob(['x']) }) as unknown as Response;
const lastCall = () => fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [string, RequestInit];
const headersOf = () => (lastCall()[1].headers ?? {}) as Record<string, string>;

beforeEach(() => {
  store.clear();
  vi.stubGlobal('sessionStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v); },
    removeItem: (k: string) => { store.delete(k); },
  });
  win = { location: { hash: '#/pipeline' } };
  vi.stubGlobal('window', win);
  fetchMock = vi.fn(async () => reply({ ok: true }));
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => { vi.unstubAllGlobals(); });

describe('call(): the admin token', () => {
  it('is sent as X-Admin-Token on get, post and upload', async () => {
    store.set(ADMIN_TOKEN_KEY, 'tok-1');
    await api.getPipelineStatus();
    expect(headersOf()['X-Admin-Token']).toBe('tok-1');
    await api.checkJob(1);
    expect(headersOf()['X-Admin-Token']).toBe('tok-1');
    expect(headersOf()['Content-Type']).toBe('application/json');
    await api.ingestFile(new File(['a'], 'a.csv'), 'imd');
    expect(headersOf()['X-Admin-Token']).toBe('tok-1');
  });
  it('sends no header when signed out', async () => {
    await api.getPipelineStatus();
    expect(headersOf()['X-Admin-Token']).toBeUndefined();
    await api.ingestFile(new File(['a'], 'a.csv'), 'imd');
    expect(headersOf()['X-Admin-Token']).toBeUndefined();
  });
  it('merges the caller headers with the token, and functions that pass their own token keep it', async () => {
    store.set(ADMIN_TOKEN_KEY, 'stored');
    await api.checkJob(1);
    expect(headersOf()).toEqual({ 'X-Admin-Token': 'stored', 'Content-Type': 'application/json' });
    // no public function passes its own X-Admin-Token through call(); the ones that take a token bypass it, so the explicit one is what is sent
    await api.startReplay('explicit');
    expect(headersOf()['X-Admin-Token']).toBe('explicit');
  });
});

describe('401 handling', () => {
  it('clears the stored token and goes to #/login when a token was stored', async () => {
    store.set(ADMIN_TOKEN_KEY, 'old');
    fetchMock.mockResolvedValueOnce(reply({ detail: 'session expired' }, 401));
    await expect(api.listJobs()).rejects.toMatchObject({ status: 401, message: 'session expired' });
    expect(store.get(ADMIN_TOKEN_KEY)).toBe('');
    expect(win.location.hash).toBe('#/login');
  });
  it('does not redirect on a 401 with no stored token', async () => {
    fetchMock.mockResolvedValueOnce(reply({ detail: 'sign in' }, 401));
    await expect(api.listJobs()).rejects.toBeInstanceOf(ApiError);
    expect(win.location.hash).toBe('#/pipeline');
  });
  it('does not touch window when there is none', async () => {
    vi.stubGlobal('window', undefined);
    store.set(ADMIN_TOKEN_KEY, 'old');
    fetchMock.mockResolvedValueOnce(reply({ detail: 'x' }, 401));
    await expect(api.listJobs()).rejects.toMatchObject({ status: 401 });
    expect(store.get(ADMIN_TOKEN_KEY)).toBe('old');
  });
  it('does not redirect for other failures', async () => {
    store.set(ADMIN_TOKEN_KEY, 'old');
    fetchMock.mockResolvedValueOnce(reply({ detail: 'boom' }, 500));
    await expect(api.listJobs()).rejects.toMatchObject({ status: 500 });
    expect(store.get(ADMIN_TOKEN_KEY)).toBe('old');
    expect(win.location.hash).toBe('#/pipeline');
  });
});

describe('ApiError reason', () => {
  it('carries a string detail, an object reason, a validation message, or the status', async () => {
    fetchMock.mockResolvedValueOnce(reply({ detail: 'plain' }, 400));
    await expect(api.listJobs()).rejects.toMatchObject({ message: 'plain', status: 400 });
    fetchMock.mockResolvedValueOnce(reply({ detail: { reason: 'gate failed' } }, 409));
    await expect(api.listJobs()).rejects.toMatchObject({ message: 'gate failed', status: 409 });
    fetchMock.mockResolvedValueOnce(reply({ detail: [{ msg: 'field required' }] }, 422));
    await expect(api.listJobs()).rejects.toMatchObject({ message: 'field required' });
    fetchMock.mockResolvedValueOnce({ ok: false, status: 502, json: async () => { throw new Error('no json'); } } as unknown as Response);
    await expect(api.listJobs()).rejects.toMatchObject({ message: 'HTTP 502' });
  });
});

describe('pipeline functions', () => {
  const bodyOf = () => JSON.parse(lastCall()[1].body as string);

  it('ingestFile posts FormData with file and source', async () => {
    const f = new File(['a,b'], 'rain.csv');
    await api.ingestFile(f, 'imd');
    const [url, init] = lastCall();
    expect(url).toBe('/api/pipeline/ingest');
    expect(init.method).toBe('POST');
    const fd = init.body as FormData;
    expect(fd.get('source')).toBe('imd');
    expect((fd.get('file') as File).name).toBe('rain.csv');
  });
  it('checkJob and makeProposals post an empty object to the right URL', async () => {
    await api.checkJob(7);
    expect(lastCall()[0]).toBe('/api/pipeline/jobs/7/check');
    expect(lastCall()[1].method).toBe('POST'); expect(bodyOf()).toEqual({});
    await api.makeProposals(3);
    expect(lastCall()[0]).toBe('/api/pipeline/runs/3/proposals'); expect(bodyOf()).toEqual({});
  });
  it('decideProposal sends accept and a null reviewer when none is given', async () => {
    await api.decideProposal(5, true);
    expect(lastCall()[0]).toBe('/api/pipeline/proposals/5/decide');
    expect(bodyOf()).toEqual({ accept: true, reviewer: null });
    await api.decideProposal(5, false, 'asha');
    expect(bodyOf()).toEqual({ accept: false, reviewer: 'asha' });
  });
  it('drawAudit and decideAudit', async () => {
    await api.drawAudit(2, 25);
    expect(lastCall()[0]).toBe('/api/pipeline/runs/2/audit'); expect(bodyOf()).toEqual({ n: 25 });
    await api.decideAudit(9, 'fault', 'asha');
    expect(lastCall()[0]).toBe('/api/pipeline/audit/9/decide');
    expect(bodyOf()).toEqual({ decision: 'fault', reviewer: 'asha' });
    await api.decideAudit(9, 'ok');
    expect(bodyOf()).toEqual({ decision: 'ok', reviewer: null });
  });
  it('makeSnapshot maps to snake_case', async () => {
    await api.makeSnapshot('2023-12-31', true);
    expect(lastCall()[0]).toBe('/api/pipeline/snapshots');
    expect(bodyOf()).toEqual({ cut_day: '2023-12-31', allow_test_years: true });
  });
  it('startTraining and refreshTrainingJob', async () => {
    await api.startTraining(4, 'kaggle');
    expect(lastCall()[0]).toBe('/api/pipeline/train'); expect(bodyOf()).toEqual({ snapshot_id: 4, target: 'kaggle' });
    await api.refreshTrainingJob(6);
    expect(lastCall()[0]).toBe('/api/pipeline/train/jobs/6/refresh'); expect(lastCall()[1].method).toBe('POST');
  });
  it('AWS training sends its options and the X-Aws headers, and refresh sends them only for aws jobs', async () => {
    api.rememberAws({ accessKeyId: 'AKIAFAKEFAKEFAKEFAKE', secret: 'FAKE-SECRET', sessionToken: '', region: 'ap-southeast-2', bucket: 'fake-bucket' });
    await api.startAwsTraining(4, { instanceType: 'g4dn.xlarge', maxMinutes: 45, spot: true });
    expect(lastCall()[0]).toBe('/api/pipeline/train');
    expect(bodyOf()).toEqual({ snapshot_id: 4, target: 'aws', instance_type: 'g4dn.xlarge', max_minutes: 45, spot: true });
    expect(headersOf()).toMatchObject({ 'X-Aws-Access-Key-Id': 'AKIAFAKEFAKEFAKEFAKE', 'X-Aws-Secret-Access-Key': 'FAKE-SECRET', 'X-Aws-Region': 'ap-southeast-2', 'X-Aws-Bucket': 'fake-bucket' });
    expect(headersOf()['X-Aws-Session-Token']).toBeUndefined();
    await api.refreshTrainingJob(9, 'aws');
    expect(headersOf()['X-Aws-Bucket']).toBe('fake-bucket');
    await api.refreshTrainingJob(9);
    expect(headersOf()['X-Aws-Bucket']).toBeUndefined();
    await api.startTraining(4, 'local');
    expect(headersOf()['X-Aws-Access-Key-Id']).toBeUndefined();
    api.rememberAws(null);
    expect(api.storedAws()).toBeNull();
  });
  it('model and lineage endpoints', async () => {
    await api.listModels();
    expect(lastCall()[0]).toBe('/api/pipeline/models'); expect(lastCall()[1].method).toBeUndefined();
    await api.promoteModel(8);
    expect(lastCall()[0]).toBe('/api/pipeline/models/8/promote'); expect(lastCall()[1].method).toBe('POST');
    await api.rollbackModel('stnet v2');
    expect(lastCall()[0]).toBe('/api/pipeline/models/stnet%20v2/rollback');
    await api.getLineage();
    expect(lastCall()[0]).toBe('/api/pipeline/lineage');
  });
  it('listProposals builds its query', async () => {
    await api.listProposals(3);
    expect(lastCall()[0]).toBe('/api/pipeline/proposals?run_id=3&status=pending');
  });
});

describe('downloads', () => {
  let anchor: { href: string; download: string; click: ReturnType<typeof vi.fn>; remove: ReturnType<typeof vi.fn> };
  let created: ReturnType<typeof vi.fn>, revoked: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    anchor = { href: '', download: '', click: vi.fn(), remove: vi.fn() };
    vi.stubGlobal('document', { createElement: vi.fn(() => anchor), body: { appendChild: vi.fn() } });
    created = vi.fn(() => 'blob:abc'); revoked = vi.fn();
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: created, revokeObjectURL: revoked }));
  });

  it('downloadExport attaches the token and saves run-<id>.<kind>', async () => {
    store.set(ADMIN_TOKEN_KEY, 'tok-2');
    await api.downloadExport(12, 'csv');
    expect(lastCall()[0]).toBe('/api/validation/runs/12/export.csv');
    expect(headersOf()['X-Admin-Token']).toBe('tok-2');
    expect(anchor.download).toBe('run-12.csv'); expect(anchor.href).toBe('blob:abc');
    expect(anchor.click).toHaveBeenCalled(); expect(revoked).toHaveBeenCalledWith('blob:abc');
  });
  it('downloadSnapshot attaches the token and saves snapshot-<id>.jsonl', async () => {
    store.set(ADMIN_TOKEN_KEY, 'tok-3');
    await api.downloadSnapshot(4);
    expect(lastCall()[0]).toBe('/api/pipeline/snapshots/4/data.jsonl');
    expect(headersOf()['X-Admin-Token']).toBe('tok-3');
    expect(anchor.download).toBe('snapshot-4.jsonl');
  });
  it('a failed download throws the reason and saves nothing', async () => {
    fetchMock.mockResolvedValueOnce(reply({ detail: 'not found' }, 404));
    await expect(api.downloadSnapshot(99)).rejects.toMatchObject({ status: 404, message: 'not found' });
    expect(created).not.toHaveBeenCalled();
  });
});
