import { describe, expect, it } from 'vitest';
import { ROW_CAP, addFilter, capSpec, cellText, columnKind, coerceValue, describeFilter, makeFilter, opsFor, removeFilter, rowCapNotice, sortRows, specForTable } from './tablequery';
import type { ExploreTable, QueryResult } from './types';

const table: ExploreTable = {
  id: 'observations', label: 'Observations', description: '',
  columns: [{ name: 'station_key', type: 'text' }, { name: 'value', type: 'float' }, { name: 'at', type: 'timestamp' }, { name: 'flag', type: 'boolean' }],
};
const result = (over: Partial<QueryResult> = {}): QueryResult => ({
  columns: [{ name: 'station_key', type: 'text' }, { name: 'value', type: 'float' }],
  rows: [['b', 2], ['a', 10], ['c', null], ['d', 1]], total: 4, truncated: false, spec: { table: 'observations' }, ...over,
});

describe('table specs', () => {
  it('opens a table with the row cap, and a run when given', () => {
    expect(specForTable('observations')).toEqual({ table: 'observations', limit: ROW_CAP });
    expect(specForTable('rows', 7)).toEqual({ table: 'rows', limit: ROW_CAP, run_id: 7 });
  });
  it('never lets a spec from elsewhere ask for more than the cap', () => {
    expect(capSpec({ table: 't', limit: 100000 }).limit).toBe(ROW_CAP);
    expect(capSpec({ table: 't' }).limit).toBe(ROW_CAP);
    expect(capSpec({ table: 't', limit: 20 }).limit).toBe(20);
    expect(capSpec({ table: 't', limit: -1 }).limit).toBe(ROW_CAP);
  });
});

describe('filters built from the column type', () => {
  it('classifies column types and offers the right operators', () => {
    expect(columnKind('float')).toBe('number'); expect(columnKind('timestamp')).toBe('time'); expect(columnKind('boolean')).toBe('bool'); expect(columnKind('text')).toBe('text');
    expect(opsFor('text')).toContain('contains'); expect(opsFor('float')).not.toContain('contains');
  });
  it('coerces typed text, and refuses what is not valid', () => {
    expect(coerceValue('float', ' 2.5 ')).toBe(2.5);
    expect(coerceValue('float', 'abc')).toBeUndefined();
    expect(coerceValue('boolean', 'true')).toBe(true);
    expect(coerceValue('boolean', 'yes')).toBeUndefined();
    expect(coerceValue('text', '  ')).toBeUndefined();
  });
  it('makes a filter only for a known column and an operator that fits it', () => {
    expect(makeFilter(table, 'value', '>', '5')).toEqual({ column: 'value', op: '>', value: 5 });
    expect(makeFilter(table, 'value', 'contains', '5')).toBeNull();
    expect(makeFilter(table, 'nope', '=', '5')).toBeNull();
    expect(makeFilter(table, 'value', '>', 'x')).toBeNull();
    expect(makeFilter(table, 'value', 'is_null', '')).toEqual({ column: 'value', op: 'is_null' });
  });
  it('adds and removes filters without touching the rest of the spec', () => {
    const s = addFilter(addFilter({ table: 'observations', limit: 500 }, { column: 'value', op: '>', value: 1 }), { column: 'station_key', op: '=', value: 'a' });
    expect(s.filters).toHaveLength(2);
    expect(removeFilter(s, 0).filters).toEqual([{ column: 'station_key', op: '=', value: 'a' }]);
    expect(removeFilter(removeFilter(s, 0), 0)).toEqual({ table: 'observations', limit: 500 });
    expect(describeFilter({ column: 'value', op: '>', value: 5 })).toBe('value > 5');
    expect(describeFilter({ column: 'value', op: 'not_null' })).toBe('value is not empty');
  });
});

describe('sorting the rows shown', () => {
  it('sorts numbers numerically with empty cells last, both ways', () => {
    expect(sortRows(result(), 'value', 'asc').map((r) => r[0])).toEqual(['d', 'b', 'a', 'c']);
    expect(sortRows(result(), 'value', 'desc').map((r) => r[0])).toEqual(['a', 'b', 'd', 'c']);
  });
  it('sorts text, keeps the server order with no column, ignores an unknown column', () => {
    expect(sortRows(result(), 'station_key', 'asc').map((r) => r[0])).toEqual(['a', 'b', 'c', 'd']);
    expect(sortRows(result(), null, 'asc')).toEqual(result().rows);
    expect(sortRows(result(), 'zzz', 'asc')).toEqual(result().rows);
  });
  it('does not change the loaded rows', () => {
    const r = result(); sortRows(r, 'value', 'asc');
    expect(r.rows[0]).toEqual(['b', 2]);
  });
});

describe('the row cap notice', () => {
  it('is absent when everything is shown, present when the server cut the table', () => {
    expect(rowCapNotice(result())).toBeNull();
    expect(rowCapNotice(result({ truncated: true, total: 90000 }))).toContain('of 90,000 rows');
  });
  it('formats cells', () => {
    expect(cellText(null)).toBe(''); expect(cellText(2)).toBe('2'); expect(cellText(0.123456)).toBe('0.1235'); expect(cellText(true)).toBe('true');
  });
});
