// Typed client of /api/validation and /api/rainfall. Errors carry the server's plain-language reason.
import type {
  Decision, Evidence, ExplanationItem, FeedStation, FeedStatus, FeedTestResult,
  MapLayers, McpState, NarratorStatus, NewMcpToken, StationCycleResponse,
  Overview, PlaceInfo, GaugeStation, QueuePage, ReviewItem, ReviewSummary, RowContext, RowDetail, RowsPage, RunFull, RunSummary,
  Series, SettingsState, SettingsUpdate,
} from './types';

import type { InsightsData } from './insights';

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
  if (!res.ok) {
    // a session the server no longer accepts (expired, or the server restarted): drop it and go to the sign-in page
    if (res.status === 401 && typeof window !== 'undefined' && storedToken()) expireSession();
    throw new ApiError(res.status, await readError(res));
  }
  return res.json() as Promise<T>;
}

/** fetch that carries the signed-in session on every request (the server refuses anything else). */
const call = (url: string, init: RequestInit = {}) => {
  const t = storedToken();
  return fetch(url, { ...init, headers: { ...(t ? { 'X-Admin-Token': t } : {}), ...((init.headers as Record<string, string>) ?? {}) } });
};

const get = <T>(url: string) => call(url).then((r) => json<T>(r));
const post = <T>(url: string, body: unknown) =>
  call(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then((r) => json<T>(r));

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

export const getOverview = () => get<Overview>(`${V}/overview`);
export const getContext = (id: number, rowId: number) => get<RowContext>(`${V}/runs/${id}/rows/${rowId}/context?before=6&after=6`);
export const getQueue = (query: string) => get<QueuePage>(`${V}/review/queue?${query}`);
export const getReviewSummary = () => get<ReviewSummary>(`${V}/review/summary`);
export const getReviews = (id: number, rowId: number) => get<{ reviews: ReviewItem[]; decisions: Decision[] }>(`${V}/runs/${id}/rows/${rowId}/reviews`);
export const locate = (lat: number, lon: number) => get<PlaceInfo>(`/api/places/locate?lat=${lat}&lon=${lon}`);

/** The whole gauge catalogue (the map draws every station). */
export const getAllGauges = () =>
  get<{ cities: string[]; count: number; shown: number; stations: GaugeStation[] }>('/api/places/stations?limit=600');
export const getMapLayers = () => get<MapLayers>('/api/places/map');
export const getInsights = (query: string) => get<InsightsData>(`${V}/insights?${query}`);
export const getStationCycle =() => get<StationCycleResponse>(`${V}/stations`);

/** The admin session token is kept in this browser (localStorage), so a refresh, a new tab or a restart does not sign you out; the server
 *  still expires it after 12 hours and keeps sessions in the database. Sign out removes it. */
export const ADMIN_TOKEN_KEY = 'datamend-admin-token';
export const storedToken = () => (typeof localStorage === 'undefined' ? '' : localStorage.getItem(ADMIN_TOKEN_KEY) ?? '');
export const rememberToken = (v: string) => { if (typeof localStorage !== 'undefined') localStorage.setItem(ADMIN_TOKEN_KEY, v); };

/** The server no longer accepts the stored session (expired, secret changed): forget it everywhere and show the sign-in page. Called by every API layer on a 401. */
export const SIGNED_OUT_EVENT = 'datamend:signed-out';
export function expireSession(): void {
  if (typeof localStorage !== 'undefined') { localStorage.setItem(ADMIN_TOKEN_KEY, ''); localStorage.removeItem('datamend-admin-email'); }
  if (typeof window !== 'undefined') { window.dispatchEvent(new Event(SIGNED_OUT_EVENT)); window.location.hash = '#/login'; }
}

/** Admin sign-in (api/auth). The session token is sent as X-Admin-Token like the older ADMIN_TOKEN. */
export interface Me { signed_in: boolean; email: string | null; login_enabled: boolean }
export const login = (email: string, password: string) => post<{ token: string; email: string; expires_in: number }>('/api/auth/login', { email, password });
export const getMe = (token: string) => fetch('/api/auth/me', { headers: { 'X-Admin-Token': token } }).then((r) => json<Me>(r));
export const logout = (token: string) => fetch('/api/auth/logout', { method: 'POST', headers: { 'X-Admin-Token': token } }).then(() => undefined);

export const postReview = (id: number, rowId: number, body: { decision: Decision; note?: string; reviewer?: string }, token: string) =>
  call(`${V}/runs/${id}/rows/${rowId}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token }, body: JSON.stringify(body) })
    .then((r) => json<ReviewItem>(r));

export const getSettings = () => get<SettingsState>('/api/settings');

const admin = (token: string) => ({ 'Content-Type': 'application/json', 'X-Admin-Token': token });

export const saveSettings = (body: SettingsUpdate, token: string) =>
  call('/api/settings', { method: 'PUT', headers: admin(token), body: JSON.stringify(body) }).then((r) => json<SettingsState>(r));

/** MCP access for other people's agents: the tokens (never the token itself) and the endpoint facts; making and revoking need the signed-in admin. */
export const getMcp = () => get<McpState>('/api/settings/mcp');
export const createMcpToken = (label: string) => post<NewMcpToken>('/api/settings/mcp/tokens', { label });
export const revokeMcpToken = (id: number) =>
  call(`/api/settings/mcp/tokens/${id}`, { method: 'DELETE' }).then((r) => json<{ revoked: boolean }>(r));

export const testFeed =(token: string) =>
  call('/api/settings/feed/test', { method: 'POST', headers: admin(token) }).then((r) => json<FeedTestResult>(r));

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
  return json<RunFull>(await call(`${V}/runs`, { method: 'POST', body: fd }));
}

/** Import one CSV or JSON file from a Kaggle dataset link. A public dataset needs no token; a private one answers 401 (ApiError.status). */
export interface KaggleForm { url: string; token?: string; profile: 'reading' | 'daily'; accumulationMode?: string; timezone?: string; intervalMinutes?: string; synthetic: boolean }
export const importKaggle = (f: KaggleForm) => post<RunFull>(`${V}/runs/kaggle`, {
  url: f.url, token: f.token || null, profile: f.profile, accumulation_mode: f.accumulationMode || null, timezone: f.timezone || null,
  interval_minutes: f.intervalMinutes ? Number(f.intervalMinutes) : null, synthetic: f.synthetic,
});

/** The live feed answers 503 when it is not enabled; that is a state, not an error. */
export async function getFeed(): Promise<{ enabled: false; reason: string } | { enabled: true; status: FeedStatus; stations: FeedStation[] }> {
  const res = await call('/api/rainfall/stations');
  if (res.status === 503) return { enabled: false, reason: await readError(res) };
  const body = await json<{ status: FeedStatus; stations: FeedStation[] }>(res);
  return { enabled: true, status: body.status, stations: body.stations };
}
