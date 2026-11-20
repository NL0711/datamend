// The table-spec runner's pure parts: building a query body from a table and a filter bar, filter rules by column type, client-side sort of
// the rows already loaded, and the row-cap notice. No React, no network (unit-tested in tablequery.test.ts).
import type { Cell, ExploreTable, QueryFilter, QueryResult, QuerySpec } from './types';

/** How many rows one request asks for (a design choice, assumed): the server may cap lower and says so with `truncated`. */
export const ROW_CAP = 500;

export type ColKind = 'number' | 'time' | 'bool' | 'text';
export function columnKind(type: string): ColKind {
  const t = type.toLowerCase();
  if (/bool/.test(t)) return 'bool';
  if (/time|date/.test(t)) return 'time';
  if (/int|float|num|real|double|decimal/.test(t)) return 'number';
  return 'text';
}

export const OPS: Record<ColKind, string[]> = {
  number: ['=', '!=', '>', '>=', '<', '<=', 'is_null', 'not_null'],
  time: ['>=', '<=', '=', 'is_null', 'not_null'],
  bool: ['=', 'is_null', 'not_null'],
  text: ['=', '!=', 'contains', 'is_null', 'not_null'],
};
export const opsFor = (type: string) => OPS[columnKind(type)];
export const needsValue = (op: string) => op !== 'is_null' && op !== 'not_null';
export const OP_LABEL: Record<string, string> = { '=': 'is', '!=': 'is not', '>': '>', '>=': '>=', '<': '<', '<=': '<=', contains: 'contains', is_null: 'is empty', not_null: 'is not empty', in: 'is one of' };

/** The body that opens a table (its rows, capped). */
export function specForTable(table: string, runId?: number | null): QuerySpec {
  return { table, limit: ROW_CAP, ...(runId ? { run_id: runId } : {}) };
}

/** A spec from the assistant (or anywhere else) is never allowed to ask for more rows than the cap. */
export function capSpec(spec: QuerySpec): QuerySpec {
  return { ...spec, limit: Math.min(spec.limit && spec.limit > 0 ? spec.limit : ROW_CAP, ROW_CAP) };
}

/** Turns what was typed into the value the server expects, or `undefined` when it is not valid for the column. */
export function coerceValue(type: string, raw: string): string | number | boolean | undefined {
  const k = columnKind(type);
  const s = raw.trim();
  if (s === '') return undefined;
  if (k === 'number') { const n = Number(s); return Number.isFinite(n) ? n : undefined; }
  if (k === 'bool') return s === 'true' ? true : s === 'false' ? false : undefined;
  return s;
}

export function makeFilter(table: ExploreTable, column: string, op: string, raw: string): QueryFilter | null {
  const col = table.columns.find((c) => c.name === column);
  if (!col || !opsFor(col.type).includes(op)) return null;
  if (!needsValue(op)) return { column, op };
  const value = coerceValue(col.type, raw);
  return value === undefined ? null : { column, op, value };
}

export const addFilter = (spec: QuerySpec, f: QueryFilter): QuerySpec => ({ ...spec, filters: [...(spec.filters ?? []), f] });
export const removeFilter = (spec: QuerySpec, index: number): QuerySpec => {
  const filters = (spec.filters ?? []).filter((_, i) => i !== index);
  const { filters: _drop, ...rest } = spec;
  return filters.length ? { ...rest, filters } : rest;
};

export function describeFilter(f: QueryFilter): string {
  const op = OP_LABEL[f.op] ?? f.op;
  return needsValue(f.op) ? `${f.column} ${op} ${Array.isArray(f.value) ? f.value.join(', ') : String(f.value)}` : `${f.column} ${op}`;
}

const cmp = (a: Cell, b: Cell, numeric: boolean): number => {
  if (numeric) return Number(a) - Number(b);
  return String(a).localeCompare(String(b));
};

/** Sorts the rows already loaded by one column (empty cells always last). The server's own order is kept when no column is chosen. */
export function sortRows(result: QueryResult, column: string | null, dir: 'asc' | 'desc'): Cell[][] {
  const i = column === null ? -1 : result.columns.findIndex((c) => c.name === column);
  if (i < 0) return result.rows;
  const numeric = columnKind(result.columns[i].type) === 'number';
  const sign = dir === 'asc' ? 1 : -1;
  return result.rows
    .map((r, idx) => ({ r, idx }))
    .sort((x, y) => {
      const a = x.r[i], b = y.r[i];
      if (a === null || a === undefined) return b === null || b === undefined ? x.idx - y.idx : 1;
      if (b === null || b === undefined) return -1;
      return sign * cmp(a, b, numeric) || x.idx - y.idx;
    })
    .map((x) => x.r);
}

/** The notice under a table that was cut, or null when every matching row is shown. */
export function rowCapNotice(result: QueryResult): string | null {
  if (!result.truncated && result.rows.length >= result.total) return null;
  return `Showing the first ${result.rows.length.toLocaleString('en-IN')} of ${result.total.toLocaleString('en-IN')} rows. Add a filter to narrow it down; sorting reorders only the rows shown.`;
}

export function cellText(c: Cell | undefined): string {
  if (c === null || c === undefined) return '';
  return typeof c === 'number' ? (Number.isInteger(c) ? String(c) : String(Number(c.toFixed(4)))) : String(c);
}
