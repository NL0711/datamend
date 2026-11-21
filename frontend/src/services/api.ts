/**
 * DataMend — Typed REST API Service Client (the ORIGINAL dashboard contract, restored in slice S2b from commit ab3b0b3).
 *
 * Wired to the backend of slices S3a and S3b: stations, observations, anomalies, data sources, the simulator, the fault injector and the
 * stream settings. Still NOT BUILT on the server (they answer 404): /health*, /metrics, /inference, /feedback, /telemetry/process,
 * /upload; no view that is mounted calls them. A 404 on a mounted call is shown as an empty state (see isNotBuilt), anything else as the
 * server's own answer. Nothing here is mocked.
 */

import {
  AnomalyEvent,
  AnomalyEventDetail,
  AnomalyStats,
  FleetHealthSummary,
  InferenceResult,
  Observation,
  SimulationStatus,
  Station,
  StationHealthDetail,
  SystemMetrics,
  Phase3InferenceResult,
  StationHealthSnapshot,
  OperatorFeedbackPayload,
  OperatorFeedbackRecord,
} from '../types';
import { expireSession, storedToken } from '../validation/api';
import { apiDetail, needsSignIn } from './stream';

export const API_BASE_URL = '/api';

/** An HTTP answer that was not 2xx. `status` lets a view tell "not built yet" from a real failure. */
export class ServiceError extends Error {
  /** The server's own words (its `detail`), without the status line around them. */
  public detail: string;
  constructor(public status: number, message: string, detail = '') {
    super(message);
    this.detail = detail;
  }
}

/** One line for the screen: "409: the simulator is not the running source ..." for a server answer, else the error's text. */
export function errorText(err: unknown): string {
  if (err instanceof ServiceError) return err.detail ? `${err.status}: ${err.detail}` : err.message;
  return err instanceof Error ? err.message : String(err);
}

/** True when the server asked for an admin sign-in (401 or 403). */
export const isAuthError = (err: unknown): boolean => err instanceof ServiceError && needsSignIn(err.status);

/** True when the endpoint is simply not there (yet): 404, 405, 501, 502 or 503 (a dev proxy with nothing behind it answers 502). */
export function isNotBuilt(err: unknown): boolean {
  return err instanceof ServiceError && [404, 405, 501, 502, 503].includes(err.status);
}

/** fetch that carries the signed-in session (the server refuses anything else when sign-in is on). */
function request(url: string, init: RequestInit = {}): Promise<Response> {
  const t = storedToken();
  return fetch(url, { ...init, headers: { ...(t ? { 'X-Admin-Token': t } : {}), ...((init.headers as Record<string, string>) ?? {}) } }).then((res) => {
    if (res.status === 401 && t) expireSession();        // a session the server no longer accepts: go to the sign-in page instead of showing "failed"
    return res;
  });
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new ServiceError(res.status, `API error (${res.status} ${res.statusText}): ${errorBody}`, apiDetail(errorBody));
  }
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string; service: string; version: string }> {
  const res = await request(`${API_BASE_URL}/health`);
  return handleResponse(res);
}

export async function fetchStations(status?: string): Promise<{ items: Station[]; total: number }> {
  const url = status ? `${API_BASE_URL}/stations?status=${encodeURIComponent(status)}` : `${API_BASE_URL}/stations`;
  const res = await request(url);
  return handleResponse(res);
}

export async function fetchStation(stationId: string): Promise<Station> {
  const res = await request(`${API_BASE_URL}/stations/${encodeURIComponent(stationId)}`);
  return handleResponse(res);
}

export async function fetchObservations(params?: {
  station_id?: string;
  limit?: number;
  page?: number;
}): Promise<{ items: Observation[]; total: number }> {
  const query = new URLSearchParams();
  if (params?.station_id) query.append('station_id', params.station_id);
  if (params?.limit) query.append('limit', params.limit.toString());
  if (params?.page) query.append('page', params.page.toString());

  const res = await request(`${API_BASE_URL}/observations?${query.toString()}`);
  return handleResponse(res);
}

export async function fetchAnomalies(params?: {
  station_id?: string;
  severity?: string;
  classification?: string;
  limit?: number;
  offset?: number;
  page?: number;
  page_size?: number;
  fleet_balanced?: boolean;
}): Promise<{ items: AnomalyEvent[]; total: number; page?: number; page_size?: number }> {
  const query = new URLSearchParams();
  if (params?.station_id) query.append('station_id', params.station_id);
  if (params?.severity) query.append('severity', params.severity);
  if (params?.classification) query.append('classification', params.classification);
  if (params?.limit) query.append('limit', params.limit.toString());
  if (params?.page_size) query.append('page_size', params.page_size.toString());
  if (params?.page) query.append('page', params.page.toString());
  if (params?.fleet_balanced !== undefined) query.append('fleet_balanced', params.fleet_balanced.toString());

  const res = await request(`${API_BASE_URL}/anomalies?${query.toString()}`);
  return handleResponse(res);
}

export async function fetchAnomalyStats(hours: number = 24): Promise<AnomalyStats> {
  const res = await request(`${API_BASE_URL}/anomalies/stats?hours=${hours}`);
  return handleResponse(res);
}

