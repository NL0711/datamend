// Typed client of /api/validation and /api/rainfall. Errors carry the server's plain-language reason.
import type {
  Evidence, ExplanationItem, FeedStation, FeedStatus, FeedTestResult, NarratorStatus, RowDetail, RowsPage, RunFull, RunSummary, Series,
  SettingsState, SettingsUpdate,
} from './types';

const V = '/api/validation';

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const d = body?.detail;
    if (typeof d === 'string') return d;
    if (d && typeof d === 'object' && typeof d.reason === 'string') return d.reason;
    if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  } catch { /* not JSON */ }
  return `HTTP ${res.status}`;
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return res.json() as Promise<T>;
}

const get = <T>(url: string) => fetch(url).then((r) => json<T>(r));
const post = <T>(url: string, body: unknown) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then((r) => json<T>(r));

export const listRuns = () => get<{ storage: string; cap: number; runs: RunSummary[] }>(`${V}/runs`);
export const getRun = (id: number) => get<RunFull>(`${V}/runs/${id}`);
export const getRows = (id: number, query: string) => get<RowsPage>(`${V}/runs/${id}/rows?${query}`);
export const getRow = (id: number, rowId: number) => get<RowDetail>(`${V}/runs/${id}/rows/${rowId}`);
export const getEvidence = (id: number, rowId: number) =>
  get<{ schema: string; evidence: Evidence[] }>(`${V}/runs/${id}/rows/${rowId}/evidence`);
export const getSeries = (id: number, station: string, maxPoints = 1500) =>
  get<Series>(`${V}/runs/${id}/series?station=${encodeURIComponent(station)}&max_points=${maxPoints}`);
export const getExplanations = (id: number, rowId: number) =>
  get<{ explanations: ExplanationItem[] }>(`${V}/runs/${id}/rows/${rowId}/explanations`);
export const explain = (id: number, rowId: number, generator: 'baseline' | 'narrator', check?: string) =>
  post<{ explanations: ExplanationItem[] }>(`${V}/runs/${id}/rows/${rowId}/explain`, { generator, check: check ?? null });
export const getNarrator = () => get<NarratorStatus>(`${V}/narrator`);
export const getChat = (id: number) => get<{ messages: ExplanationItem[] }>(`${V}/runs/${id}/chat`);
export const sendChat = (id: number, message: string, rowId?: number) =>
  post<ExplanationItem>(`${V}/runs/${id}/chat`, { message, row_id: rowId ?? null });

export const getSettings = () => get<SettingsState>('/api/settings');

const admin = (token: string) => ({ 'Content-Type': 'application/json', 'X-Admin-Token': token });

export const saveSettings = (body: SettingsUpdate, token: string) =>
  fetch('/api/settings', { method: 'PUT', headers: admin(token), body: JSON.stringify(body) }).then((r) => json<SettingsState>(r));

export const testFeed = (token: string) =>
  fetch('/api/settings/feed/test', { method: 'POST', headers: admin(token) }).then((r) => json<FeedTestResult>(r));

export const exportUrl =(id: number, kind: 'json' | 'csv') => `${V}/runs/${id}/export.${kind}`;

export interface UploadForm {
  file: File; profile: 'reading' | 'daily'; accumulationMode?: string; timezone?: string; intervalMinutes?: string; synthetic: boolean;
}

export async function uploadRun(f: UploadForm): Promise<RunFull> {
  const fd = new FormData();
  fd.append('file', f.file);
  fd.append('profile', f.profile);
  if (f.accumulationMode) fd.append('accumulation_mode', f.accumulationMode);
  if (f.timezone) fd.append('timezone', f.timezone);
  if (f.intervalMinutes) fd.append('interval_minutes', f.intervalMinutes);
  fd.append('synthetic', String(f.synthetic));
  return json<RunFull>(await fetch(`${V}/runs`, { method: 'POST', body: fd }));
}

/** The live feed answers 503 when it is not enabled; that is a state, not an error. */
export async function getFeed(): Promise<{ enabled: false; reason: string } | { enabled: true; status: FeedStatus; stations: FeedStation[] }> {
  const res = await fetch('/api/rainfall/stations');
  if (res.status === 503) return { enabled: false, reason: await readError(res) };
  const body = await json<{ status: FeedStatus; stations: FeedStation[] }>(res);
  return { enabled: true, status: body.status, stations: body.stations };
}
