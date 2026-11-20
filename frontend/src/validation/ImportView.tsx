// Step 1, Import: one box. Paste a Kaggle dataset or an Amazon S3 link; the source is recognised from what you paste. Public datasets and public
// buckets import with no credentials. Only when the server says a dataset is private (status 428) does a small popup ask for a Kaggle API token
// (the token and nothing else); a private S3 bucket asks for an access key the same way. Nothing is asked up front.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Cloud, Database, Loader2, Lock, X } from 'lucide-react';
import { ApiError, listJobs, rememberImportAws, rememberKaggleToken, startImport, storedImportAws, storedKaggleToken } from './api';
import { detectProvider, looksLikeKaggleToken, providerLabel } from './importLink';
import { useAdmin } from './Login';
import type { ImportedJob, ImportFormat, ImportProvider } from './types';
import { NextButton, Notice, Panel, btn, btnQuiet, field, formatError, num } from './ui';

const FORMATS: { id: ImportFormat; label: string }[] = [{ id: 'auto', label: 'Auto-detect format' }, { id: 'cwc', label: 'CWC hourly CSV' }, { id: 'isd', label: 'NOAA ISD' }];

/** A small centred dialog: Esc or the backdrop closes it, the first field is focused. */
function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-sm rounded-xl bg-white shadow-xl border border-[#D3DCE7] p-5 space-y-3">
        <div className="flex items-center gap-2">
          <Lock className="w-4 h-4 text-teal-700" aria-hidden="true" />
          <h2 className="text-sm font-bold text-slate-900 flex-1">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-700"><X className="w-4 h-4" /></button>
        </div>
        {children}
      </div>
    </div>);
}

function TokenDialog({ error, busy, onSubmit, onClose }: { error: string; busy: boolean; onSubmit: (token: string) => void; onClose: () => void }) {
  const [token, setToken] = useState('');
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const ok = looksLikeKaggleToken(token);
  return (
    <Modal title="This dataset is private" onClose={onClose}>
      <p className="text-xs text-slate-600">Paste your Kaggle API token to import it. It is used for this import only.</p>
      <input ref={ref} type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="KGAT_…" autoComplete="off" spellCheck={false}
             onKeyDown={(e) => { if (e.key === 'Enter' && ok && !busy) onSubmit(token.trim()); }}
             className={`${field} block w-full font-mono py-2`} aria-label="Kaggle API token" />
      {error && <p className="text-xs text-red-700">{error}</p>}
      <div className="flex justify-end gap-2">
        <button className={btnQuiet} onClick={onClose}>Cancel</button>
        <button className={btn} disabled={!ok || busy} onClick={() => onSubmit(token.trim())}>{busy ? 'Importing…' : 'Import'}</button>
      </div>
    </Modal>);
}

function AwsDialog({ error, busy, onSubmit, onClose }: { error: string; busy: boolean; onSubmit: (a: { accessKeyId: string; secret: string; region: string }) => void; onClose: () => void }) {
  const [a, setA] = useState({ accessKeyId: '', secret: '', region: 'ap-south-1' });
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const ok = /^[A-Za-z0-9]{16,128}$/.test(a.accessKeyId.trim()) && a.secret.trim().length > 0 && !/\s/.test(a.secret.trim()) && /^[a-z]{2}(-[a-z]+){1,2}-[0-9]{1,2}$/.test(a.region.trim());
  return (
    <Modal title="This bucket is private" onClose={onClose}>
      <p className="text-xs text-slate-600">Enter an AWS access key that can read it. Kept for this tab only.</p>
      <input ref={ref} value={a.accessKeyId} onChange={(e) => setA({ ...a, accessKeyId: e.target.value })} placeholder="Access key id" autoComplete="off" spellCheck={false} className={`${field} block w-full font-mono py-2`} aria-label="AWS access key id" />
      <input type="password" value={a.secret} onChange={(e) => setA({ ...a, secret: e.target.value })} placeholder="Secret access key" autoComplete="off" className={`${field} block w-full py-2`} aria-label="AWS secret access key" />
      <input value={a.region} onChange={(e) => setA({ ...a, region: e.target.value })} placeholder="Region" autoComplete="off" spellCheck={false} className={`${field} block w-full font-mono py-2`} aria-label="AWS region" />
      {error && <p className="text-xs text-red-700">{error}</p>}
      <div className="flex justify-end gap-2">
        <button className={btnQuiet} onClick={onClose}>Cancel</button>
        <button className={btn} disabled={!ok || busy} onClick={() => onSubmit({ accessKeyId: a.accessKeyId.trim(), secret: a.secret.trim(), region: a.region.trim() })}>{busy ? 'Importing…' : 'Import'}</button>
      </div>
    </Modal>);
}

export function JobsTable({ jobs }: { jobs: ImportedJob[] }) {
  return (
    <div className="overflow-x-auto"><table className="w-full text-[11px]">
      <thead className="text-left text-slate-500"><tr><th className="py-1 font-medium">Source</th><th className="font-medium">Status</th><th className="text-right font-medium">Read</th>
        <th className="text-right font-medium">Stored</th><th className="text-right font-medium">Bad rows</th><th className="text-right font-medium">Stations</th></tr></thead>
      <tbody>{jobs.map((j) => (
        <tr key={j.id} className="border-t border-[#E2E8F2] align-top">
          <td className="py-1.5 pr-2">{j.filename}<div className="text-[10px] text-slate-500">{[j.provider === 'aws' ? 'S3' : j.provider === 'kaggle' ? 'Kaggle' : '', j.source, `${(j.size_bytes / 1048576).toFixed(1)} MB`].filter(Boolean).join(' · ')}</div></td>
          <td className="font-semibold">{j.status === 'running' || j.status === 'queued' ? <span className="inline-flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" />{j.status}</span> : j.status}
            {j.error && <div className="text-red-700 font-normal">{j.error}</div>}</td>
          <td className="text-right font-mono">{num(j.rows_read)}</td><td className="text-right font-mono">{num(j.rows_inserted)}</td>
          <td className="text-right font-mono" title={j.bad_samples.map((b) => `row ${b.row}: ${b.problem}`).join('\n')}>{num(j.rows_bad)}</td>
          <td className="text-right font-mono">{j.stations}</td>
        </tr>))}</tbody></table></div>);
}

