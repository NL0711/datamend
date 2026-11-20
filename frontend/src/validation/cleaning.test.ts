import { describe, expect, it } from 'vitest';
import {
  LOCK_REASON_NO_ZEROS, NO_OVERRIDE, applyProfileDefaults, applySuggestion, buildPlanBody, canToggle, describeProfile, omitsZeros, overrideValid, planBlockedReason,
  setEnabled, setParam, usesOverride,
} from './cleaning';
import type { CleanPolicy, DatasetProfile } from './types';

const profile = (o: Partial<DatasetProfile> = {}): DatasetProfile => ({
  parameter: 'rainfall', kind: 'intermittent_accumulation', reports_zero_values: false, cadence: { median_minutes: 60, regular: false }, units: 'mm',
  valid_range: [0, 500], missing_codes: [-999], evidence: ['The smallest value is 0.1 mm.'], ...o,
});
const policy = (): CleanPolicy => ({
  steps: [
    { id: 'remove_duplicates', enabled: true, params: {} },
    { id: 'exclude_impossible', enabled: true, params: { min: 0, max: 500 } },
    { id: 'fill_gaps', enabled: true, params: { method: 'linear', max_gap_steps: 3 } },
  ],
});
const stepOf = (p: CleanPolicy, id: string) => p.steps.find((s) => s.id === id)!;

describe('defaults from the profile', () => {
  it('a dataset that omits zeros gets gap filling off and locked with the reason, even if the server default did not say so', () => {
    const p = applyProfileDefaults(policy(), profile());
    expect(stepOf(p, 'fill_gaps')).toMatchObject({ enabled: false, locked: true, locked_reason: LOCK_REASON_NO_ZEROS });
    expect(stepOf(p, 'remove_duplicates').enabled).toBe(true);
  });
  it('keeps the server reason when it sends one', () => {
    const p = policy(); p.steps[2] = { ...p.steps[2], locked: true, locked_reason: 'server says no' };
    expect(stepOf(applyProfileDefaults(p, profile()), 'fill_gaps').locked_reason).toBe('server says no');
  });
  it('leaves a continuous variable alone (temperature may be filled)', () => {
    const t = profile({ parameter: 'temperature', kind: 'continuous_state', reports_zero_values: true, units: 'degC' });
    expect(omitsZeros(t)).toBe(false);
    expect(applyProfileDefaults(policy(), t)).toEqual(policy());
  });
});

describe('a locked step and the override', () => {
  const locked = () => applyProfileDefaults(policy(), profile());
  it('cannot be switched on without an override', () => {
    expect(canToggle(stepOf(locked(), 'fill_gaps'), NO_OVERRIDE)).toBe(false);
    expect(stepOf(setEnabled(locked(), 'fill_gaps', true, NO_OVERRIDE), 'fill_gaps').enabled).toBe(false);
    expect(stepOf(setEnabled(locked(), 'fill_gaps', true, { ack: true, reason: '' }), 'fill_gaps').enabled).toBe(false);
  });
  it('needs the box ticked and a typed reason', () => {
    expect(overrideValid({ ack: false, reason: 'we checked the source' })).toBe(false);
    expect(overrideValid({ ack: true, reason: '   ' })).toBe(false);
    expect(overrideValid({ ack: true, reason: 'we checked the source' })).toBe(true);
    expect(stepOf(setEnabled(locked(), 'fill_gaps', true, { ack: true, reason: 'we checked the source' }), 'fill_gaps').enabled).toBe(true);
  });
  it('can always be switched off, and unlocked steps toggle freely', () => {
    expect(stepOf(setEnabled(policy(), 'remove_duplicates', false, NO_OVERRIDE), 'remove_duplicates').enabled).toBe(false);
    const on = setEnabled(locked(), 'fill_gaps', true, { ack: true, reason: 'checked it' });
    expect(stepOf(setEnabled(on, 'fill_gaps', false, NO_OVERRIDE), 'fill_gaps').enabled).toBe(false);
  });
  it('blocks Plan when a locked step is on without a valid override', () => {
    const forced = { steps: locked().steps.map((s) => (s.id === 'fill_gaps' ? { ...s, enabled: true } : s)) };
    expect(planBlockedReason(forced, NO_OVERRIDE)).toContain('locked');
    expect(planBlockedReason(forced, { ack: true, reason: 'checked it' })).toBeNull();
    expect(planBlockedReason(locked(), NO_OVERRIDE)).toBeNull();
  });
});

