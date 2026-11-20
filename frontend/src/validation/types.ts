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
  id: number; created_at: string | null; profile: Profile; source: 'upload' | 'live' | 'replay' | 'pipeline'; label: string | null;
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
  run: { id: number; profile: Profile; source: 'upload' | 'live' | 'replay' | 'pipeline'; synthetic: boolean };
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
  /** Present only when a trained model scored the row (a stored score or an exported file); never invented. */
  provider?: { model_id?: string; model_kind?: 'label_fusion' | 'stnet'; score?: number; flagged?: boolean; fault_scores?: Record<string, number>;
               ensemble_disagreement?: number; calibrated: boolean; label_tier: 'synthetic' | 'reviewer_labels' };
}

export interface ShadowSide { model_id: number; flagged: number; faults: number; faults_flagged: number; recall_on_reviewed: number | null;
                              false_alarms_labelled: number; false_alarms_flagged: number; genuine_extremes: number; genuine_extremes_flagged: number }
export interface ShadowRun {
  id: number; run_id: number; champion_id: number | null; challenger_id: number; created_at: string | null;
  report: { rows: number; reviewed_rows_used: number; note: string; challenger: ShadowSide; champion: ShadowSide | null; disagreements: number;
            only_challenger_flags: string[]; only_champion_flags: string[]; no_champion: boolean };
}
export interface ScoreSummary { run_id: number; model_id: number; rows: number; flagged: number; threshold: number; note: string }

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

export interface NarratorStatus { connected: boolean; message: string; implemented: boolean; host?: string; note?: string; provider?: 'gemini' | 'mcp-narrator' | null; model?: string }

export type Decision = 'confirmed_fault' | 'false_alarm' | 'genuine_extreme' | 'needs_followup';

export interface ReviewItem {
  id: number; run_id: number; row_ref: string; station_id: string; decision: Decision; note: string | null; reviewer: string | null;
  verdict_at_review: Verdict; created_at: string | null;
}

export interface QueueRow {
  id: number; run_id: number; run_label: string | null; synthetic: boolean; source: string; row_ref: string; station_id: string;
  time: string | null; verdict: Verdict; rule_score: number; severity: Severity; checks: string[]; review: ReviewItem | null;
}

export interface QueuePage { page: number; page_size: number; total: number; pages: number; status: string; rows: QueueRow[] }

export interface ReviewSummary {
  flagged_rows: number; reviewed_rows: number; unreviewed_rows: number; by_decision: Record<Decision, number>;
  by_check: Record<string, Record<Decision, number>>; truncated: boolean; caveat: string;
}

export interface ExplorerRow extends RowItem { intensity: number | null; accumulation: number | null; mm: number | null }
export interface ExplorerPage extends Omit<RowsPage, 'rows'> { rows: ExplorerRow[] }

export interface ContextRow {
  id: number; row_ref: string; time: string | null; intensity: number | null; accumulation: number | null; mm: number | null;
  verdict: Verdict; rule_score: number; checks: string[];
}
export interface RowContext { station_id: string; selected_id: number; rows: ContextRow[] }

export interface Overview {
  storage: string;
  runs: { total: number; completed: number; open_live: number; rejected_uploads: number };
  rows: { total: number; uploaded_or_live: number; synthetic: number };
  verdicts: Record<Verdict, number>; checks_fired: Record<string, number>;
  latest_run: RunSummary | null; live_run: RunSummary | null; note: string;
}

export interface LabOptions {
  label: string; faults: Record<Profile, string[]>; expected_check: Record<string, string>; stations: [number, number]; length: Record<Profile, [number, number]>;
}

export interface LabResult {
  run: RunFull; seed: number; note: string;
  injected: Array<{ fault: string; station_id: string; row_ref: string; time: string; expected_check: string; caught: boolean }>;
  summary: { injected: number; caught: number; other_flagged_rows: number; rows: number; label: string };
}

export interface PlaceInfo {
  latitude: number; longitude: number; cell: { row: number; col: number; lat: number; lon: number; grid: string };
  is_land: boolean | null; client_region: number | null; imd_subdivision: { status: string; reason: string };
}

export interface NearestImd { id: string; name: string; km: number }

export interface GaugeStation {
  station_id: string; city: string; place: string; latitude: number; longitude: number; device: string;
  cell: { row: number; col: number; lat: number; lon: number; grid: string } | null; is_land: boolean | null;
  nearest_imd?: NearestImd | null;
}

/** An Indian synoptic station from NOAA's station inventory (most are IMD's). NOT IMD's own list: that one is not public. */
export interface ImdStation {
  id: string; name: string; state: string | null; icao: string | null; latitude: number; longitude: number;
  elevation_m: number | null; first_data: string | null; last_data: string | null;
}
export interface ImdStationsResponse { source: string; count: number; with_data_2024_or_later: number; note: string; stations: ImdStation[] }

