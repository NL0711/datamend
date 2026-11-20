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

export interface ContextRow {
  id: number; row_ref: string; time: string | null; intensity: number | null; accumulation: number | null; mm: number | null;
  verdict: Verdict; rule_score: number; checks: string[];
}
export interface RowContext { station_id: string; selected_id: number; rows: ContextRow[] }

export interface LabOptions {
  label: string; faults: Record<Profile, string[]>; expected_check: Record<string, string>; stations: [number, number]; length: Record<Profile, [number, number]>;
}

export interface LabResult {
  run: RunFull; seed: number; note: string;
  injected: Array<{ fault: string; station_id: string; row_ref: string; time: string; expected_check: string; caught: boolean }>;
  summary: { injected: number; caught: number; other_flagged_rows: number; rows: number; label: string };
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
/** The import step (a remote link, never a hand upload): what the server accepts, and the job it starts. */
export type ImportProvider = 'aws' | 'kaggle';
export type ImportFormat = 'auto' | 'cwc' | 'isd';
export interface ImportSources {
  providers: { id: ImportProvider; label: string; accepts: string[]; credentials: string; examples: string[] }[];
  formats: { id: string; label?: string }[];
  limits: { max_mb: number };
}
export type ImportedJob = IngestJob & { provider?: ImportProvider; origin?: string; job_ids?: number[] };

/** The explore step: tables, a query spec, and its answer. */
export interface ExploreColumn { name: string; type: string; description?: string }
export interface ExploreTable { id: string; label: string; description: string; columns: ExploreColumn[] }
export type FilterOp = '=' | '!=' | '>' | '>=' | '<' | '<=' | 'contains' | 'in' | 'is_null' | 'not_null';
export interface QueryFilter { column: string; op: FilterOp | string; value?: unknown }
export interface QueryAggregate { fn: string; column: string; as: string }
export interface QueryOrder { column: string; dir: 'asc' | 'desc' }
export interface QuerySpec {
  table: string; columns?: string[]; filters?: QueryFilter[]; group_by?: string[]; aggregates?: QueryAggregate[];
  order_by?: QueryOrder[]; limit?: number; run_id?: number | null;
}
export type Cell = string | number | boolean | null;
export interface QueryResult { columns: { name: string; type: string }[]; rows: Cell[][]; total: number; truncated: boolean; spec: QuerySpec }
export interface ExploreStation {
  station_key: string; name: string | null; state: string | null; district: string | null; latitude: number | null; longitude: number | null; located: boolean;
  rf25: { row: number; col: number; lat: number; lon: number; grid: string; is_land: boolean | null; client_region: number | null } | null;
  nearest_imd: { id: string; name: string; km: number } | null; n_observations: number; first: string | null; last: string | null;
}
export interface ExploreStations { stations: ExploreStation[]; located: number; unlocated: number; note: string }

/** The assistant (rule-based baseline now, the AI narrator when connected). Its text is always generated. */
export interface AssistantReply {
  reply: string; generator: 'baseline-rules' | 'mcp-narrator'; generated: true; label: string;
  table_spec: QuerySpec | null; cleaning: { plan_hint: Record<string, unknown> | string | null } | null; why: string[];
}
export interface ChatTurn { role: 'user' | 'assistant'; text: string; reply?: AssistantReply }

/** Cleaning: proposals are derived suggestions and change nothing until accepted and applied. */
export interface CleanPlanResult { created: number; skipped: { station_key: string; reason: string; count: number }[]; proposals: CleanProposal[]; policy?: CleanPolicy }
/** What the dataset is (detected by the server, never guessed silently) and the cleaning policy built from it. */
export interface DatasetProfile {
  parameter: string; kind: 'intermittent_accumulation' | 'continuous_state' | 'unknown'; reports_zero_values: boolean;
  cadence: { median_minutes: number | null; regular: boolean }; units: string | null; valid_range: [number | null, number | null] | null;
  missing_codes: (string | number)[]; evidence: string[]; notes?: string | null;
}
export interface PolicyStep { id: string; enabled: boolean; params: Record<string, unknown>; locked?: boolean; locked_reason?: string }
export interface CleanPolicy { steps: PolicyStep[] }
export interface CleanPlanBody { source: string; policy?: CleanPolicy; override_reason?: string; method?: string; max_gap_hours?: number }
export interface CleanProposal {
  id: number; station_key: string; at: string; kind: 'interpolate' | 'exclude'; original: number | null; proposed: number | null; method: string;
  why: string; neighbours: { at: string; value: number | null }[]; basis: 'derived'; status: 'pending' | 'accepted' | 'rejected' | string;
}
export interface CleanApplyResult { accepted: number; excluded: number; interpolated: number }

/** The model card: how a flag is made, as the server describes it. */
export interface ModelCard {
  method: string;
  checks: { name: string; profile: string; layer: string; kind: string; weight: number | null; needs: string | string[] | null; threshold_note: string | null }[];
  champion: { id: number; name: string; version: string; weights: Record<string, number> | null; metrics_basis: string; trained_from_snapshot: number | null } | null;
  explanation: { generator: string; narrator_connected: boolean; note: string };
  flags_how: string[]; not_implemented: string[];
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

