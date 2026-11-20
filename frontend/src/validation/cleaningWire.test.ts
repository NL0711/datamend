// The translation between the server's cleaning policy and the editor's. The "server" objects below are copied from what
// GET /api/pipeline/clean/policy/default really answered (2026-11-20, an imported NOAA ISD file); the crash that blanked the page came from
// reading `steps` off the wrapper.
import { describe, expect, it, vi } from 'vitest';
import { FILL, LOCK_REASON_UNKNOWN_KIND, fillLock, hintFromServer, policyFromServer, policyToServer } from './cleaningWire';
import { applySuggestion, NO_OVERRIDE, planBlockedReason } from './cleaning';
import type { CleanPolicy } from './types';

const serverDefault = {
  steps: [{ step: 'remove_duplicates' }, { step: 'normalise_units', from: null, to: null }, { step: 'fill_gaps', method: 'none', max_gap_steps: 3 }],
  rule: 'intermittent-reports-zeros-no-fill', why: 'x', basis: 'y',
};
const reportsZeros = { kind: 'intermittent_accumulation' as const, reports_zero_values: true };
const omitsZeros = { kind: 'intermittent_accumulation' as const, reports_zero_values: false };

describe('policyFromServer', () => {
  it('turns the real default into editor steps with the fill step off (method none) and nothing locked when zeros are reported', () => {
    const p = policyFromServer(serverDefault, reportsZeros);
    expect(p.steps.map((s) => s.id)).toEqual(['remove_duplicates', 'normalise_units', 'fill_gaps']);
    expect(p.steps[0]).toMatchObject({ enabled: true, params: {} });
    expect(p.steps[2]).toMatchObject({ id: FILL, enabled: false, params: { method: 'linear', max_gap_steps: 3 } });
    expect(p.steps[2].locked).toBeUndefined();
    expect(planBlockedReason(p, NO_OVERRIDE)).toBeNull();
  });
  it('locks the fill step when the dataset omits zeros or its kind is unknown, with the reason', () => {
    expect(policyFromServer(serverDefault, omitsZeros).steps[2]).toMatchObject({ locked: true });
    const u = policyFromServer(serverDefault, { kind: 'unknown' as never, reports_zero_values: false });
    expect(u.steps[2]).toMatchObject({ locked: true, locked_reason: LOCK_REASON_UNKNOWN_KIND });
    expect(fillLock(null)).toBeNull();
  });
  it('shows a server fill method as on', () => {
    const p = policyFromServer({ steps: [{ step: 'fill_gaps', method: 'previous', max_gap_steps: 2 }] }, reportsZeros);
    expect(p.steps[0]).toMatchObject({ enabled: true, params: { method: 'previous', max_gap_steps: 2 } });
  });
  it('never throws on a missing, wrapped or odd policy', () => {
    for (const bad of [undefined, null, {}, { steps: 'no' }, { policy: serverDefault }, 7, { steps: [null, 3, { nostep: 1 }] }]) {
      expect(policyFromServer(bad, null)).toEqual({ steps: [] });
    }
  });
});

describe('policyToServer', () => {
  it('sends enabled steps by name, a switched-off fill step as method none, and drops other switched-off steps', () => {
    const p: CleanPolicy = { steps: [
      { id: 'remove_duplicates', enabled: true, params: {} },
      { id: 'normalise_units', enabled: false, params: { from: null, to: null } },
      { id: 'exclude_out_of_range', enabled: true, params: { min: '0', max: 500, missing_codes: true } },
      { id: FILL, enabled: false, params: { method: 'linear', max_gap_steps: '4' } },
    ] };
    expect(policyToServer(p)).toEqual({ steps: [
      { step: 'remove_duplicates' },
      { step: 'exclude_out_of_range', min: 0, max: 500, missing_codes: true },
      { step: FILL, method: 'none', max_gap_steps: 4 },
    ] });
  });
  it('puts the override reason only on a locked fill step that is switched on', () => {
    const on: CleanPolicy = { steps: [{ id: FILL, enabled: true, locked: true, params: { method: 'linear', max_gap_steps: 3 } }] };
    expect(policyToServer(on, '  checked with CWC today ').steps[0]).toEqual({ step: FILL, method: 'linear', max_gap_steps: 3, override_reason: 'checked with CWC today' });
    expect(policyToServer(on).steps[0]).not.toHaveProperty('override_reason');
    const off: CleanPolicy = { steps: [{ id: FILL, enabled: false, locked: true, params: {} }] };
    expect(policyToServer(off, 'a reason that is long enough').steps[0]).toEqual({ step: FILL, method: 'none', max_gap_steps: 3 });
    const free: CleanPolicy = { steps: [{ id: FILL, enabled: true, params: { method: 'previous', max_gap_steps: 2 } }] };
    expect(policyToServer(free, 'a reason that is long enough').steps[0]).not.toHaveProperty('override_reason');
  });
  it('sends only parameters the server knows, with numbers coerced and empty bounds as null', () => {
    const p: CleanPolicy = { steps: [{ id: 'exclude_out_of_range', enabled: true, params: { min: '', max: 'abc', junk: 1, missing_codes: false } }] };
    expect(policyToServer(p).steps[0]).toEqual({ step: 'exclude_out_of_range', min: null, max: null, missing_codes: false });
    expect(policyToServer({ steps: [{ id: 'made_up_step', enabled: true, params: {} }] })).toEqual({ steps: [] });
  });
  it('round-trips the server default with no change', () => {
    const ui = policyFromServer(serverDefault, reportsZeros);
    expect(policyToServer(ui).steps).toEqual([{ step: 'remove_duplicates' }, { step: 'normalise_units', from: null, to: null }, { step: FILL, method: 'none', max_gap_steps: 3 }]);
  });
});

describe('hintFromServer', () => {
  it('adds the editor form of the advised policy so a suggestion can be applied', () => {
    const hint = { endpoint: 'POST /api/pipeline/clean/plan', body: { source: 'isd', policy: { steps: [{ step: 'fill_gaps', method: 'linear', max_gap_steps: 3 }] } }, profile: reportsZeros };
    const out = hintFromServer(hint) as { policy: CleanPolicy };
    expect(out.policy.steps[0]).toMatchObject({ id: FILL, enabled: true });
    const base = policyFromServer(serverDefault, reportsZeros);
    const { policy, ignored } = applySuggestion(base, out);
    expect(policy.steps.find((s) => s.id === FILL)).toMatchObject({ enabled: true, params: { method: 'linear' } });
    expect(ignored).toEqual([]);
  });
  it('leaves other values alone', () => {
    expect(hintFromServer(null)).toBeNull(); expect(hintFromServer('text')).toBe('text'); expect(hintFromServer({ a: 1 })).toEqual({ a: 1 });
    vi.fn();
  });
});
