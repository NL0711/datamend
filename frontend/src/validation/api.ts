// Typed client of /api/validation and /api/rainfall. Errors carry the server's plain-language reason.
import type {
  Decision, Evidence, ExplanationItem, ImdStationsResponse, LabOptions, LabResult, MapLayers, NarratorStatus,
  AuditEstimate, AuditItem, IngestJob, Lineage, PipelineModel, PipelineProposal, PipelineSnapshot, PipelineStatus, TrainingJob,
  AssistantReply, ChatTurn, CleanApplyResult, CleanPlanBody, CleanPlanResult, CleanPolicy, CleanProposal, DatasetProfile, ExploreStations, ExploreTable,
  ImportedJob, ImportFormat, ImportProvider, ImportSources, ModelCard, QueryResult, QuerySpec,
  Profile, QueuePage, ReviewItem, ReviewSummary, RowContext, RowDetail, RowsPage, RunFull, RunSummary, Series, ScoreSummary, ShadowRun,
} from './types';
import { hintFromServer, policyFromServer, policyToServer } from './cleaningWire';

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
const post = <T>(url: string, body: unknown, extra: Record<string, string> = {}) =>
  call(url, { method: 'POST', headers: { 'Content-Type': 'application/json', ...extra }, body: JSON.stringify(body) }).then((r) => json<T>(r));

export const getRun = (id: number) => get<RunFull>(`${V}/runs/${id}`);
export const getRows = (id: number, query: string) => get<RowsPage>(`${V}/runs/${id}/rows?${query}`);
export const getRow = (id: number, rowId: number) => get<RowDetail>(`${V}/runs/${id}/rows/${rowId}`);
export const getEvidence = (id: number, rowId: number) =>
  get<{ schema: string; evidence: Evidence[]; evidence_hash?: string }>(`${V}/runs/${id}/rows/${rowId}/evidence`);
export const getSeries = (id: number, station: string, maxPoints = 1500) =>
  get<Series>(`${V}/runs/${id}/series?station=${encodeURIComponent(station)}&max_points=${maxPoints}`);
export const getExplanations = (id: number, rowId: number) =>
  get<{ explanations: ExplanationItem[] }>(`${V}/runs/${id}/rows/${rowId}/explanations`);
export const explain = (id: number, rowId: number, generator: 'baseline' | 'narrator', check?: string, evidenceHash?: string) =>
  post<{ explanations: ExplanationItem[] }>(`${V}/runs/${id}/rows/${rowId}/explain`, { generator, check: check ?? null, ...(evidenceHash ? { evidence_hash: evidenceHash } : {}) });
export const getNarrator = () => get<NarratorStatus>(`${V}/narrator`);
export const getChat = (id: number) => get<{ messages: ExplanationItem[] }>(`${V}/runs/${id}/chat`);
export const sendChat = (id: number, message: string, rowId?: number) =>
  post<ExplanationItem>(`${V}/runs/${id}/chat`, { message, row_id: rowId ?? null });

export const getContext = (id: number, rowId: number) => get<RowContext>(`${V}/runs/${id}/rows/${rowId}/context?before=6&after=6`);
export const getQueue = (query: string) => get<QueuePage>(`${V}/review/queue?${query}`);
export const getReviewSummary = () => get<ReviewSummary>(`${V}/review/summary`);
export const getReviews = (id: number, rowId: number) => get<{ reviews: ReviewItem[]; decisions: Decision[] }>(`${V}/runs/${id}/rows/${rowId}/reviews`);
export const getLabOptions = () => get<LabOptions>(`${V}/lab/options`);
export const getImdStations = () => get<ImdStationsResponse>('/api/places/imd-stations');
export const getMapLayers = () => get<MapLayers>('/api/places/map');

/** The ingest and feedback loop (/api/pipeline). */
const P = '/api/pipeline';
export const getPipelineStatus = () => get<PipelineStatus>(`${P}/status`);
export const listJobs = () => get<{ jobs: ImportedJob[] }>(`${P}/jobs`);
export async function ingestFile(file: File, source: string): Promise<IngestJob> {
  const fd = new FormData();
  fd.append('file', file); fd.append('source', source);
  return json<IngestJob>(await call(`${P}/ingest`, { method: 'POST', body: fd }));
}
export interface CheckOptions { start?: string; end?: string; use_clean?: boolean }
export const checkJob = (id: number, o: CheckOptions = {}) => post<RunSummary>(`${P}/jobs/${id}/check`, o);

