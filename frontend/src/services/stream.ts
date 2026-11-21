// Pure helpers of the live stream (no React, no browser): parse a /ws/live frame, the reconnect delay, the words for the stream state,
// and small formatters. Everything here maps what the server sent and invents nothing: a value that is missing stays null.

export type StreamState = 'stopped' | 'running' | 'stale' | 'disconnected';
const STATES: StreamState[] = ['stopped', 'running', 'stale', 'disconnected'];

/** The `data` of a `{type:"status"}` frame (backend/app/stream/manager.py, StreamStatus.as_dict). */
export interface StreamStatusData {
  source_id: string | null;
  source_type: string | null;
  state: StreamState;
  last_reading_at: string | null;
  stale_since: string | null;
  stale_after_seconds: number | null;
  packet_count: number;
  last_error: string | null;
  last_error_at: string | null;
  expected_interval_seconds: number | null;
  subscribers: number;
}

/** A check that could not run, with the reason (the server's own words). */
export interface NotRunEntry { check: string; reason: string }

/** One reading as the stream sends it. Score, severity and the rest are present only when a check ran. */
export interface StreamObservation {
  timestamp: string;
  station_id: string;
  temperature: number | null;
  pressure: number | null;
  humidity: number | null;
  rain_mm: number | null;
  validation_status: string;
  checks_run: unknown[];
  not_run: NotRunEntry[];
  stored: boolean | null;
  anomaly_score?: number;
  is_anomaly?: boolean;
  severity?: string;
  classification?: string;
  reason?: string | null;
  is_fault?: boolean;
}

export type StreamFrame =
  | { kind: 'status'; status: StreamStatusData }
  | { kind: 'observation'; observation: StreamObservation };

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const str = (v: unknown): string | null => (typeof v === 'string' && v ? v : null);
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

function normalizeNotRun(v: unknown): NotRunEntry[] {
  if (!Array.isArray(v)) return [];
  return v.filter(isObj).map((n) => ({ check: str(n.check) ?? 'check', reason: str(n.reason) ?? 'no reason given' }));
}

/** A reading's `data` object -> StreamObservation, or null when it has no station or no time. */
export function normalizeObservation(raw: unknown, stationId?: unknown): StreamObservation | null {
  if (!isObj(raw)) return null;
  const station = str(raw.station_id) ?? str(stationId);
  const timestamp = str(raw.timestamp);
  if (!station || !timestamp) return null;
  const out: StreamObservation = {
    timestamp, station_id: station,
    temperature: num(raw.temperature), pressure: num(raw.pressure), humidity: num(raw.humidity), rain_mm: num(raw.rain_mm),
    validation_status: str(raw.validation_status) ?? 'NO_CHECKS',
    checks_run: Array.isArray(raw.checks_run) ? raw.checks_run : [],
    not_run: normalizeNotRun(raw.not_run),
    stored: typeof raw.stored === 'boolean' ? raw.stored : null,
  };
  const score = num(raw.anomaly_score);
  if (score !== null) out.anomaly_score = score;
  if (typeof raw.is_anomaly === 'boolean') out.is_anomaly = raw.is_anomaly;
  if (str(raw.severity)) out.severity = String(raw.severity);
  if (str(raw.classification)) out.classification = String(raw.classification);
  if (raw.reason !== undefined) out.reason = str(raw.reason);
  if (typeof raw.is_fault === 'boolean') out.is_fault = raw.is_fault;
  return out;
}

function normalizeStatus(raw: unknown): StreamStatusData | null {
  if (!isObj(raw) || !STATES.includes(raw.state as StreamState)) return null;
  return {
    source_id: str(raw.source_id), source_type: str(raw.source_type), state: raw.state as StreamState,
    last_reading_at: str(raw.last_reading_at), stale_since: str(raw.stale_since), stale_after_seconds: num(raw.stale_after_seconds),
    packet_count: num(raw.packet_count) ?? 0, last_error: str(raw.last_error), last_error_at: str(raw.last_error_at),
    expected_interval_seconds: num(raw.expected_interval_seconds), subscribers: num(raw.subscribers) ?? 0,
  };
}

