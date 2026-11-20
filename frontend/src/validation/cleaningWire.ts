// The cleaning policy as the SERVER speaks it, and as the editor shows it.
//
// Server (pipeline/cleaning.py): {steps: [{step: 'fill_gaps', method: 'none' | 'linear' | 'previous', max_gap_steps, override_reason?}, ...]}. A step that is
// present runs; fill_gaps with method 'none' leaves gaps missing. The default policy comes wrapped: {source, policy, profile}.
// Editor (cleaning.ts): {steps: [{id, enabled, params, locked?, locked_reason?}]}. A step can be switched off, and a locked one only on with a reason.
// The two never matched, so the Cleaning tab got undefined where it expected steps and the page went blank. These pure functions are the one
// translation, used by api.ts for every cleaning call (and unit-tested in cleaningWire.test.ts).
import type { CleanPolicy, DatasetProfile, PolicyStep } from './types';

export const FILL = 'fill_gaps';
export const LOCK_REASON_UNKNOWN_KIND = 'the kind of this variable is not identified, so filling is refused unless you give a reason (edit the profile first)';
const LOCK_REASON_NO_ZEROS = 'this dataset lists only non-zero values, so a missing value may be a dry value; interpolating would invent rain';
const METHODS = ['linear', 'previous'];
const ALLOWED: Record<string, string[]> = {
  remove_duplicates: [], normalise_units: ['from', 'to'], exclude_out_of_range: ['min', 'max', 'missing_codes'], [FILL]: ['method', 'max_gap_steps', 'override_reason'],
};

export interface ServerStep { step: string; [k: string]: unknown }
export interface ServerPolicy { steps?: ServerStep[]; rule?: string; why?: string; basis?: string }

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v);

/** Why a fill step is locked for this profile, or null when it may be switched on freely. Mirrors the server's refusal rules. */
export function fillLock(profile: Partial<DatasetProfile> | null | undefined): string | null {
  if (!profile) return null;
  if (profile.kind === 'intermittent_accumulation' && profile.reports_zero_values === false) return LOCK_REASON_NO_ZEROS;
  if (profile.kind === 'unknown') return LOCK_REASON_UNKNOWN_KIND;
  return null;
}

/** The server's policy as editor steps. Tolerates a missing or odd policy (returns no steps, never throws). */
export function policyFromServer(p: unknown, profile?: Partial<DatasetProfile> | null): CleanPolicy {
  const raw = isObj(p) && Array.isArray(p.steps) ? (p.steps as unknown[]) : [];
  const steps: PolicyStep[] = [];
  for (const s of raw) {
    if (!isObj(s) || typeof s.step !== 'string') continue;
    const { step, override_reason: _ignored, ...rest } = s as ServerStep;
    if (step === FILL) {
      const method = typeof rest.method === 'string' ? rest.method : 'none';
      const on = method !== 'none';
      const lock = fillLock(profile);
      steps.push({
        id: FILL, enabled: on,
        params: { method: on && METHODS.includes(method) ? method : 'linear', max_gap_steps: typeof rest.max_gap_steps === 'number' ? rest.max_gap_steps : 3 },
        ...(lock ? { locked: true, locked_reason: lock } : {}),
      });
    } else {
      steps.push({ id: step, enabled: true, params: rest as Record<string, unknown> });
    }
  }
  return { steps };
}

const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : Number(v);
  return Number.isFinite(n) ? n : null;
};

/** The editor's policy as the server takes it. A step that is off is left out (fill_gaps becomes method 'none'); a locked fill step that is on carries
 *  the override reason the user typed. Parameters are cut to the ones the server knows and numbers are coerced. */
export function policyToServer(policy: CleanPolicy, overrideReason?: string): { steps: ServerStep[] } {
  const steps: ServerStep[] = [];
  for (const s of policy?.steps ?? []) {
    if (s.id === FILL) {
      const m = String(s.params?.method ?? 'linear');
      const gap = num(s.params?.max_gap_steps);
      const out: ServerStep = { step: FILL, method: s.enabled ? (METHODS.includes(m) ? m : 'linear') : 'none', max_gap_steps: gap === null ? 3 : Math.round(gap) };
      if (s.enabled && s.locked && overrideReason && overrideReason.trim()) out.override_reason = overrideReason.trim();
      steps.push(out);
      continue;
    }
    if (!s.enabled || !(s.id in ALLOWED)) continue;
    const out: ServerStep = { step: s.id };
    for (const k of ALLOWED[s.id]) {
      if (!(k in (s.params ?? {}))) continue;
      const v = s.params[k];
      if (k === 'min' || k === 'max') out[k] = num(v);
      else if (k === 'missing_codes') out[k] = v !== false && v !== 'false';
      else out[k] = v === '' || v === undefined ? null : v;
    }
    steps.push(out);
  }
  return { steps };
}

/** The assistant's advice carries a ready policy in the server's form; add the editor's form beside it so "use this suggestion" can apply it. */
export function hintFromServer(hint: unknown): unknown {
  if (!isObj(hint)) return hint;
  const body = isObj(hint.body) ? hint.body : null;
  const pol = body && isObj(body.policy) ? body.policy : null;
  if (!pol) return hint;
  return { ...hint, policy: policyFromServer(pol, isObj(hint.profile) ? (hint.profile as Partial<DatasetProfile>) : null) };
}
