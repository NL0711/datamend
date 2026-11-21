import { useCallback, useEffect, useState } from 'react';
import { Upload } from 'lucide-react';
import { ApiError, importKaggle, listRuns, uploadRun } from './api';
import { headlineLine } from './lib';
import type { RunSummary } from './types';
import { Notice, Panel, SyntheticBadge, formatError } from './ui';

/** Asks for a Kaggle API token, and only that, when a dataset turned out to be private. */
function TokenDialog({ busy, error, onSubmit, onCancel }: { busy: boolean; error: string | null; onSubmit: (token: string) => void; onCancel: () => void }) {
  const [token, setToken] = useState('');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" role="dialog" aria-modal="true" aria-label="Kaggle token"
      onKeyDown={(e) => { if (e.key === 'Escape') onCancel(); }}>
      <form className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl space-y-3" onSubmit={(e) => { e.preventDefault(); if (token.trim()) onSubmit(token.trim()); }}>
        <div>
          <h3 className="text-sm font-bold text-slate-900">This dataset is private</h3>
          <p className="text-[11px] text-slate-500 mt-0.5">Enter a Kaggle API token. It is used once and not saved.</p>
        </div>
        <input autoFocus type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="KGAT_…" autoComplete="off" aria-label="Kaggle API token"
          className="w-full text-sm border border-[#D3DCE7] rounded-lg px-3 py-2 font-mono focus:outline-none focus:ring-2 focus:ring-sky-300" />
        {error && <p className="text-[11px] text-red-700">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="px-3 py-1.5 rounded-lg text-xs font-bold text-slate-600 hover:bg-slate-100">Cancel</button>
          <button type="submit" disabled={!token.trim() || busy} className="px-3 py-1.5 rounded-lg bg-sky-600 text-white text-xs font-bold disabled:opacity-40">{busy ? 'Importing…' : 'Import'}</button>
        </div>
      </form>
    </div>
  );
}

export function NewRun({ onCreated }: { onCreated: (id: number) => void }) {
  const [source, setSource] = useState<'file' | 'kaggle'>('file');
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState('');
  const [needToken, setNeedToken] = useState(false);
  const [tokenError, setTokenError] = useState<string | null>(null);
  const [profile, setProfile] = useState<'reading' | 'daily'>('reading');
  const [mode, setMode] = useState('');
  const [tz, setTz] = useState('');
  const [interval, setInterval_] = useState('');
  const [synthetic, setSynthetic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = source === 'file' ? !!file : url.trim().length > 3;
  const opts = { profile, accumulationMode: profile === 'reading' ? mode : undefined, timezone: tz, intervalMinutes: profile === 'reading' ? interval : undefined, synthetic };

  const submit = async (token?: string) => {
    if (!ready) return;
    setBusy(true); setError(null); setTokenError(null);
    try {
      const run = source === 'file' ? await uploadRun({ file: file as File, ...opts }) : await importKaggle({ url: url.trim(), token, ...opts });
      setNeedToken(false);
      onCreated(run.id);
    } catch (e) {
      if (source === 'kaggle' && e instanceof ApiError && e.status === 401) {
        if (token) setTokenError(e.message); else setNeedToken(true);
      } else { setNeedToken(false); setError(formatError(e)); }
    } finally { setBusy(false); }
  };

  const field = 'text-xs border border-[#D3DCE7] rounded-lg px-2.5 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-sky-200';
  const seg = (on: boolean) => `px-3 py-1 rounded-md text-xs font-bold ${on ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`;
  return (
    <Panel className="p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Upload className="w-4 h-4" />New run</h2>
        <div className="inline-flex rounded-lg bg-slate-100 p-0.5" role="tablist">
          <button role="tab" aria-selected={source === 'file'} className={seg(source === 'file')} onClick={() => setSource('file')}>File</button>
          <button role="tab" aria-selected={source === 'kaggle'} className={seg(source === 'kaggle')} onClick={() => setSource('kaggle')}>Link</button>
        </div>
      </div>
      <div className="flex gap-2 flex-wrap items-center">
        {source === 'file'
          ? <input type="file" accept=".csv,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className={`${field} flex-1 min-w-[14rem]`} aria-label="file" />
          : <input value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void submit(); }} placeholder="Kaggle dataset or public S3 link" aria-label="Dataset link" className={`${field} flex-1 min-w-[14rem]`} />}
        <button disabled={!ready || busy} onClick={() => void submit()} className="px-4 py-1.5 rounded-lg bg-sky-600 text-white text-xs font-bold disabled:opacity-40">{busy ? (source === 'file' ? 'Validating…' : 'Importing…') : (source === 'file' ? 'Validate' : 'Import')}</button>
      </div>
      <details className="text-[11px] text-slate-600">
        <summary className="cursor-pointer select-none font-bold text-slate-500">Options</summary>
        <div className="grid sm:grid-cols-2 gap-2 mt-2">
          <select aria-label="Profile" value={profile} onChange={(e) => setProfile(e.target.value as 'reading' | 'daily')} className={field}>
            <option value="reading">Readings (timestamp, station, accumulation or intensity)</option>
            <option value="daily">Daily totals (day, station, mm)</option></select>
          {profile === 'reading' && (
            <>
              <select aria-label="Accumulation" value={mode} onChange={(e) => setMode(e.target.value)} className={field}>
                <option value="">Accumulation: not declared</option><option value="cumulative">Accumulation: running total</option><option value="per_reading">Accumulation: per reading</option></select>
              <input aria-label="Interval" value={interval} onChange={(e) => setInterval_(e.target.value)} inputMode="decimal" placeholder="Interval in minutes, e.g. 15" className={field} />
            </>)}
          <input aria-label="Time zone" value={tz} onChange={(e) => setTz(e.target.value)} placeholder="Time zone if timestamps have none" className={field} />
          <label className="flex items-center gap-2"><input type="checkbox" checked={synthetic} onChange={(e) => setSynthetic(e.target.checked)} />Synthetic data</label>
        </div>
      </details>
      {error && <Notice tone="error">{error}</Notice>}
      {needToken && <TokenDialog busy={busy} error={tokenError} onSubmit={(t) => void submit(t)} onCancel={() => { setNeedToken(false); setTokenError(null); }} />}
    </Panel>
  );
}

export function RunsView({ onOpen }: { onOpen: (id: number) => void }) {
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => { listRuns().then((r) => setRuns(r.runs)).catch((e) => setError(formatError(e))); }, []);
  useEffect(load, [load]);

  return (
    <div className="space-y-3">
      <NewRun onCreated={onOpen} />
      <Panel className="p-3">
        <h2 className="text-sm font-bold text-slate-900 mb-2">Runs</h2>
        {error && <Notice tone="error">{error}</Notice>}
        {runs && runs.length === 0 && <p className="text-xs text-slate-500">No runs yet.</p>}
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