/** Step 1, Import: a remote link (an Amazon S3 object or a Kaggle dataset), never a hand upload. The visitor's own credentials, when set, go as
 *  headers (never in the URL or the body) and only for the provider chosen. The server uses them for that request and does not store them. */
export const IMPORT_AWS_KEY = 'datamend-import-aws';
export interface ImportAwsAccount { accessKeyId: string; secret: string; sessionToken: string; region: string }
export const storedImportAws = (): ImportAwsAccount | null => {
  if (typeof sessionStorage === 'undefined') return null;
  try {
    const a = JSON.parse(sessionStorage.getItem(IMPORT_AWS_KEY) ?? 'null');
    return a && a.accessKeyId && a.secret && a.region ? { accessKeyId: a.accessKeyId, secret: a.secret, sessionToken: a.sessionToken ?? '', region: a.region } : null;
  } catch { return null; }
};
export const rememberImportAws = (a: ImportAwsAccount | null) => {
  if (typeof sessionStorage === 'undefined') return;
  if (a) sessionStorage.setItem(IMPORT_AWS_KEY, JSON.stringify(a)); else sessionStorage.removeItem(IMPORT_AWS_KEY);
};
/** A Kaggle API token for a PRIVATE dataset only. It is never sent on a first try: a public dataset needs none, and the server answers 428 when it
 *  needs one. After it worked it is kept for this tab (sessionStorage) so the next private dataset does not ask again. */
export const IMPORT_KAGGLE_TOKEN_KEY = 'datamend-import-kaggle-token';
export const storedKaggleToken = (): string | null => (typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(IMPORT_KAGGLE_TOKEN_KEY));
export const rememberKaggleToken = (t: string | null) => {
  if (typeof sessionStorage === 'undefined') return;
  if (t) sessionStorage.setItem(IMPORT_KAGGLE_TOKEN_KEY, t); else sessionStorage.removeItem(IMPORT_KAGGLE_TOKEN_KEY);
};
/** Headers of an import request. AWS credentials go only when the visitor saved them (a private bucket). Kaggle credentials never go here: pass the
 *  token to startImport after the server asked for one. */
export const importHeaders = (provider: ImportProvider): Record<string, string> => {
  if (provider === 'kaggle') return {};
  const a = storedImportAws();
  if (!a) return {};
  return { 'X-Aws-Access-Key-Id': a.accessKeyId, 'X-Aws-Secret-Access-Key': a.secret, ...(a.sessionToken ? { 'X-Aws-Session-Token': a.sessionToken } : {}), 'X-Aws-Region': a.region };
};
export const getImportSources = () => get<ImportSources>(`${P}/import/sources`);
export const startImport = (provider: ImportProvider, url: string, format: ImportFormat, kaggleToken?: string) =>
  post<ImportedJob>(`${P}/import`, { provider, url, format }, { ...importHeaders(provider), ...(provider === 'kaggle' && kaggleToken ? { 'X-Kaggle-Token': kaggleToken } : {}) });