describe('the plan body', () => {
  it('sends the policy, and an override reason only when a locked step is really on', () => {
    const l = applyProfileDefaults(policy(), profile());
    expect(buildPlanBody('cwc', l, { ack: true, reason: 'x'.repeat(10) })).toEqual({ source: 'cwc', policy: l });
    const on = setEnabled(l, 'fill_gaps', true, { ack: true, reason: 'checked with CWC' });
    expect(usesOverride(on)).toBe(true);
    expect(buildPlanBody('cwc', on, { ack: true, reason: '  checked with CWC ' })).toEqual({ source: 'cwc', policy: on, override_reason: 'checked with CWC' });
    expect(buildPlanBody('cwc', on, NO_OVERRIDE).override_reason).toBeUndefined();
  });
  it('edits a parameter of one step only', () => {
    const p = setParam(policy(), 'fill_gaps', 'max_gap_steps', 6);
    expect(stepOf(p, 'fill_gaps').params).toEqual({ method: 'linear', max_gap_steps: 6 });
    expect(stepOf(p, 'exclude_impossible').params).toEqual({ min: 0, max: 500 });
  });
});

describe('using the assistant suggestion', () => {
  it('applies a method hint to an unlocked fill step', () => {
    const r = applySuggestion(policy(), { method: 'previous' });
    expect(stepOf(r.policy, 'fill_gaps')).toMatchObject({ enabled: true, params: { method: 'previous' } });
  });
  it('a none hint switches filling off', () => {
    expect(stepOf(applySuggestion(policy(), { method: 'none' }).policy, 'fill_gaps').enabled).toBe(false);
  });
  it('never turns a locked step on, and says what it left out', () => {
    const l = applyProfileDefaults(policy(), profile());
    const a = applySuggestion(l, { method: 'linear' });
    expect(stepOf(a.policy, 'fill_gaps').enabled).toBe(false); expect(a.ignored[0]).toContain('locked');
    const b = applySuggestion(l, { steps: [{ id: 'fill_gaps', enabled: true, params: {} }, { id: 'remove_duplicates', enabled: false, params: {} }, { id: 'bogus', enabled: true, params: {} }] });
    expect(stepOf(b.policy, 'fill_gaps').enabled).toBe(false);
    expect(stepOf(b.policy, 'remove_duplicates').enabled).toBe(false);
    expect(b.ignored).toHaveLength(2);
  });
  it('ignores a missing or odd hint', () => {
    expect(applySuggestion(policy(), null).policy).toEqual(policy());
    expect(applySuggestion(policy(), 'text').policy).toEqual(policy());
  });
});

describe('words taken from the profile', () => {
  it('reads the rainfall profile in plain words', () => {
    const v = describeProfile(profile());
    expect(v).toMatchObject({ parameter: 'rainfall', units: 'mm', zeros: 'zero values are not reported', cadence: '1 h median, irregular', range: '0 to 500 mm', rainfallOnly: false, validationNote: null });
  });
  it('uses the profile own parameter and units for temperature, and says verdicts are rainfall-only', () => {
    const v = describeProfile(profile({ parameter: 'temperature', kind: 'continuous_state', reports_zero_values: true, units: 'degC', valid_range: [-60, 60], cadence: { median_minutes: 15, regular: true }, missing_codes: [] }));
    expect(v.parameter).toBe('temperature'); expect(v.units).toBe('degC'); expect(v.range).toBe('-60 to 60 degC'); expect(v.cadence).toBe('15 min median, regular');
    expect(v.missing).toBe('none declared');
    expect(v.rainfallOnly).toBe(true); expect(v.validationNote).toContain('rainfall-only');
  });
  it('an unidentified parameter is not labelled non-rainfall', () => {
    const v = describeProfile(profile({ parameter: 'unknown', kind: 'unknown', units: null, valid_range: null, cadence: { median_minutes: null, regular: false } }));
    expect(v.rainfallOnly).toBe(false); expect(v.units).toBe('unknown'); expect(v.range).toBe('not set'); expect(v.cadence).toBe('unknown');
  });
});
