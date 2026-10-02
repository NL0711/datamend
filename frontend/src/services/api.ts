/**
 * SkyGuard AI — Typed REST API Service Client.
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
} from '../types';

export const API_BASE_URL = '/api';

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const errorBody = await res.text().catch(() => '');
    throw new Error(`API error (${res.status} ${res.statusText}): ${errorBody}`);
  }
  return res.json();
}

export async function fetchHealth(): Promise<{ status: string; service: string; version: string }> {
  const res = await fetch(`${API_BASE_URL}/health`);
  return handleResponse(res);
}

export async function fetchStations(status?: string): Promise<{ items: Station[]; total: number }> {
  const url = status ? `${API_BASE_URL}/stations?status=${encodeURIComponent(status)}` : `${API_BASE_URL}/stations`;
  const res = await fetch(url);
  return handleResponse(res);
}

export async function fetchStation(stationId: string): Promise<Station> {
  const res = await fetch(`${API_BASE_URL}/stations/${encodeURIComponent(stationId)}`);
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

  const res = await fetch(`${API_BASE_URL}/observations?${query.toString()}`);
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

  const res = await fetch(`${API_BASE_URL}/anomalies?${query.toString()}`);
  return handleResponse(res);
}

export async function fetchAnomalyStats(hours: number = 24): Promise<AnomalyStats> {
  const res = await fetch(`${API_BASE_URL}/anomalies/stats?hours=${hours}`);
  return handleResponse(res);
}

export async function fetchAnomalyDetail(id: number): Promise<AnomalyEventDetail> {
  const res = await fetch(`${API_BASE_URL}/anomalies/${id}`);
  return handleResponse(res);
}

export async function fetchFleetHealth(): Promise<FleetHealthSummary> {
  const res = await fetch(`${API_BASE_URL}/health/fleet`);
  return handleResponse(res);
}

export async function fetchStationHealth(stationId: string): Promise<StationHealthDetail> {
  const res = await fetch(`${API_BASE_URL}/health/${encodeURIComponent(stationId)}`);
  return handleResponse(res);
}

export async function fetchMetrics(): Promise<SystemMetrics> {
  const res = await fetch(`${API_BASE_URL}/metrics`);
  return handleResponse(res);
}

export async function startSimulation(config?: {
  station_ids?: string[];
  interval_seconds?: number;
  noise_level?: number;
  scenario?: string;
}): Promise<SimulationStatus> {
  const res = await fetch(`${API_BASE_URL}/simulation/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config || {}),
  });
  return handleResponse(res);
}

export async function stopSimulation(): Promise<SimulationStatus> {
  const res = await fetch(`${API_BASE_URL}/simulation/stop`, {
    method: 'POST',
  });
  return handleResponse(res);
}

export async function getSimulationStatus(): Promise<SimulationStatus> {
  const res = await fetch(`${API_BASE_URL}/simulation/status`);
  return handleResponse(res);
}

export async function injectAnomaly(data: {
  anomaly_type: string;
  station_id?: string;
  parameter?: string;
  magnitude?: number;
  duration_steps?: number;
  decay?: boolean;
}): Promise<{ status: string; message: string; injection_id?: string }> {
  const res = await fetch(`${API_BASE_URL}/simulation/inject`, {
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
  const res = await fetch(`${API_BASE_URL}/inference`, {
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

  const res = await fetch(`${API_BASE_URL}/data/upload`, {
    method: 'POST',
    body: formData,
  });
  return handleResponse(res);
}

// ---------------------------------------------------------------------------
// Data Source Management APIs
// ---------------------------------------------------------------------------
import { DataSourceListResponse, DataSourceStatus, DataSourceType } from '../types';

export async function fetchDataSources(): Promise<DataSourceListResponse> {
  const res = await fetch(`${API_BASE_URL}/data-sources`);
  return handleResponse(res);
}

export async function fetchActiveDataSourceStatus(): Promise<DataSourceStatus> {
  const res = await fetch(`${API_BASE_URL}/data-sources/status`);
  return handleResponse(res);
}

export async function selectDataSource(sourceType: DataSourceType): Promise<DataSourceStatus> {
  const res = await fetch(`${API_BASE_URL}/data-sources/select`, {
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
  const res = await fetch(`${API_BASE_URL}/data-sources/external/preview`);
  return handleResponse(res);
}

export async function configureExternalWeatherSource(config: {
  latitude: number;
  longitude: number;
  station_id?: string;
  station_name?: string;
}): Promise<DataSourceStatus> {
  const res = await fetch(`${API_BASE_URL}/data-sources/external/configure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  return handleResponse(res);
}

export async function ingestVirtualPhysicalPacket(payload: Record<string, any>): Promise<InferenceResult> {
  const res = await fetch(`${API_BASE_URL}/data-sources/physical/virtual-packet`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}

