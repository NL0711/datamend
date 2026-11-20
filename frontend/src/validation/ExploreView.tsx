// Step 2, Explore & clean. Tables: the list of tables on the left, a dynamic table in the centre, the assistant on the right. Locations: the
// stations the data identified, located or not. Cleaning: profile, policy, plan, proposals (CleaningPanel).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { getExploreStations, getExploreTables, runQuery } from './api';
import { AssistantPanel } from './AssistantPanel';
import { CleaningPanel } from './CleaningPanel';
import { DataTable } from './DataTable';
import { capSpec, specForTable } from './tablequery';
import type { ExploreStations, ExploreTable, ImportedJob, QueryResult, QuerySpec } from './types';
import { NextButton, Notice, Panel, formatError } from './ui';

type Tab = 'tables' | 'locations' | 'cleaning';
const TABS: { id: Tab; label: string }[] = [{ id: 'tables', label: 'Tables' }, { id: 'locations', label: 'Locations' }, { id: 'cleaning', label: 'Cleaning' }];

function Locations() {
  const [data, setData] = useState<ExploreStations | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { getExploreStations().then(setData).catch((e) => setError(formatError(e))); }, []);
  if (error) return <Notice tone="error">{error}</Notice>;
  if (!data) return <p className="text-xs text-slate-500">Loading stations…</p>;
  return (
    <Panel className="p-3 space-y-2">
      <div className="flex items-center gap-4 text-xs font-mono flex-wrap"><span><b>{data.located}</b> located</span><span className={data.unlocated > 0 ? 'text-amber-800' : ''}><b>{data.unlocated}</b> not located</span></div>
      {data.note && <p className="text-[11px] text-slate-600">{data.note}</p>}
      <div className="overflow-auto max-h-[32rem] border border-[#D3DCE7] rounded">
        <table className="w-full text-[11px]">
          <thead className="text-left bg-[#EDF1F7] sticky top-0"><tr><th className="px-2 py-1">Station</th><th className="px-2">State, district</th><th className="px-2">Position</th><th className="px-2">State</th><th className="px-2 text-right">Observations</th></tr></thead>
          <tbody>{data.stations.map((s) => (
            <tr key={s.station_key} className="border-t border-[#E2E8F2]">
              <td className="px-2 py-0.5 font-bold">{s.name ?? s.station_key}<div className="font-mono text-[10px] text-slate-400">{s.station_key}</div></td>
              <td className="px-2">{[s.state, s.district].filter(Boolean).join(', ') || '-'}</td>
              <td className="px-2 font-mono">{s.latitude !== null && s.longitude !== null ? `${s.latitude.toFixed(3)}, ${s.longitude.toFixed(3)}` : '-'}</td>
              <td className="px-2"><span className={`font-mono font-bold ${s.located ? 'text-emerald-700' : 'text-amber-800'}`}>{s.located ? 'located' : 'not located'}</span></td>
              <td className="px-2 text-right font-mono">{s.n_observations.toLocaleString('en-IN')}</td></tr>))}</tbody>
        </table>
      </div>
    </Panel>);
}

export function ExploreView({ jobs, onExplored, onNext }: { jobs: ImportedJob[]; onExplored: () => void; onNext: () => void }) {
  const [tab, setTab] = useState<Tab>('tables');
  const [tables, setTables] = useState<ExploreTable[]>([]);
  const [current, setCurrent] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [fromAssistant, setFromAssistant] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const sources = useMemo(() => [...new Set(jobs.filter((j) => j.status === 'done').map((j) => j.source))], [jobs]);
  const run = useCallback(async (spec: QuerySpec, assistant: boolean) => {
    setBusy(true); setError('');
    try {
      const r = await runQuery(capSpec(spec));
      setResult(r); setFromAssistant(assistant); setCurrent(r.spec?.table ?? spec.table);
      if (r.rows.length > 0) onExplored();
    } catch (e) { setError(formatError(e)); } finally { setBusy(false); }
  }, [onExplored]);

  useEffect(() => {
    getExploreTables().then((r) => { setTables(r.tables); if (r.tables[0]) void run(specForTable(r.tables[0].id), false); }).catch((e) => setError(formatError(e)));
  }, [run]);

  const table = tables.find((t) => t.id === current) ?? null;
  return (
    <div className="space-y-3">
      <div role="tablist" className="flex gap-1 border-b border-[#E2E8F2]">
        {TABS.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}
                  className={`px-4 py-2 text-sm font-bold -mb-px border-b-2 ${tab === t.id ? 'border-teal-700 text-teal-800' : 'border-transparent text-slate-600'}`}>{t.label}</button>))}
      </div>
      {error && <Notice tone="error">{error}</Notice>}

      {tab === 'tables' && (
        <div className="grid lg:grid-cols-[200px_minmax(0,1fr)_340px] gap-3 items-start">
          <Panel className="p-2">
            <h3 className="text-[10px] uppercase font-mono text-slate-500 px-1 pb-1">Tables</h3>
            {tables.length === 0 && <p className="text-xs text-slate-500 px-1">No tables yet.</p>}
            <ul>{tables.map((t) => (
              <li key={t.id}><button onClick={() => void run(specForTable(t.id), false)} aria-current={current === t.id ? 'true' : undefined}
                                     className={`w-full text-left rounded px-2 py-1.5 text-xs ${current === t.id ? 'bg-[#ECFEFF] text-[#0B5E75] font-bold' : 'hover:bg-[#F8FAFC]'}`} title={t.description}>
                {t.label}<div className="text-[10px] text-slate-500 font-normal">{t.columns.length} columns</div></button></li>))}</ul>
          </Panel>
          <div className="min-w-0">
            <Panel className="p-3">
              {table && <p className="text-[11px] text-slate-600 mb-2">{table.description}</p>}
              {result ? <DataTable result={result} table={table} fromAssistant={fromAssistant} onSpec={(s) => void run(s, fromAssistant)} />
                : <p className="text-xs text-slate-500">{busy ? 'Loading…' : 'Choose a table.'}</p>}
            </Panel>
          </div>
          <AssistantPanel onShowTable={(s) => void run(s, true)} />
        </div>)}
      {tab === 'locations' && <Locations />}
      {tab === 'cleaning' && <CleaningPanel sources={sources} />}
      <NextButton label="Stations" onClick={onNext} />
    </div>);
}
