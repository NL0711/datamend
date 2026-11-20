// A dynamic table: renders any query result (columns and rows from the server), sortable by column, with a small filter bar built from the
// spec that produced it. Filters re-run the query through onSpec; sorting reorders only the rows already loaded.
import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, X } from 'lucide-react';
import { OP_LABEL, addFilter, cellText, columnKind, describeFilter, makeFilter, needsValue, opsFor, removeFilter, rowCapNotice, sortRows } from './tablequery';
import type { ExploreTable, QueryResult, QuerySpec } from './types';
import { GeneratedBadge, Notice, btn, field } from './ui';

export function DataTable({ result, table, fromAssistant, onSpec }: { result: QueryResult; table: ExploreTable | null; fromAssistant: boolean; onSpec: (s: QuerySpec) => void }) {
  const [sort, setSort] = useState<{ col: string | null; dir: 'asc' | 'desc' }>({ col: null, dir: 'asc' });
  const [fCol, setFCol] = useState('');
  const [fOp, setFOp] = useState('=');
  const [fVal, setFVal] = useState('');
  const [bad, setBad] = useState('');

  const rows = useMemo(() => sortRows(result, sort.col, sort.dir), [result, sort]);
  const spec = result.spec;
  const colDef = table?.columns.find((c) => c.name === fCol);
  const ops = colDef ? opsFor(colDef.type) : [];
  const notice = rowCapNotice(result);

  const pickCol = (name: string) => {
    setFCol(name); setBad('');
    const c = table?.columns.find((x) => x.name === name);
    setFOp(c ? opsFor(c.type)[0] : '='); setFVal('');
  };
  const add = () => {
    if (!table) return;
    const f = makeFilter(table, fCol, fOp, fVal);
    if (!f) { setBad(`Enter a valid ${colDef ? columnKind(colDef.type) : ''} value for ${fCol || 'the column'}.`); return; }
    setBad(''); setFVal(''); onSpec(addFilter(spec, f));
  };
  const toggleSort = (name: string) => setSort((s) => (s.col === name ? { col: name, dir: s.dir === 'asc' ? 'desc' : 'asc' } : { col: name, dir: 'asc' }));

  return (
    <div className="space-y-2 min-w-0">
      <div className="flex items-center gap-2 flex-wrap text-[11px]">
        <span className="font-mono font-bold text-slate-900">{spec.table}</span>
        <span className="font-mono text-slate-500">{result.total.toLocaleString('en-IN')} matching rows</span>
        {fromAssistant && <GeneratedBadge text="from the assistant" />}
        {(spec.group_by?.length ?? 0) > 0 && <span className="font-mono text-slate-500">grouped by {spec.group_by?.join(', ')}</span>}
      </div>

      <div className="flex items-center gap-1.5 flex-wrap" aria-label="filters">
        {(spec.filters ?? []).map((f, i) => (
          <span key={`${describeFilter(f)}-${i}`} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-[#D3DCE7] bg-[#F4F6FA] text-[11px] font-mono">
            {describeFilter(f)}
            <button aria-label={`remove filter ${describeFilter(f)}`} onClick={() => onSpec(removeFilter(spec, i))}><X className="w-3 h-3" /></button></span>))}
        {table && (
          <>
            <select value={fCol} onChange={(e) => pickCol(e.target.value)} className={field} aria-label="filter column"><option value="">Add a filter…</option>
              {table.columns.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}</select>
            {fCol && (
              <>
                <select value={fOp} onChange={(e) => setFOp(e.target.value)} className={field} aria-label="filter operator">{ops.map((o) => <option key={o} value={o}>{OP_LABEL[o] ?? o}</option>)}</select>
                {needsValue(fOp) && <input value={fVal} onChange={(e) => setFVal(e.target.value)} className={`${field} w-32`} aria-label="filter value" onKeyDown={(e) => { if (e.key === 'Enter') add(); }} />}
                <button className={btn} onClick={add}>Filter</button>
              </>)}
          </>)}
      </div>
      {bad && <p className="text-[11px] text-red-700">{bad}</p>}

      <div className="overflow-auto max-h-[28rem] border border-[#D3DCE7] rounded">
        <table className="w-full text-[11px] font-mono">
          <thead className="text-left bg-[#EDF1F7] sticky top-0"><tr>
            {result.columns.map((c) => (
              <th key={c.name} className="px-2 py-1 whitespace-nowrap" aria-sort={sort.col === c.name ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                <button className="inline-flex items-center gap-1 font-bold" onClick={() => toggleSort(c.name)} title={`sort by ${c.name}`}>{c.name}
                  {sort.col === c.name && (sort.dir === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}</button></th>))}
          </tr></thead>
          <tbody>{rows.map((r, i) => (
            <tr key={i} className="border-t border-[#E2E8F2]">
              {r.map((c, j) => <td key={j} className={`px-2 py-0.5 whitespace-nowrap ${columnKind(result.columns[j]?.type ?? 'text') === 'number' ? 'text-right' : ''}`}>{cellText(c)}</td>)}</tr>))}</tbody>
        </table>
        {rows.length === 0 && <p className="p-3 text-xs text-slate-500">No rows match.</p>}
      </div>
      {notice && <Notice tone="warn">{notice}</Notice>}
    </div>);
}
