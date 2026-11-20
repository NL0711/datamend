// The cleaning policy editor's logic and the words taken from the dataset profile (pure, unit-tested in cleaning.test.ts).
// The server proposes the default policy from the profile; this module keeps a step locked when the server (or the profile) says it must be,
// and only lets it be switched on with an explicit, recorded override reason. Labels come from the profile, so the same screen reads right
// for rainfall, temperature or humidity.
import type { AssistantReply, CleanPlanBody, CleanPolicy, DatasetProfile, PolicyStep } from './types';

export const LOCK_REASON_NO_ZEROS = 'this dataset lists only non-zero values, so a missing value may be a dry value; interpolating would invent rain';
export const MIN_REASON_CHARS = 10;      // the server refuses a shorter override reason (pipeline/cleaning.py fill_decision)

export interface Override { ack: boolean; reason: string }
export const NO_OVERRIDE: Override = { ack: false, reason: '' };

export const isFillStep = (s: PolicyStep) => /fill|gap|interpol/.test(s.id);
export const overrideValid = (o: Override) => o.ack && o.reason.trim().length >= MIN_REASON_CHARS;

/** True when the profile says the dataset leaves out its zero (dry) values: a missing value may then be a real zero. */
export const omitsZeros = (p: DatasetProfile | null | undefined) => !!p && p.kind === 'intermittent_accumulation' && !p.reports_zero_values;

export function stepTitle(id: string): string {
  const t = id.replace(/_/g, ' ');
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Makes sure the profile's rule holds even if the server's default did not carry it: gap filling of a dataset that omits zeros is off and locked. */
export function applyProfileDefaults(policy: CleanPolicy, profile: DatasetProfile | null | undefined): CleanPolicy {
  if (!omitsZeros(profile)) return policy;
  return {
    steps: policy.steps.map((s) => (isFillStep(s) ? { ...s, enabled: false, locked: true, locked_reason: s.locked_reason || LOCK_REASON_NO_ZEROS, params: s.params } : s)),
  };
}

/** A step is unlocked for editing only when it is not locked, or the override is valid. */
export const canToggle = (s: PolicyStep, o: Override) => !s.locked || overrideValid(o);

/** Switches a step on or off. A locked step is left as it was unless the override is valid; turning a locked step off is always allowed. */
export function setEnabled(policy: CleanPolicy, id: string, on: boolean, o: Override): CleanPolicy {
  return { steps: policy.steps.map((s) => (s.id !== id ? s : on && !canToggle(s, o) ? s : { ...s, enabled: on })) };
}

export function setParam(policy: CleanPolicy, id: string, key: string, value: unknown): CleanPolicy {
  return { steps: policy.steps.map((s) => (s.id === id ? { ...s, params: { ...s.params, [key]: value } } : s)) };
}

/** Why Plan must wait: a locked step is switched on without a valid override. Null when the policy may be sent. */
export function planBlockedReason(policy: CleanPolicy, o: Override): string | null {
  const bad = policy.steps.find((s) => s.locked && s.enabled && !overrideValid(o));
  return bad ? `${stepTitle(bad.id)} is locked: tick "I understand, override" and type a reason first.` : null;
}

export function usesOverride(policy: CleanPolicy): boolean {
  return policy.steps.some((s) => s.locked && s.enabled);
}

/** The body of POST clean/plan. The override reason travels only when a locked step is really switched on. */
export function buildPlanBody(source: string, policy: CleanPolicy, o: Override): CleanPlanBody {
  const body: CleanPlanBody = { source, policy };
  if (usesOverride(policy) && overrideValid(o)) body.override_reason = o.reason.trim();
  return body;
}

/** The assistant's suggested policy (a full policy, or a small hint such as a method and a gap length), applied on top of the current one.
 *  It can never switch a locked step on: that stays the user's explicit override. `ignored` lists what was left out, so it can be shown. */
export function applySuggestion(base: CleanPolicy, hint: unknown): { policy: CleanPolicy; ignored: string[] } {
  const ignored: string[] = [];
  let policy = base;
  if (!hint || typeof hint !== 'object') return { policy, ignored };
  const h = hint as Record<string, unknown>;
  const inner = (h.policy && typeof h.policy === 'object' ? h.policy : h) as Record<string, unknown>;
  const steps = Array.isArray(inner.steps) ? (inner.steps as PolicyStep[]) : [];
  for (const sug of steps) {
    const cur = policy.steps.find((s) => s.id === sug.id);
    if (!cur) { ignored.push(`${stepTitle(String(sug.id))}: not a step of this policy`); continue; }
    if (cur.locked && sug.enabled) { ignored.push(`${stepTitle(cur.id)}: locked, so it stays off (only your override can turn it on)`); }
    else policy = setEnabled(policy, cur.id, !!sug.enabled, NO_OVERRIDE);
    if (sug.params && typeof sug.params === 'object') for (const [k, v] of Object.entries(sug.params)) policy = setParam(policy, cur.id, k, v);
  }
  const fill = policy.steps.find(isFillStep);
  if (fill && typeof inner.method === 'string') {
    if (inner.method === 'none') policy = setParam(setEnabled(policy, fill.id, false, NO_OVERRIDE), fill.id, 'method', 'none');
    else if (fill.locked) ignored.push(`${stepTitle(fill.id)}: locked, so ${inner.method} filling was not applied`);
    else policy = setParam(setEnabled(policy, fill.id, true, NO_OVERRIDE), fill.id, 'method', inner.method);
  }
  return { policy, ignored };
}

export const suggestionHint = (r: AssistantReply | null): unknown => r?.cleaning?.plan_hint ?? null;

/** The question the "best cleaning" button sends. */
export const BEST_CLEANING_QUESTION = 'What is the best cleaning for my data?';

export interface ProfileView {
  parameter: string; units: string; kind: string; zeros: string; cadence: string; range: string; missing: string; rainfallOnly: boolean; validationNote: string | null;
}

export const isRainfall = (p: DatasetProfile) => /rain|precip/i.test(p.parameter);

/** The profile in plain words. Nothing is hard-coded to rainfall: the parameter and units are the profile's own. */
export function describeProfile(p: DatasetProfile): ProfileView {
  const parameter = p.parameter && p.parameter !== 'unknown' ? p.parameter : 'unknown parameter';
  const kind = p.kind === 'intermittent_accumulation' ? 'intermittent accumulation (often zero, then bursts)'
    : p.kind === 'continuous_state' ? 'continuous state (always has a value)' : 'not identified';
  const m = p.cadence?.median_minutes;
  const cadence = m === null || m === undefined ? 'unknown'
    : `${m >= 60 && m % 60 === 0 ? `${m / 60} h` : `${m} min`} median, ${p.cadence.regular ? 'regular' : 'irregular'}`;
  const [lo, hi] = p.valid_range ?? [null, null];
  const rng = lo === null && hi === null ? 'not set' : `${lo ?? '-inf'} to ${hi ?? '+inf'}${p.units ? ` ${p.units}` : ''}`;
  const rainfallOnly = p.parameter !== '' && p.parameter !== 'unknown' && !isRainfall(p);
  return {
    parameter, units: p.units ?? 'unknown', kind,
    zeros: p.reports_zero_values ? 'zero values are reported' : 'zero values are not reported',
    cadence, range: rng, missing: p.missing_codes?.length ? p.missing_codes.join(', ') : 'none declared', rainfallOnly,
    validationNote: rainfallOnly ? `Exploring and cleaning work for ${parameter} data, but validation verdicts are rainfall-only: this dataset gets no verdicts from the checks.` : null,
  };
}
