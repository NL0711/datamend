// Typed client of /api/validation and /api/rainfall. Errors carry the server's plain-language reason.
import type {
  Decision, Evidence, ExplanationItem, ExplorerPage, FeedStation, FeedStatus, FeedTestResult, ImdStationsResponse, LabOptions, LabResult,
  MapLayers, NarratorStatus, ReplayStatus, StationCycleResponse,
  AuditEstimate, AuditItem, IngestJob, Lineage, PipelineModel, PipelineProposal, PipelineSnapshot, PipelineStatus, TrainingJob,
  Overview, PlaceInfo, GaugeStation, Profile, QueuePage, ReviewItem, ReviewSummary, RowContext, RowDetail, RowsPage, RunFull, RunSummary,
  Series, SettingsState, SettingsUpdate,
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
  if (!res.ok) {
    // a session the server no longer accepts (expired, or the server restarted): drop it and go to the sign-in page
    if (res.status === 401 && typeof window !== 'undefined' && storedToken()) { rememberToken(''); window.location.hash = '#/login'; }
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
export const getExplorer = (id: number, query: string) => get<ExplorerPage>(`${V}/runs/${id}/rows?${query}`);
export const getContext = (id: number, rowId: number) => get<RowContext>(`${V}/runs/${id}/rows/${rowId}/context?before=6&after=6`);
export const getQueue = (query: string) => get<QueuePage>(`${V}/review/queue?${query}`);
export const getReviewSummary = () => get<ReviewSummary>(`${V}/review/summary`);
export const getReviews = (id: number, rowId: number) => get<{ reviews: ReviewItem[]; decisions: Decision[] }>(`${V}/runs/${id}/rows/${rowId}/reviews`);
export const getLabOptions = () => get<LabOptions>(`${V}/lab/options`);
export const locate = (lat: number, lon: number) => get<PlaceInfo>(`/api/places/locate?lat=${lat}&lon=${lon}`);
export const getGauges = (city?: string) =>
  get<{ cities: string[]; count: number; shown: number; stations: GaugeStation[] }>(`/api/places/stations${city ? `?city=${encodeURIComponent(city)}` : ''}`);

/** The whole gauge catalogue (the map draws every station). */
export const getAllGauges = () =>
  get<{ cities: string[]; count: number; shown: number; stations: GaugeStation[] }>('/api/places/stations?limit=600');
export const getImdStations = () => get<ImdStationsResponse>('/api/places/imd-stations');
export const getMapLayers = () => get<MapLayers>('/api/places/map');
export const getStationCycle = () => get<StationCycleResponse>(`${V}/stations`);

/** The NOAA ISD India replay (real station rainfall, labelled REPLAY). Reading is open; loading it needs the admin token. */
export const getReplayStatus = () => get<ReplayStatus>(`${V}/replay/isd`);
export const startReplay = (token: string) =>
  fetch(`${V}/replay/isd`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token } }).then((r) => json<ReplayStatus>(r));