/** Step 2, Explore and clean. */
export const getExploreTables = () => get<{ tables: ExploreTable[] }>(`${P}/explore/tables`);
export const runQuery = (spec: QuerySpec) => post<QueryResult>(`${P}/explore/query`, spec);
export const getExploreStations = () => get<ExploreStations>(`${P}/explore/stations`);
export const getExploreProfile = (source: string) => get<DatasetProfile>(`${P}/explore/profile?source=${encodeURIComponent(source)}`);
export const askAssistant = async (message: string, history: ChatTurn[] = [], runId?: number | null): Promise<AssistantReply> => {
  const r = await post<AssistantReply>(`${P}/assistant`, { message, history: history.map((t) => ({ role: t.role, text: t.text })), run_id: runId ?? null });
  const hint = r?.cleaning?.plan_hint;
  return r && r.cleaning && hint ? { ...r, cleaning: { ...r.cleaning, plan_hint: hintFromServer(hint) as typeof hint } } : r;     // add the editor's form of the advised policy
};
/** The server wraps the default policy ({source, policy, profile}) and writes steps as {step, ...}; the editor wants {id, enabled, params}. */
export const getDefaultPolicy = async (source: string): Promise<CleanPolicy> => {
  const r = await get<{ policy?: unknown; profile?: Partial<DatasetProfile> }>(`${P}/clean/policy/default?source=${encodeURIComponent(source)}`);
  return policyFromServer(r?.policy, r?.profile);
};
export const planCleaning = async (body: CleanPlanBody): Promise<CleanPlanResult> => {
  const { policy, override_reason, ...rest } = body;
  const res = await post<CleanPlanResult & { profile?: Partial<DatasetProfile> }>(`${P}/clean/plan`, { ...rest, ...(policy ? { policy: policyToServer(policy, override_reason) } : {}) });
  return res && res.policy ? { ...res, policy: policyFromServer(res.policy, res.profile) } : res;
};
export const listCleanProposals = (o: { status?: string; station?: string; limit?: number } = {}) => {
  const q = new URLSearchParams();
  if (o.status) q.set('status', o.status);
  if (o.station) q.set('station', o.station);
  if (o.limit) q.set('limit', String(o.limit));
  const s = q.toString();
  return get<{ proposals: CleanProposal[] }>(`${P}/clean/proposals${s ? `?${s}` : ''}`);
};
export const decideCleanProposal = (id: number, accept: boolean) => post<CleanProposal>(`${P}/clean/proposals/${id}/decide`, { accept });
/** The server counts accepted proposals as accepted, imputed_values and excluded_values; the page reads accepted, interpolated and excluded. */
export const applyCleaning = async (): Promise<CleanApplyResult> => {
  const r = await post<{ accepted?: number; imputed_values?: number; excluded_values?: number }>(`${P}/clean/apply`, {});
  return { accepted: r?.accepted ?? 0, interpolated: r?.imputed_values ?? 0, excluded: r?.excluded_values ?? 0 };
};

/** Step 6, Anomalies: how a flag is made. */
export const getModelCard = () => get<ModelCard>(`${P}/model-card`);
export const makeProposals = (runId: number, generator: 'baseline-rules' | 'ai' = 'baseline-rules') =>
  post<{ created: number; proposals: PipelineProposal[]; skipped_over_limit?: number; stopped?: string | null }>(`${P}/runs/${runId}/proposals`, { generator });
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
/** The visitor's own Kaggle account, kept for this browser tab only (sessionStorage, like the admin token). It is sent as two headers on the
 *  Kaggle start and check requests, and nowhere else. The server uses it for that request and does not store it. */
export const KAGGLE_USER_KEY = 'datamend-kaggle-username';
export const KAGGLE_SECRET_KEY = 'datamend-kaggle-key';
export interface KaggleAccount { username: string; key: string }
export const storedKaggle = (): KaggleAccount | null => {
  if (typeof sessionStorage === 'undefined') return null;
  const username = sessionStorage.getItem(KAGGLE_USER_KEY) ?? '', key = sessionStorage.getItem(KAGGLE_SECRET_KEY) ?? '';
  return username && key ? { username, key } : null;
};
export const rememberKaggle = (a: KaggleAccount | null) => {
  if (typeof sessionStorage === 'undefined') return;
  if (a) { sessionStorage.setItem(KAGGLE_USER_KEY, a.username); sessionStorage.setItem(KAGGLE_SECRET_KEY, a.key); }
  else { sessionStorage.removeItem(KAGGLE_USER_KEY); sessionStorage.removeItem(KAGGLE_SECRET_KEY); }
};
const kaggleHeaders = (): Record<string, string> => {
  const a = storedKaggle();
  return a ? { 'X-Kaggle-Username': a.username, 'X-Kaggle-Key': a.key } : {};
};
/** The visitor's own AWS account for the AWS training target, kept for this browser tab only (sessionStorage). Sent as X-Aws-* headers on the AWS
 *  start and check requests, and nowhere else; the server uses it for that request and does not store it. */