/** One WebSocket message (text or already-parsed) -> a frame, or null for anything malformed or unknown. Never throws. */
export function parseFrame(message: unknown): StreamFrame | null {
  let raw: unknown = message;
  if (typeof message === 'string') {
    try { raw = JSON.parse(message); } catch { return null; }
  }
  if (!isObj(raw)) return null;
  if (raw.type === 'status') {
    const status = normalizeStatus(raw.data);
    return status ? { kind: 'status', status } : null;
  }
  if (raw.type === 'observation') {
    const observation = normalizeObservation(raw.data, raw.station_id);
    return observation ? { kind: 'observation', observation } : null;
  }
  return null;
}

/** Delay before reconnect attempt number `attempt` (0 first): 2.5 s, doubling, never more than 60 s. */
export function backoffDelay(attempt: number): number {
  const a = Number.isFinite(attempt) && attempt > 0 ? Math.floor(attempt) : 0;
  return Math.min(60_000, 2_500 * 2 ** Math.min(a, 10));
}

/** Append and keep the newest `max`. */
export function pushRolling<T>(buffer: T[], item: T, max: number): T[] {
  const next = [...buffer, item];
  return next.length > max ? next.slice(next.length - max) : next;
}

// ---- the words for the stream state ---------------------------------------------------------------------------------------
export type StreamTone = 'nominal' | 'warning' | 'critical' | 'neutral';
export interface StreamView {
  key: 'no_socket' | 'waiting' | 'stopped' | 'running' | 'stale' | 'source_down';
  label: string;
  detail: string;
  tone: StreamTone;
  /** Only RUNNING is a live stream; a stale one is shown as such, never as live. */
  live: boolean;
}

/** "14:03:09" from an ISO time, in UTC; null when it cannot be read. */
export function fmtUtc(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d.toISOString().slice(11, 19);
}

/** The state the dashboard shows, from the socket (open or not) and the last status frame (null until one arrived). */
export function describeStream(socketOpen: boolean, status: StreamStatusData | null): StreamView {
  if (!socketOpen) return { key: 'no_socket', label: 'DISCONNECTED', detail: 'No connection to the server stream (/ws/live). Sign in again if the session is old.', tone: 'neutral', live: false };
  if (!status) return { key: 'waiting', label: 'CONNECTING', detail: 'Connected; waiting for the stream state.', tone: 'neutral', live: false };
  switch (status.state) {
    case 'running':
      return { key: 'running', label: 'RUNNING', detail: status.source_id ? `Source ${status.source_id}` : 'Streaming', tone: 'nominal', live: true };
    case 'stale': {
      const since = fmtUtc(status.stale_since);
      return { key: 'stale', label: since ? `STALE since ${since} UTC` : 'STALE', detail: `No new reading${status.stale_after_seconds ? ` for more than ${Math.round(status.stale_after_seconds)} s` : ''}.`, tone: 'warning', live: false };
    }
    case 'disconnected':
      return { key: 'source_down', label: 'SOURCE DISCONNECTED', detail: status.last_error ?? 'The source stopped answering.', tone: 'critical', live: false };
    default:
      return { key: 'stopped', label: 'STOPPED', detail: 'No source is running.', tone: 'neutral', live: false };
  }
}

// ---- formatters ---------------------------------------------------------------------------------------------------------------
/** "12.3 unit"; null -> a dash. Never a default. */
export function fmtValue(v: number | null | undefined, digits: number, unit = ''): string {
  return v == null || Number.isNaN(v) ? '—' : `${v.toFixed(digits)}${unit}`;
}

