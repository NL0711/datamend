// The calls of the step-by-step workflow, against a mocked fetch. Every one lives in api.ts; none touches a real server.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from './api';

const store = new Map<string, string>();
let fetchMock: ReturnType<typeof vi.fn>;
const reply = (body: unknown, status = 200) => ({ ok: status < 300, status, json: async () => body }) as unknown as Response;
const last = () => fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [string, RequestInit];
const headers = () => (last()[1].headers ?? {}) as Record<string, string>;
const body = () => JSON.parse(last()[1].body as string);

beforeEach(() => {
  store.clear();
  vi.stubGlobal('sessionStorage', { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => { store.set(k, v); }, removeItem: (k: string) => { store.delete(k); } });
  vi.stubGlobal('window', { location: { hash: '' } });
  fetchMock = vi.fn(async () => reply({ ok: true }));
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe('import', () => {
  it('reads the sources with GET', async () => {
    await api.getImportSources();
    expect(last()[0]).toBe('/api/pipeline/import/sources'); expect(last()[1].method).toBeUndefined();
  });
  it('posts provider, url and format, with no credential headers when none are set', async () => {
    await api.startImport('aws', 's3://bucket/key.csv', 'cwc');
    expect(last()[0]).toBe('/api/pipeline/import'); expect(last()[1].method).toBe('POST');
    expect(body()).toEqual({ provider: 'aws', url: 's3://bucket/key.csv', format: 'cwc' });
    expect(Object.keys(headers()).filter((k) => /aws|kaggle/i.test(k))).toEqual([]);
  });
  it('sends the AWS headers only for aws, never in the url or body', async () => {
    api.rememberImportAws({ accessKeyId: 'AKIAFAKEFAKEFAKE1234', secret: 'FAKE-SECRET', sessionToken: 'FAKE-TOKEN', region: 'ap-south-1' });
    await api.startImport('aws', 's3://b/k.csv', 'auto');
    expect(headers()).toMatchObject({ 'X-Aws-Access-Key-Id': 'AKIAFAKEFAKEFAKE1234', 'X-Aws-Secret-Access-Key': 'FAKE-SECRET', 'X-Aws-Session-Token': 'FAKE-TOKEN', 'X-Aws-Region': 'ap-south-1' });
    expect(last()[0]).not.toContain('FAKE'); expect(JSON.stringify(body())).not.toContain('FAKE');
    await api.startImport('kaggle', 'owner/data', 'isd');
    expect(headers()['X-Aws-Access-Key-Id']).toBeUndefined();
  });
  it('leaves the session token out when empty, and forgets credentials', async () => {
    api.rememberImportAws({ accessKeyId: 'AKIAFAKEFAKEFAKE1234', secret: 's', sessionToken: '', region: 'ap-south-1' });
    await api.startImport('aws', 's3://b/k', 'auto');
    expect(headers()['X-Aws-Session-Token']).toBeUndefined();
    api.rememberImportAws(null);
    expect(api.storedImportAws()).toBeNull();
  });
  it('sends no Kaggle credential on a first try (a public dataset needs none), not even a username', async () => {
    api.rememberKaggle({ username: 'someone', key: 'FAKE-KEY' });                       // the training form's account must not leak into an import
    api.rememberKaggleToken('KGAT_fakefakefake0001');                                    // a remembered token is not sent proactively either
    await api.startImport('kaggle', 'https://www.kaggle.com/datasets/o/d', 'auto');
    expect(last()[0]).toBe('/api/pipeline/import');
    expect(Object.keys(headers()).filter((k) => /kaggle/i.test(k))).toEqual([]);
    api.rememberKaggleToken(null);
  });
  it('sends the Kaggle token, and only the token, when one is passed for kaggle', async () => {
    await api.startImport('kaggle', 'owner/data', 'auto', 'KGAT_fakefakefake0001');
    expect(headers()).toMatchObject({ 'X-Kaggle-Token': 'KGAT_fakefakefake0001' });
    expect(headers()['X-Kaggle-Username']).toBeUndefined(); expect(headers()['X-Kaggle-Key']).toBeUndefined();
    expect(last()[0]).not.toContain('KGAT'); expect(JSON.stringify(body())).not.toContain('KGAT');
    await api.startImport('aws', 's3://b/k', 'auto', 'KGAT_fakefakefake0001');           // a token is never sent to the S3 provider
    expect(headers()['X-Kaggle-Token']).toBeUndefined();
  });
  it('remembers a Kaggle token for this tab only and can forget it', () => {
    expect(api.storedKaggleToken()).toBeNull();
    api.rememberKaggleToken('KGAT_fakefakefake0001');
    expect(api.storedKaggleToken()).toBe('KGAT_fakefakefake0001');
    api.rememberKaggleToken(null);
    expect(api.storedKaggleToken()).toBeNull();
  });
});

describe('explore', () => {
  it('lists tables, runs a query body, lists stations', async () => {
    await api.getExploreTables(); expect(last()[0]).toBe('/api/pipeline/explore/tables');
    await api.runQuery({ table: 'observations', filters: [{ column: 'value', op: '>', value: 1 }], limit: 500, run_id: 3 });
    expect(last()[0]).toBe('/api/pipeline/explore/query'); expect(last()[1].method).toBe('POST');
    expect(body()).toEqual({ table: 'observations', filters: [{ column: 'value', op: '>', value: 1 }], limit: 500, run_id: 3 });
    await api.getExploreStations(); expect(last()[0]).toBe('/api/pipeline/explore/stations');
  });
  it('asks for the profile and the default policy of a source, encoded', async () => {
    await api.getExploreProfile('cwc hourly'); expect(last()[0]).toBe('/api/pipeline/explore/profile?source=cwc%20hourly');
    await api.getDefaultPolicy('isd'); expect(last()[0]).toBe('/api/pipeline/clean/policy/default?source=isd');
  });
  it('sends the assistant message, the history as role and text only, and the run', async () => {
    await api.askAssistant('hello', [{ role: 'user', text: 'a' }, { role: 'assistant', text: 'b', reply: { reply: 'b', generator: 'baseline-rules', generated: true, label: 'x', table_spec: null, cleaning: null, why: [] } }], 4);
    expect(last()[0]).toBe('/api/pipeline/assistant');
    expect(body()).toEqual({ message: 'hello', history: [{ role: 'user', text: 'a' }, { role: 'assistant', text: 'b' }], run_id: 4 });
    await api.askAssistant('x');
    expect(body()).toEqual({ message: 'x', history: [], run_id: null });
  });
});

describe('cleaning', () => {
  it('plans with the source and the policy in the SERVER form, the override reason riding on the locked fill step', async () => {
    const policy = { steps: [{ id: 'fill_gaps', enabled: true, locked: true, params: { method: 'linear', max_gap_steps: 3 } }] };
    await api.planCleaning({ source: 'cwc', policy, override_reason: 'checked with the source' });
    expect(last()[0]).toBe('/api/pipeline/clean/plan'); expect(last()[1].method).toBe('POST');
    expect(body()).toEqual({ source: 'cwc', policy: { steps: [{ step: 'fill_gaps', method: 'linear', max_gap_steps: 3, override_reason: 'checked with the source' }] } });
    await api.planCleaning({ source: 'cwc' });
    expect(body()).toEqual({ source: 'cwc' });
  });
  it('lists proposals with only the filters given', async () => {
    await api.listCleanProposals(); expect(last()[0]).toBe('/api/pipeline/clean/proposals');
    await api.listCleanProposals({ status: 'pending', station: 'S 1', limit: 50 });
    expect(last()[0]).toBe('/api/pipeline/clean/proposals?status=pending&station=S+1&limit=50');
  });
  it('decides one proposal and applies', async () => {
    await api.decideCleanProposal(12, false);
    expect(last()[0]).toBe('/api/pipeline/clean/proposals/12/decide'); expect(body()).toEqual({ accept: false });
    await api.applyCleaning();
    expect(last()[0]).toBe('/api/pipeline/clean/apply'); expect(last()[1].method).toBe('POST');
  });
});

describe('validate and the model card', () => {
  it('checkJob posts an empty body by default and use_clean when asked', async () => {
    await api.checkJob(5); expect(last()[0]).toBe('/api/pipeline/jobs/5/check'); expect(body()).toEqual({});
    await api.checkJob(5, { use_clean: true }); expect(body()).toEqual({ use_clean: true });
    await api.checkJob(5, { start: '2024-01-01', end: '2024-02-01', use_clean: false }); expect(body()).toEqual({ start: '2024-01-01', end: '2024-02-01', use_clean: false });
  });
  it('reads the model card', async () => {
    await api.getModelCard(); expect(last()[0]).toBe('/api/pipeline/model-card');
  });
});