export const AWS_ACCOUNT_KEY = 'datamend-aws-account';
export interface AwsAccount { accessKeyId: string; secret: string; sessionToken: string; region: string; bucket: string }
export const AWS_INSTANCE_TYPES = [
  { id: 't3.small', gpu: false }, { id: 't3.medium', gpu: false }, { id: 'c6i.large', gpu: false },
  { id: 'g4dn.xlarge', gpu: true }, { id: 'g5.xlarge', gpu: true },
] as const;
export const storedAws = (): AwsAccount | null => {
  if (typeof sessionStorage === 'undefined') return null;
  try {
    const a = JSON.parse(sessionStorage.getItem(AWS_ACCOUNT_KEY) ?? 'null');
    return a && a.accessKeyId && a.secret && a.region && a.bucket ? { accessKeyId: a.accessKeyId, secret: a.secret, sessionToken: a.sessionToken ?? '', region: a.region, bucket: a.bucket } : null;
  } catch { return null; }
};
export const rememberAws = (a: AwsAccount | null) => {
  if (typeof sessionStorage === 'undefined') return;
  if (a) sessionStorage.setItem(AWS_ACCOUNT_KEY, JSON.stringify(a)); else sessionStorage.removeItem(AWS_ACCOUNT_KEY);
};
const awsHeaders = (): Record<string, string> => {
  const a = storedAws();
  if (!a) return {};
  return { 'X-Aws-Access-Key-Id': a.accessKeyId, 'X-Aws-Secret-Access-Key': a.secret, ...(a.sessionToken ? { 'X-Aws-Session-Token': a.sessionToken } : {}),
    'X-Aws-Region': a.region, 'X-Aws-Bucket': a.bucket };
};
export interface AwsOptions { instanceType: string; maxMinutes: number; spot: boolean }
export const startTraining = (snapshotId: number, target: 'local' | 'kaggle') =>
  post<TrainingJob>(`${P}/train`, { snapshot_id: snapshotId, target }, target === 'kaggle' ? kaggleHeaders() : {});
export const startAwsTraining = (snapshotId: number, o: AwsOptions) =>
  post<TrainingJob & { gpu_note?: string }>(`${P}/train`, { snapshot_id: snapshotId, target: 'aws', instance_type: o.instanceType, max_minutes: o.maxMinutes, spot: o.spot }, awsHeaders());
export const listTrainingJobs = () =>
  get<{ jobs: TrainingJob[]; kaggle_configured: boolean; byo_supported?: boolean; aws_supported?: boolean; aws_configured?: boolean }>(`${P}/train/jobs`);
export const refreshTrainingJob = (id: number, target: 'kaggle' | 'aws' = 'kaggle') =>
  post<TrainingJob>(`${P}/train/jobs/${id}/refresh`, {}, target === 'aws' ? awsHeaders() : kaggleHeaders());
export const getLineage = () => get<Lineage>(`${P}/lineage`);
export const listModels = () => get<{ models: PipelineModel[]; not_implemented: string[] }>(`${P}/models`);
export const registerModel = (body: { name: string; version: string; metrics: Record<string, unknown>; snapshot_id?: number }) => post<PipelineModel>(`${P}/models`, body);
export const promoteModel = (id: number, requireShadow = false) => post<PipelineModel>(`${P}/models/${id}/promote${requireShadow ? '?require_shadow=true' : ''}`, {});
export const scoreRun = (runId: number, modelId: number) => post<ScoreSummary>(`${P}/runs/${runId}/score`, { model_id: modelId });
export const shadowRun = (runId: number, challengerId: number) => post<ShadowRun>(`${P}/runs/${runId}/shadow`, { model_id: challengerId });
export const getModelShadow = (id: number) => get<{ shadow: ShadowRun | null }>(`${P}/models/${id}/shadow`);
export const rollbackModel = (name: string) => post<PipelineModel>(`${P}/models/${encodeURIComponent(name)}/rollback`, {});

/** The admin token is kept for this browser tab only (sessionStorage). Imports, cleaning and reviews need it; reading never does. */
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