/** The RF25 land mask and client regions: one string per row (row 0 is the southernmost), one digit per cell (0 = not land). */
export interface MapLayers {
  grid: { lat0: number; lon0: number; step: number; n_lat: number; n_lon: number; row0: 'south' };
  rows: string[]; regions: number[]; held_out_regions: number[]; note: string;
}

/** One station's check -> flag -> audit cycle, from the stored runs and reviews. */
export interface StationCycle {
  station_id: string; place: string | null; city: string | null; latitude: number | null; longitude: number | null;
  position_source: 'catalogue' | 'upload' | 'imd' | null; nearest_imd: NearestImd | null;
  checked: number; runs: number; synthetic_rows: number; replay_rows: number; last_run_at: string | null; latest_run_id: number | null;
  flagged: number; suspect: number; uncertain: number; no_data: number;
  audited: number; unaudited: number; decisions: Record<Decision, number>; top_checks: Record<string, number>;
}
/** The NOAA ISD India replay: real station rainfall to Aug 2025, shown as a REPLAY, never as live. */
export interface ReplayStatus {
  state: 'idle' | 'running' | 'done' | 'failed'; started_at: string | null; finished_at: string | null; run_id: number | null;
  stations: { id: string; name: string | null; ok: boolean; totals: number; error: string | null }[]; stations_ok: number;
  message: string | null; default_stations: number; year: number; note: string;
  stored_run_id: number | null; stored_run_label: string | null; on_start: boolean;
}

/** The bulk-ingest and feedback loop (backend/app/api/pipeline.py). */
export interface PipelineStatus {
  observations: number; stations: number; jobs: number; proposals_pending: number; snapshots: number; champions: PipelineModel[];
  sources: string[]; max_upload_mb: number; not_implemented: string[];
}
export interface IngestJob {
  id: number; created_at: string | null; source: string; filename: string; sha256: string | null; size_bytes: number;
  status: 'queued' | 'running' | 'done' | 'failed'; rows_read: number; rows_inserted: number; rows_duplicate: number; rows_bad: number;
  stations: number; bad_samples: { row: number; problem: string }[]; assumptions: Record<string, string>; error: string | null;
  started_at: string | null; finished_at: string | null; run_id: number | null;
}
export interface PipelineProposal {
  id: number; run_id: number; row_ref: string; station_id: string; kind: string; original_mm: number | null; proposed_mm: number | null;
  text: string; generator: string; generated: true; label: string; status: 'pending' | 'accepted' | 'rejected';
  decided_by: string | null; decided_at: string | null; created_at: string | null;
}
export interface AuditItem {
  id: number; run_id: number; row_ref: string; station_id: string; inclusion_probability: number; weight: number;
  decision: 'ok' | 'missed_fault' | 'unsure' | null; note: string | null; reviewer: string | null; decided_at: string | null;
}
export interface AuditEstimate {
  run_id: number; drawn: number; decided: number; unsure: number; missed_faults: number; missed_fault_rate: number | null;
  interval_95: number[] | null; note: string;
}
export interface PipelineSnapshot {
  id: number; created_at: string | null; cut_day: string; n_rows: number; sha256: string;
  manifest: { excluded_years: number[]; skipped: Record<string, number>; label_counts: Record<string, number>; random_sample_rows: number; notes: string[] };
}
export interface PipelineModel {
  id: number; created_at: string | null; name: string; version: string; artifact_sha256: string | null; artifact_uri: string | null;
  snapshot_id: number | null; metrics: Record<string, unknown>; gate: { passed: boolean; checks: { rule: string; passed: boolean; detail: string }[] } | null;
  alias: 'champion' | 'challenger' | 'archived' | 'rejected'; notes: string | null; metrics_basis: string;
}

export interface TrainingJob {
  id: number; created_at: string | null; snapshot_id: number; target: 'local' | 'kaggle' | 'aws'; name: string; slug: string | null;
  status: 'running' | 'complete' | 'failed'; error: string | null; model_id: number | null; finished_at: string | null;
}
export interface LineageNode {
  id: string; kind: 'job' | 'run' | 'snapshot' | 'train' | 'model'; label: string; status: string; run_id?: number;
  facts: Record<string, string | number>; gate_checks?: { rule: string; passed: boolean; detail: string }[];
}
export interface Lineage { columns: string[]; nodes: LineageNode[]; edges: { from: string; to: string }[]; note: string }

export interface StationCycleResponse {
  storage: string; count: number; shown: number; truncated: boolean; positioned: number; positions_truncated: boolean;
  truncated_reviews: boolean; stations: StationCycle[]; note: string;
}

export interface SettingsState {
  editing_enabled: boolean; cities: string[]; accumulation_modes: string[]; interval_limits_seconds: [number, number];
  weather_union: {
    api_key_set: boolean; api_key_source: 'runtime' | 'environment' | 'unset'; city: string; city_source: string;
    poll_interval_seconds: number; poll_interval_source: string; accumulation_mode: string; accumulation_mode_source: string; enabled: boolean;
  };
  narrator: { url: string; url_source: string; token_set: boolean; token_source: string; connected: boolean };
  gemini?: { key_set: boolean; model: string; active: boolean };
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
