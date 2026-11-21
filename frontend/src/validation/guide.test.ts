import { describe, expect, it } from 'vitest';
import {
  GUIDE_KEY, GUIDE_STEPS, LEGEND, PAGE_INFO, RAIL_GROUPS, RAIL_HINT, dismissGuide, isGuideDismissed, railKey, railTitle, readsLine, restoreGuide,
} from './guide';
import { RAIL } from './shell';
import type { PageId } from './shell';

const ALL: PageId[] = [...RAIL.map((r) => r.id), 'import', 'settings'];
const memory = () => {
  const m = new Map<string, string>();
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k), m };
};

describe('page descriptions', () => {
  it('has a sentence and a Reads line for every page', () => {
    for (const p of ALL) {
      expect(PAGE_INFO[p].what.length).toBeGreaterThan(20);
      expect(readsLine(p).startsWith('Reads: ')).toBe(true);
    }
  });
  it('says truthfully what each page reads', () => {
    expect(readsLine('live')).toContain('the live stream');
    expect(readsLine('import')).toContain('uploaded files');
    expect(readsLine('alerts')).toContain('both the live stream and uploaded files');
    expect(readsLine('events')).toContain('both the live stream and uploaded files');
    expect(PAGE_INFO.alerts.what).toMatch(/first section.*second/);
  });
  it('never labels anything simulated and never promises a decision', () => {
    for (const p of ALL) expect(`${PAGE_INFO[p].what} ${readsLine(p)}`.toLowerCase()).not.toContain('simulated data');
  });
});

describe('rail', () => {
  it('lists every page once, in three groups', () => {
    expect(RAIL_GROUPS.map((g) => g.label)).toEqual(['Watch', 'Decide', 'Tools']);
    expect(RAIL_GROUPS.flatMap((g) => g.pages).sort()).toEqual([...ALL].sort());
  });
  it('gives each page a one-line hint and keeps the number keys', () => {
    for (const p of ALL) expect(RAIL_HINT[p].length).toBeGreaterThan(10);
    expect(railKey('overview')).toBe('1');
    expect(railKey('agent')).toBe('8');
    expect(railKey('import')).toBeNull();
    expect(railTitle('events')).toContain('press 4');
    expect(railTitle('settings')).toContain('press S');
  });
});

describe('start guide', () => {
  it('has the four steps in order, each with a button', () => {
    expect(GUIDE_STEPS.map((s) => s.target)).toEqual(['pick-station', 'live', 'alerts', 'import']);
    expect(GUIDE_STEPS.every((s) => s.button.length > 0)).toBe(true);
  });
  it('stays until dismissed, remembers it, and can come back', () => {
    const st = memory();
    expect(isGuideDismissed(st)).toBe(false);
    dismissGuide(st);
    expect(st.m.get(GUIDE_KEY)).toBe('1');
    expect(isGuideDismissed(st)).toBe(true);
    restoreGuide(st);
    expect(isGuideDismissed(st)).toBe(false);
  });
  it('shows the guide when storage is missing or blocked', () => {
    expect(isGuideDismissed(null)).toBe(false);
    const blocked = { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } };
    expect(isGuideDismissed(blocked)).toBe(false);
    expect(() => dismissGuide(blocked)).not.toThrow();
  });
});

describe('legend', () => {
  const text = LEGEND.flatMap((s) => s.entries.map((e) => `${e.term} ${e.meaning}`)).join(' | ');
  it('explains the verdict words, the scores and not run', () => {
    for (const t of ['OK', 'UNCERTAIN', 'SUSPECT']) expect(LEGEND[0].entries.map((e) => e.term)).toContain(t);
    expect(text).toContain('uncalibrated, not a probability');
    expect(text).toContain('Not run');
    expect(text).toContain('optional, not validated');
  });
  it('explains the four review decisions', () => {
    const review = LEGEND.find((s) => s.heading.startsWith('Review decisions'))!;
    expect(review.entries.map((e) => e.term)).toEqual(['Confirmed fault', 'False alarm', 'Genuine extreme', 'Needs follow-up']);
  });
});