/** Seconds as "12 s", "3 min", "2 h 5 min"; null -> a dash. */
export function fmtAge(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—';
  if (seconds < 90) return `${Math.round(seconds)} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  const h = Math.floor(seconds / 3600);
  return `${h} h ${Math.round((seconds - h * 3600) / 60)} min`;
}

/** 0..1 rule score as "35.0 %" (an uncalibrated rule score, not a probability); null -> a dash. */
export function fmtScore(score: number | null | undefined): string {
  return score == null || !Number.isFinite(score) ? '—' : `${(score * 100).toFixed(1)} %`;
}

/** "check: reason" lines for the checks that did not run. */
export function notRunLines(not_run: NotRunEntry[] | undefined): string[] {
  return (not_run ?? []).map((n) => `${n.check}: ${n.reason}`);
}

/** A check that ran (a verdict other than NO_CHECKS) for this reading. */
export const hasVerdict = (o: Pick<StreamObservation, 'validation_status'> | null | undefined): boolean =>
  !!o && o.validation_status !== 'NO_CHECKS' && o.validation_status !== '';

/** Badge words and tone of a raw verdict (OK, UNCERTAIN, SUSPECT, NO_DATA, NO_CHECKS, or the REST names QC_PASSED, QC_FLAGGED). */
export function verdictWords(status: string | null | undefined): { label: string; tone: StreamTone } {
  switch (status) {
    case 'SUSPECT': return { label: 'SUSPECT', tone: 'critical' };
    case 'UNCERTAIN': return { label: 'UNCERTAIN', tone: 'warning' };
    case 'QC_FLAGGED': return { label: 'FLAGGED', tone: 'warning' };
    case 'OK': case 'QC_PASSED': return { label: 'OK', tone: 'nominal' };
    case 'NO_DATA': return { label: 'NO DATA', tone: 'neutral' };
    default: return { label: 'NOT CHECKED', tone: 'neutral' };
  }
}

/** Verdict of a station's latest reading as a pin state: only a real verdict colours a pin, everything else is NO_DATA. */
export function pinState(o: Pick<StreamObservation, 'validation_status'> | null | undefined): 'OK' | 'UNCERTAIN' | 'SUSPECT' | 'NO_DATA' {
  const s = o?.validation_status;
  return s === 'OK' || s === 'UNCERTAIN' || s === 'SUSPECT' ? s : 'NO_DATA';
}

/** "key: value" lines for the scalar facts in a check's evidence object (numbers to 3 decimals at most; nested objects and the
 *  variable name are left out); at most `max` lines. */
export function evidenceFacts(evidence: Record<string, unknown> | undefined | null, max = 8): string[] {
  if (!isObj(evidence)) return [];
  const out: string[] = [];
  for (const [k, v] of Object.entries(evidence)) {
    if (k === 'variable' || v === null || v === undefined) continue;
    if (typeof v === 'number') out.push(`${k.replace(/_/g, ' ')}: ${Number.isInteger(v) ? v : Number(v.toFixed(3))}`);
    else if (typeof v === 'string' || typeof v === 'boolean') out.push(`${k.replace(/_/g, ' ')}: ${v}`);
    if (out.length >= max) break;
  }
  return out;
}

/** The text of an API error for the screen: the server's `detail` when it sent one (a string, or a FastAPI validation list), else the raw body. */
export function apiDetail(body: string): string {
  const text = body.trim();
  if (!text) return '';
  try {
    const j = JSON.parse(text);
    const d = isObj(j) ? j.detail : undefined;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      return d.map((x) => (isObj(x) ? `${Array.isArray(x.loc) ? x.loc.filter((p) => p !== 'body').join('.') : ''}${x.loc ? ': ' : ''}${String(x.msg ?? '')}` : String(x))).join('; ');
    }
    if (isObj(j) && typeof j.message === 'string') return j.message;
  } catch { /* not JSON: show it as sent */ }
  return text;
}

/** 401 and 403 mean "sign in as admin" (the writes need a session); everything else is the server's own answer. */
export const needsSignIn = (status: number | null | undefined): boolean => status === 401 || status === 403;