export async function fetchAnomalyDetail(id: number): Promise<AnomalyEventDetail> {
  const res = await request(`${API_BASE_URL}/anomalies/${id}`);
  return handleResponse(res);
}

export async function fetchFleetHealth(): Promise<FleetHealthSummary> {
  const res = await request(`${API_BASE_URL}/health/fleet`);
  return handleResponse(res);
}

export async function fetchStationHealth(stationId: string): Promise<StationHealthDetail> {
  const res = await request(`${API_BASE_URL}/health/${encodeURIComponent(stationId)}`);
  return handleResponse(res);
}

export async function fetchMetrics(): Promise<SystemMetrics> {
  const res = await request(`${API_BASE_URL}/metrics`);
  return handleResponse(res);
}

export async function startSimulation(config?: {
  station_ids?: string[];
  interval_seconds?: number;
  noise_level?: number;
  scenario?: string;
}): Promise<SimulationStatus> {
  const res = await request(`${API_BASE_URL}/simulation/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config || {}),
  });
  return handleResponse(res);
}

export async function stopSimulation(): Promise<SimulationStatus> {
  const res = await request(`${API_BASE_URL}/simulation/stop`, {
    method: 'POST',
  });
  return handleResponse(res);
}

export async function getSimulationStatus(): Promise<SimulationStatus> {
  const res = await request(`${API_BASE_URL}/simulation/status`);
  return handleResponse(res);
}

export async function injectAnomaly(data: {
  anomaly_type: string;
  station_id?: string;
  parameter?: string;
  magnitude?: number;
  duration_steps?: number;
  decay?: boolean;
}): Promise<{ status?: string; success?: boolean; message: string; injection_id?: string }> {
  const res = await request(`${API_BASE_URL}/simulate/inject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return handleResponse(res);
}

export async function runInference(observation: {
  timestamp: string;
  station_id: string;
  temperature: number;
  pressure: number;
  humidity: number;
}): Promise<InferenceResult> {
  const res = await request(`${API_BASE_URL}/inference`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(observation),
  });
  return handleResponse(res);
}

export async function uploadCSV(file: File): Promise<{
  total_records: number;
  valid_records: number;
  anomalies_detected: number;
  processing_time_ms: number;
  results: InferenceResult[];
}> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await request(`${API_BASE_URL}/upload`, {
    method: 'POST',
    body: formData,
  });
  const data = await handleResponse<{
    total_rows: number;
    valid_rows: number;
    anomalies_detected: number;
    execution_time_ms: number;
  }>(res);
  return {
    total_records: data.total_rows,
    valid_records: data.valid_rows,
    anomalies_detected: data.anomalies_detected,
    processing_time_ms: data.execution_time_ms,
    results: [],
  };
}

// ---------------------------------------------------------------------------
// Data Source Management APIs
// ---------------------------------------------------------------------------
import { DataSourceListResponse, DataSourceStatus, DataSourceType } from '../types';

export async function fetchDataSources(): Promise<DataSourceListResponse> {
  const res = await request(`${API_BASE_URL}/data-sources`);
  return handleResponse(res);
}

export async function fetchActiveDataSourceStatus(): Promise<DataSourceStatus> {
  const res = await request(`${API_BASE_URL}/data-sources/status`);
  return handleResponse(res);
}

export async function selectDataSource(sourceType: DataSourceType): Promise<DataSourceStatus> {
  const res = await request(`${API_BASE_URL}/data-sources/select`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_type: sourceType }),
  });
  return handleResponse(res);
}

export async function fetchExternalWeatherPreview(): Promise<{
  success: boolean;
  provider: string;
  telemetry: any;
}> {
  const res = await request(`${API_BASE_URL}/data-sources/external/preview`);
  return handleResponse(res);
}

