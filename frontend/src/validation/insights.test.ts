import { describe, expect, it } from 'vitest';
import { corrColor, insightsQuery, shareOf, toCsv } from './insights';

describe('insights helpers', () => {
  it('builds the query and leaves empty values out', () => {
    expect(insightsQuery({ granularity: 'month' })).toBe('granularity=month');
    expect(insightsQuery({ runId: 7, includeSynthetic: true, station: 'A 1', start: '2024-01-01', granularity: 'year' }))
      .toBe('run_id=7&station=A+1&start=2024-01-01&granularity=year');                      // a chosen run wins over the synthetic switch
    expect(insightsQuery({ includeSynthetic: true, granularity: 'month' })).toContain('include_synthetic=true');
  });
  it('writes a CSV with quoting and empty cells', () => {
    expect(toCsv([])).toBe('');
    expect(toCsv([{ a: 1, b: 'x,y', c: null }, { a: 2, b: 'say "hi"', c: true }])).toBe('a,b,c\n1,"x,y",\n2,"say ""hi""",true');
  });
  it('colours a correlation: grey for none, blue for positive, orange for negative', () => {
    expect(corrColor(null)).toBe('#E2E8F0');
    expect(corrColor(1)).toBe('rgb(29,78,216)');
    expect(corrColor(-1)).toBe('rgb(217,119,6)');
    expect(corrColor(0)).toBe('rgb(241,245,249)');
  });
  it('turns counts into shares that sum to 100 and handles an empty group', () => {
    expect(shareOf({ OK: 3, SUSPECT: 1 })).toEqual({ OK: 75, SUSPECT: 25 });
    expect(shareOf({ OK: 0, SUSPECT: 0 })).toEqual({ OK: 0, SUSPECT: 0 });
  });
});
