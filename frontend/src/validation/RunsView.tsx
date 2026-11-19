import { useCallback, useEffect, useState } from 'react';
import { Upload } from 'lucide-react';
import { listRuns, uploadRun } from './api';
import { headlineLine } from './lib';
import type { RunSummary } from './types';
import { Notice, Panel, SyntheticBadge, formatError } from './ui';

function NewRun({ onCreated }: { onCreated: (id: number) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [profile, setProfile] = useState<'reading' | 'daily'>('reading');
  const [mode, setMode] = useState('');
  const [tz, setTz] = useState('');
  const [interval, setInterval_] = useState('');
  const [synthetic, setSynthetic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const run = await uploadRun({ file, profile, accumulationMode: profile === 'reading' ? mode : undefined, timezone: tz, intervalMinutes: profile === 'reading' ? interval : undefined, synthetic });
      onCreated(run.id);
    } catch (e) { setError(formatError(e)); } finally { setBusy(false); }
  };

  const field = 'text-xs border border-[#D3DCE7] rounded px-2 py-1';
  return (
    <Panel className="p-4 space-y-3">
      <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Upload className="w-4 h-4" />New run</h2>
      <p className="text-[11px] text-slate-600">CSV or JSON, about 10 MB at most, millimetres only. Parquet and unit conversion are NOT IMPLEMENTED. A file-level problem rejects the whole upload with a reason; a row-level problem keeps the row with a flag.</p>
      <div className="grid md:grid-cols-2 gap-3">
        <label className="text-[11px] space-y-1 block">File
          <input type="file" accept=".csv,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className={`${field} block w-full`} aria-label="file" /></label>
        <label className="text-[11px] space-y-1 block">Profile
          <select value={profile} onChange={(e) => setProfile(e.target.value as 'reading' | 'daily')} className={`${field} block w-full`}>
            <option value="reading">reading: timestamp, station_id, accumulation and/or intensity</option>
            <option value="daily">daily: day, station_id, mm</option></select></label>
        {profile === 'reading' && (
          <>
            <label className="text-[11px] space-y-1 block">Accumulation mode (required if the file has an accumulation column)
              <select value={mode} onChange={(e) => setMode(e.target.value)} className={`${field} block w-full`}>
                <option value="">not declared</option><option value="cumulative">cumulative (running total)</option><option value="per_reading">per_reading (amount since the last reading)</option></select></label>
            <label className="text-[11px] space-y-1 block">Reading interval in minutes (needed for the gap check and completeness)
              <input value={interval} onChange={(e) => setInterval_(e.target.value)} inputMode="decimal" placeholder="for example 15" className={`${field} block w-full`} /></label>
          </>)}
        <label className="text-[11px] space-y-1 block">Time zone of timestamps that carry none (UTC, +05:30 or an IANA name; leave empty if they all carry one)
          <input value={tz} onChange={(e) => setTz(e.target.value)} placeholder="optional" className={`${field} block w-full`} /></label>
        <label className="text-[11px] flex items-center gap-2 mt-5"><input type="checkbox" checked={synthetic} onChange={(e) => setSynthetic(e.target.checked)} />This data is synthetic (it will be labelled SYNTHETIC everywhere)</label>
      </div>
      {error && <Notice tone="error">{error}</Notice>}
      <button disabled={!file || busy} onClick={() => void submit()} className="px-3 py-1.5 rounded bg-sky-600 text-white text-xs font-bold disabled:opacity-40">{busy ? 'Validating…' : 'Validate'}</button>
    </Panel>
  );
}

export function RunsView({ onOpen }: { onOpen: (id: number) => void }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [storage, setStorage] = useState('');
  const [cap, setCap] = useState(50);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { listRuns().then((r) => { setRuns(r.runs); setStorage(r.storage); setCap(r.cap); }).catch((e) => setError(formatError(e))); }, []);
  useEffect(load, [load]);

  return (
    <div className="space-y-3">
      <NewRun onCreated={(id) => { load(); onOpen(id); }} />
      <Panel className="p-3">
        <div className="flex items-center gap-3 mb-2">
          <h2 className="text-sm font-bold text-slate-900">Runs</h2>
          <span className="px-2 py-0.5 rounded border border-amber-300 bg-amber-50 text-amber-800 text-[10px] font-mono font-bold">{storage || 'demo storage, resets on restart'}</span>
          <span className="text-[10px] font-mono text-slate-500">at most {cap} kept, oldest removed first · download the JSON export to keep a run</span>
        </div>
        {error && <Notice tone="error">{error}</Notice>}
        {runs && runs.length === 0 && <p className="text-xs text-slate-500">No runs yet. Upload a file above; the live feed adds one run per rain day when it is enabled.</p>}
        <ul>
          {runs?.map((r) => (
            <li key={r.id} className="border-t border-[#E2E8F2] py-2 flex items-center gap-3 flex-wrap">
              <button disabled={r.status === 'failed'} onClick={() => onOpen(r.id)} className="text-xs font-bold text-sky-700 hover:underline disabled:text-slate-500 disabled:no-underline">#{r.id} {r.label}</button>
              {r.synthetic && <SyntheticBadge />}
              <span className="text-[10px] font-mono text-slate-500">{r.profile} · {r.source} · {r.status}{r.rain_day ? ` · rain day ending ${r.rain_day}` : ''}</span>
              <span className="text-[11px] text-slate-700">{r.status === 'failed' ? `rejected: ${r.error}` : headlineLine(r.headline)}</span>
              <span className="ml-auto text-[10px] font-mono text-slate-400">{r.created_at?.slice(0, 19).replace('T', ' ')}</span>
            </li>))}
        </ul>
      </Panel>
    </div>
  );
}