export function ImportView({ onNext, onJobs }: { onNext: () => void; onJobs?: (jobs: ImportedJob[]) => void }) {
  const { signedIn } = useAdmin();
  const [url, setUrl] = useState('');
  const [format, setFormat] = useState<ImportFormat>('auto');
  const [busy, setBusy] = useState(false);
  const [jobs, setJobs] = useState<ImportedJob[]>([]);
  const [error, setError] = useState('');
  const [dialog, setDialog] = useState<null | { kind: ImportProvider; error: string }>(null);

  const provider = detectProvider(url);
  const reload = useCallback(() => listJobs().then((r) => { setJobs(r.jobs); onJobs?.(r.jobs); }).catch((e) => setError(formatError(e))), [onJobs]);
  useEffect(() => { void reload(); }, [reload]);

  const active = jobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => { void reload(); }, 2000);
    return () => window.clearInterval(t);
  }, [active, reload]);

  /** Start the import. ``token`` is a Kaggle token the visitor just typed (or the one remembered for this tab, tried once after a 428). */
  const run = async (token?: string, retried = false) => {
    if (!provider) return;
    setBusy(true); setError('');
    try {
      const j = await startImport(provider, url.trim(), format, token);
      if (token) rememberKaggleToken(token);                                    // it worked: do not ask again in this tab
      setDialog(null); setUrl('');
      setJobs((x) => [j, ...x.filter((y) => y.id !== j.id)]);
    } catch (e) {
      if (e instanceof ApiError && provider === 'kaggle' && e.status === 428) {  // private dataset: now, and only now, a token is needed
        const saved = storedKaggleToken();
        if (saved && !token && !retried) { setBusy(false); return run(saved, true); }
        setDialog({ kind: 'kaggle', error: '' });
      } else if (e instanceof ApiError && provider === 'kaggle' && token && e.status === 403) {
        rememberKaggleToken(null);
        setDialog({ kind: 'kaggle', error: 'Kaggle refused that token, or it has no access to this dataset.' });
      } else if (e instanceof ApiError && provider === 'aws' && e.status === 403 && !storedImportAws()) {
        setDialog({ kind: 'aws', error: '' });
      } else {
        setDialog(null); setError(formatError(e));
      }
    } finally { setBusy(false); }
  };

  const submitAws = (a: { accessKeyId: string; secret: string; region: string }) => {
    rememberImportAws({ ...a, sessionToken: '' });
    setDialog(null);
    void run();
  };

  const doneJobs = jobs.filter((j) => j.status === 'done').length;
  const Icon = provider === 'aws' ? Cloud : Database;

  return (
    <div className="space-y-5 max-w-2xl">
      <Panel className="p-6 space-y-4">
        <div className="flex items-stretch gap-2">
          <div className="relative flex-1">
            <Icon className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" aria-hidden="true" />
            <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="owner/dataset  ·  s3://bucket/file.csv" spellCheck={false} autoComplete="off"
                   onKeyDown={(e) => { if (e.key === 'Enter' && provider && signedIn && !busy) void run(); }}
                   className="w-full text-sm border border-[#D3DCE7] rounded-lg pl-9 pr-24 py-3 bg-white font-mono focus:outline-none focus:ring-2 focus:ring-teal-600/30 focus:border-teal-600" aria-label="Kaggle dataset or S3 link" />
            {provider && <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold uppercase tracking-wide text-teal-700 bg-teal-50 rounded px-1.5 py-0.5">{providerLabel(provider)}</span>}
          </div>
          <button className="px-6 rounded-lg bg-teal-700 text-white text-sm font-bold disabled:opacity-40 hover:bg-teal-800" disabled={!signedIn || busy || !provider} onClick={() => void run()}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" aria-label="Importing" /> : 'Import'}</button>
        </div>
        <div className="flex items-center justify-between gap-2 text-xs text-slate-500">
          <select value={format} onChange={(e) => setFormat(e.target.value as ImportFormat)} className="text-xs bg-transparent border-0 py-0 pl-0 text-slate-500 focus:ring-0 cursor-pointer" aria-label="File format">
            {FORMATS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</select>
          {busy && <span className="text-teal-700">Downloading… a large dataset can take a minute</span>}
          {!busy && url.trim() && !provider && <span className="text-amber-700">Not a Kaggle or S3 link yet</span>}
          {!signedIn && <span className="text-amber-700">Sign in to import</span>}
        </div>
        {error && <Notice tone="error">{error}</Notice>}
      </Panel>

      {jobs.length > 0 && (
        <Panel className="p-4 space-y-2">
          <h2 className="text-sm font-bold text-slate-900">Imports</h2>
          <JobsTable jobs={jobs} />
        </Panel>)}

      <NextButton label="Explore & clean" onClick={onNext} disabled={doneJobs === 0} />

      {dialog?.kind === 'kaggle' && <TokenDialog error={dialog.error} busy={busy} onSubmit={(t) => void run(t, true)} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'aws' && <AwsDialog error={dialog.error} busy={busy} onSubmit={submitAws} onClose={() => setDialog(null)} />}
    </div>);
}