/** The ingest and feedback loop (/api/pipeline). */
const P = '/api/pipeline';
export const getPipelineStatus = () => get<PipelineStatus>(`${P}/status`);
export const listJobs = () => get<{ jobs: IngestJob[] }>(`${P}/jobs`);
export async function ingestFile(file: File, source: string): Promise<IngestJob> {
  const fd = new FormData();
  fd.append('file', file); fd.append('source', source);
  return json<IngestJob>(await call(`${P}/ingest`, { method: 'POST', body: fd }));
}
export const checkJob = (id: number) => post<RunSummary>(`${P}/jobs/${id}/check`, {});
export const makeProposals = (runId: number) => post<{ created: number; proposals: PipelineProposal[] }>(`${P}/runs/${runId}/proposals`, {});
export const listProposals = (runId: number, status = 'pending') => get<{ proposals: PipelineProposal[]; note: string }>(`${P}/proposals?run_id=${runId}&status=${status}`);
export const decideProposal = (id: number, accept: boolean, reviewer?: string) => post<PipelineProposal>(`${P}/proposals/${id}/decide`, { accept, reviewer: reviewer || null });
export const drawAudit = (runId: number, n: number) => post<{ drawn: number; items: AuditItem[] }>(`${P}/runs/${runId}/audit`, { n });
export const listAudit = (runId: number) => get<{ items: AuditItem[]; estimate: AuditEstimate }>(`${P}/runs/${runId}/audit`);
export const decideAudit = (id: number, decision: string, reviewer?: string) => post<AuditItem>(`${P}/audit/${id}/decide`, { decision, reviewer: reviewer || null });
export const makeSnapshot = (cutDay: string, allowTestYears: boolean) => post<PipelineSnapshot>(`${P}/snapshots`, { cut_day: cutDay, allow_test_years: allowTestYears });
export const listSnapshots = () => get<{ snapshots: PipelineSnapshot[] }>(`${P}/snapshots`);
export async function downloadSnapshot(id: number): Promise<void> {
  const res = await call(`${P}/snapshots/${id}/data.jsonl`);
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url; a.download = `snapshot-${id}.jsonl`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
export const startTraining = (snapshotId: number, target: 'local' | 'kaggle') => post<TrainingJob>(`${P}/train`, { snapshot_id: snapshotId, target });
export const listTrainingJobs = () => get<{ jobs: TrainingJob[]; kaggle_configured: boolean }>(`${P}/train/jobs`);
export const refreshTrainingJob = (id: number) => post<TrainingJob>(`${P}/train/jobs/${id}/refresh`, {});
export const getLineage = () => get<Lineage>(`${P}/lineage`);
export const listModels = () => get<{ models: PipelineModel[]; not_implemented: string[] }>(`${P}/models`);
export const registerModel = (body: { name: string; version: string; metrics: Record<string, unknown>; snapshot_id?: number }) => post<PipelineModel>(`${P}/models`, body);
export const promoteModel = (id: number) => post<PipelineModel>(`${P}/models/${id}/promote`, {});
export const rollbackModel = (name: string) => post<PipelineModel>(`${P}/models/${encodeURIComponent(name)}/rollback`, {});

/** The admin token is kept for this browser tab only (sessionStorage). Reviews and Settings need it; reading never does. */
export const ADMIN_TOKEN_KEY = 'datamend-admin-token';
export const storedToken = () => (typeof sessionStorage === 'undefined' ? '' : sessionStorage.getItem(ADMIN_TOKEN_KEY) ?? '');
export const rememberToken = (v: string) => { if (typeof sessionStorage !== 'undefined') sessionStorage.setItem(ADMIN_TOKEN_KEY, v); };

/** Admin sign-in (api/auth). The session token is sent as X-Admin-Token like the older ADMIN_TOKEN. */
export interface Me { signed_in: boolean; email: string | null; login_enabled: boolean }
export const login = (email: string, password: string) => post<{ token: string; email: string; expires_in: number }>('/api/auth/login', { email, password });
export const getMe = (token: string) => fetch('/api/auth/me', { headers: { 'X-Admin-Token': token } }).then((r) => json<Me>(r));
export const logout = (token: string) => fetch('/api/auth/logout', { method: 'POST', headers: { 'X-Admin-Token': token } }).then(() => undefined);

export const postReview = (id: number, rowId: number, body: { decision: Decision; note?: string; reviewer?: string }, token: string) =>
  fetch(`${V}/runs/${id}/rows/${rowId}/review`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Admin-Token': token }, body: JSON.stringify(body) })
    .then((r) => json<ReviewItem>(r));

export const generateLab = (body: { profile: Profile; n_stations: number; length: number; faults: string[]; seed: number }) => post<LabResult>(`${V}/lab/generate`, body);

export const getSettings = () => get<SettingsState>('/api/settings');

const admin = (token: string) => ({ 'Content-Type': 'application/json', 'X-Admin-Token': token });

export const saveSettings = (body: SettingsUpdate, token: string) =>
  fetch('/api/settings', { method: 'PUT', headers: admin(token), body: JSON.stringify(body) }).then((r) => json<SettingsState>(r));

export const testFeed = (token: string) =>
  fetch('/api/settings/feed/test', { method: 'POST', headers: admin(token) }).then((r) => json<FeedTestResult>(r));

export const exportUrl = (id: number, kind: 'json' | 'csv') => `${V}/runs/${id}/export.${kind}`;

/** Downloads an export with the session attached (a plain link cannot send the header). */
export async function downloadExport(id: number, kind: 'json' | 'csv'): Promise<void> {
  const res = await call(exportUrl(id, kind));
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = url; a.download = `run-${id}.${kind}`;
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

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

/** The live feed answers 503 when it is not enabled; that is a state, not an error. */
export async function getFeed(): Promise<{ enabled: false; reason: string } | { enabled: true; status: FeedStatus; stations: FeedStation[] }> {
  const res = await call('/api/rainfall/stations');
  if (res.status === 503) return { enabled: false, reason: await readError(res) };
  const body = await json<{ status: FeedStatus; stations: FeedStation[] }>(res);
  return { enabled: true, status: body.status, stations: body.stations };
}