export async function configureExternalWeatherSource(config: {
  latitude: number;
  longitude: number;
  station_id?: string;
  station_name?: string;
}): Promise<DataSourceStatus> {
  const res = await request(`${API_BASE_URL}/data-sources/external/configure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  return handleResponse(res);
}

export async function ingestVirtualPhysicalPacket(payload: Record<string, any>): Promise<InferenceResult> {
  const res = await request(`${API_BASE_URL}/data-sources/physical/virtual-packet`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}

export async function processTelemetryReading(reading: {
  station_id: string;
  timestamp?: string;
  temperature_c?: number;
  pressure_hpa?: number;
  humidity_pct?: number;
  elevation_m?: number;
  persist?: boolean;
}): Promise<Phase3InferenceResult> {
  const res = await request(`${API_BASE_URL}/telemetry/process`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(reading),
  });
  return handleResponse(res);
}

export async function fetchStationPredictiveHealth(stationId: string): Promise<StationHealthSnapshot> {
  const res = await request(`${API_BASE_URL}/stations/${encodeURIComponent(stationId)}/health`);
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Stream settings (GET and PUT /api/settings, the `stream` block and the stream_* fields)
// ---------------------------------------------------------------------------
export interface StreamSettingsView {
  source_ids: string[];
  station_modes: string[];
  cities: string[];
  max_station_cap: number;
  interval_limits_seconds: Record<string, [number, number]>;
  active_source: string;
  active_source_origin?: string;
  station_set: { mode: string; city: string; cap: number; station_ids: string[]; mode_origin?: string };
  intervals_seconds: Record<string, number>;
  esp32: { station_ids: string[]; latitude: number | null; longitude: number | null };
  mqtt: { host: string; port: number; topic_prefix: string; username: string; password_set: boolean; tls: boolean };
  external_point: { latitude: number; longitude: number; station_id: string; station_name?: string } | null;
  status?: Record<string, unknown>;
}

export interface StreamSettingsAnswer {
  editing_enabled: boolean;
  stream: StreamSettingsView;
  saved?: string[];
  stream_error?: string;
  feed_error?: string;
}

export async function fetchStreamSettings(): Promise<StreamSettingsAnswer> {
  const res = await request(`${API_BASE_URL}/settings`);
  return handleResponse(res);
}

/** PUT only the fields given (stream_* names, plus `clear` to remove a saved override). A 422 carries the server's validation message. */
export async function saveStreamSettings(update: Record<string, unknown>): Promise<StreamSettingsAnswer> {
  const res = await request(`${API_BASE_URL}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  });
  return handleResponse(res);
}

// ---- the agent (PROTOTYPE; backend/app/api/agent.py) ----
export interface AgentStatus {
  connected: boolean;
  provider: string;
  model: string | null;
  reason?: string;
  prototype: boolean;
  note: string;
  max_tool_calls: number;
  token_budget: number;
  timeout_seconds: number;
}
export interface AgentProposal {
  id: number;
  task_id: string;
  action: string;
  station_id: string | null;
  run_id: number | null;
  row_ref: string | null;
  args: Record<string, unknown>;
  status: 'proposed' | 'accepted' | 'dismissed';
  review_id: number | null;
}
/** The facts of a live-feed comment (scope 'live'): what the agent read, from a snapshot fixed at perception. */
export interface AgentLiveFacts {
  station_id: string;
  feed_state_at_perception: string;
  feed_state_at_gate: string | null;
  source_id: string | null;
  cadence_seconds: number | null;
  last_reading_at: string | null;
  last_verdict: string | null;
  n_readings: number;
  detections_in_window: number;
  /** false when the list of checks that did not run is empty: readings keep no such list, so it is "not available", not "all checks ran" */
  checks_not_run_available?: boolean;
  model_score_present: boolean;
  model_score_label: string;
  snapshot: { cutoff_id: number; cutoff_timestamp: string | null; evidence_hash: string };
}
export interface AgentTaskResult {
  scope?: 'run' | 'live';
  live?: AgentLiveFacts | null;
  comment?: string | null;
  task_id: string;
  status: string;
  agent_connected: boolean;
  abstain_reason: string;
  explanation: { text: string; generated: boolean } | null;
  baseline_explanation?: string | null;
  baseline_generator?: string | null;
  selected: { action: string; args: Record<string, unknown>; rationale?: string } | null;
  rejected_alternatives: { action: string | null; reason: string }[];
  gate_result: { ok: boolean; reason: string } | null;
  outcome: { status: string; detail: string } | null;
  tool_call_count: number;
  model_id?: string | null;
  proposals: AgentProposal[];
}
export interface AgentEventRow {
  id: number;
  step: number;
  node: string;
  note: string;
  model_id: string | null;
  tool_calls: { tool: string; ok: boolean; error: string }[];
  decision: unknown;
  rejected_alternatives: { action: string | null; reason: string }[];
  gate_result: { ok: boolean; reason: string } | null;
  outcome: { status: string; detail: string } | null;
  time_utc: string;
}

export async function fetchAgentStatus(): Promise<AgentStatus> {
  return handleResponse(await request(`${API_BASE_URL}/agent/status`));
}
export async function askAgent(stationId: string, text: string, scope: 'run' | 'live' = 'run'): Promise<AgentTaskResult> {
  const res = await request(`${API_BASE_URL}/agent/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ station_id: stationId, request: text, scope }),
  });
  return handleResponse(res);
}
export async function fetchAgentEvents(taskId: string): Promise<{ task_id: string; events: AgentEventRow[] }> {
  return handleResponse(await request(`${API_BASE_URL}/agent/tasks/${encodeURIComponent(taskId)}/events`));
}
export async function fetchAgentProposals(stationId: string): Promise<{ proposals: AgentProposal[] }> {
  return handleResponse(await request(`${API_BASE_URL}/agent/proposals?station_id=${encodeURIComponent(stationId)}`));
}
export async function decideAgentProposal(id: number, decision: 'accept' | 'dismiss'): Promise<AgentProposal> {
  return handleResponse(await request(`${API_BASE_URL}/agent/proposals/${id}/${decision}`, { method: 'POST' }));
}

export async function submitOperatorFeedback(payload: OperatorFeedbackPayload): Promise<OperatorFeedbackRecord> {
  const res = await request(`${API_BASE_URL}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}
