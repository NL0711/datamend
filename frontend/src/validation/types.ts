// Types of the validation platform API (backend/app/api/validation.py). Mirrors docs/contracts/evidence-v1.schema.json.

export type Verdict = 'OK' | 'SUSPECT' | 'UNCERTAIN' | 'NO_DATA';
export type Severity = 'high' | 'medium' | 'low' | null;
export type Basis = 'measured' | 'assumed' | 'derived';
export type Profile = 'reading' | 'daily';

export interface Completeness { value: number | null; reason?: string; n?: number; expected?: number; basis?: string }

export interface Headline {
  rows: number; stations: number; completeness: Completeness;
  share_suspect: number | null; share_uncertain: number | null; share_no_data: number | null;
  checks_not_run: number; basis: string;
}

export interface NotRun { check: string; reason: string; station_id?: string }

export interface RunSummary {
  id: number; created_at: string | null; profile: Profile; source: 'upload' | 'live'; label: string | null;
  status: 'completed' | 'failed' | 'open'; error: string | null; n_rows: number; n_stations: number;
  duration_ms: number | null; synthetic: boolean; rain_day: string | null; storage: string; headline: Headline | null;
}

export interface StationSection {
  rows: number; verdicts: Record<string, number>; checks: Record<string, number>; completeness: Completeness;
}

export interface RunFull extends RunSummary {
  input_sha256: string | null; settings: Record<string, unknown>; platform_version: string; git_commit: string;
  not_run: NotRun[]; renamed_headers: Record<string, string>; issue_counts: Record<string, number>;
  report: {
    headline: Headline; verdicts: Record<string, number>; checks: Record<string, number>;
    stations: Record<string, StationSection>; score_note: string; method: string;
  };
}

export interface RowItem {
  id: number; row_ref: string; station_id: string; time: string | null; verdict: Verdict;
  rule_score: number; severity: Severity; checks: string[];
}

export interface RowsPage { page: number; page_size: number; total: number; pages: number; rows: RowItem[] }

export interface SeriesPoint {
  id: number; time: string; intensity: number | null; accumulation: number | null; mm: number | null;
  verdict: Verdict; rule_score: number; checks?: string[];
}

export interface Series {
  station_id: string; n_total: number; downsampled: boolean; max_points: number;
  points: SeriesPoint[]; flagged: SeriesPoint[];
}

export interface Tagged<T> { value: T; basis: Basis }

export interface Evidence {
  schema: 'evidence-v1';
  run: { id: number; profile: Profile; source: 'upload' | 'live'; synthetic: boolean };
  row: { id: number; row_ref: string; station_id: string; time: string | null; verdict: Verdict; rule_score: number; severity: Severity };
  check: string; layer: string; kind: 'fault' | 'uncertain' | 'info'; weight?: number; profile: string;
  time_basis: 'observed' | 'received'; reason: string;
  observed?: { value: number; unit: string; basis: Basis };
  threshold?: { value: number | string; why: string; basis: Basis };
  window?: Array<Record<string, unknown> & { basis: Basis }>;
  window_truncated?: boolean;
  neighbours?: Array<{ station_id: string; distance_km: number; wet: boolean; basis: Basis }>;
  history?: { n_wet_days: number; basis: 'derived' };
  tail_probability?: { value: number; basis: 'derived' };
  issue?: string; truncated?: boolean; next?: string;
}

export interface RowDetail {
  id: number; run_id: number; row_ref: string; station_id: string; time: string | null; verdict: Verdict;
  rule_score: number; severity: Severity; score_kind: string; original_row: Record<string, unknown>;
  input_issues: Array<{ code: string; message: string }>;
}

export interface ExplanationItem {
  id: number; run_id: number; result_id: number | null; row_ref: string | null; check: string | null; kind: 'explain' | 'chat';
  question: string | null; text: string; contributions: Array<{ check?: string; note?: string }>; generator: string; model_id: string;
  confidence: number | null; confidence_note: string | null; generated: true; label: string; created_at: string | null;
}

export interface NarratorStatus { connected: boolean; message: string; implemented: boolean; host?: string; note?: string }

export interface SettingsState {
  editing_enabled: boolean; cities: string[]; accumulation_modes: string[]; interval_limits_seconds: [number, number];
  weather_union: {
    api_key_set: boolean; api_key_source: 'runtime' | 'environment' | 'unset'; city: string; city_source: string;
    poll_interval_seconds: number; poll_interval_source: string; accumulation_mode: string; accumulation_mode_source: string; enabled: boolean;
  };
  narrator: { url: string; url_source: string; token_set: boolean; token_source: string; connected: boolean };
  feed_running: boolean;
  feed?: { stations: number; poll_interval_seconds: number; calls_used_today: number; calls_remaining_today: number; last_poll_at: string | null; last_error: string | null };
  saved?: string[]; feed_error?: string;
}

export interface SettingsUpdate {
  weather_union_api_key?: string; weather_union_city?: string; weather_union_poll_interval_seconds?: number;
  weather_union_accumulation_mode?: string; narrator_url?: string; narrator_token?: string; clear?: string[];
}

export interface FeedTestResult { ok: boolean; message: string; station_id: string; place?: string; status?: string }

export interface FeedStatus {
  source: string; stations: number; poll_interval_seconds: number; calls_used_today: number; calls_remaining_today: number;
  last_poll_at: string | null; last_error: string | null; accumulation_mode: string; caveats: string[];
}

export interface FeedStation {
  station_id: string; place: string; city: string; device: string; latitude: number; longitude: number;
  last_reading: { received_at: string; status: string; rain_intensity: number | null; rain_accumulation: number | null } | null;
  today: { rain_day: string; total_mm: number | null; n_readings: number; complete: boolean; units_confirmed: boolean; mode: string };
  quality: { assessment: Verdict; score: number; severity: Severity; score_kind: string; reasons: Array<{ check: string; detail: string }>; neighbours_used: number } | null;
}
