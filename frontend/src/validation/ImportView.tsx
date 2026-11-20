// Step 1, Import: fetch data from an Amazon S3 link or a Kaggle dataset. There is no hand upload. Each provider is a big card with its own
// link box, optional own credentials (kept for this browser tab only, sent as headers for that request) and format choice; the jobs table
// below shows the progress of every import (it looks again every 2 seconds while one is queued or running).
import { useCallback, useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { getImportSources, listJobs, rememberImportAws, rememberKaggle, startImport, storedImportAws, storedKaggle } from './api';
import { useAdmin } from './Login';
import type { ImportedJob, ImportFormat, ImportProvider, ImportSources } from './types';
import { NextButton, Notice, Panel, btn, btnQuiet, field, formatError, num } from './ui';

const DEFAULT_SOURCES: ImportSources = {
  providers: [
    { id: 'aws', label: 'Amazon S3 (AWS)', accepts: ['s3://bucket/key.csv', 'https://bucket.s3.region.amazonaws.com/key.csv'], credentials: 'Your own AWS access key, only for a private bucket.', examples: ['s3://my-bucket/rainfall/cwc-2024.csv'] },
    { id: 'kaggle', label: 'Kaggle', accepts: ['owner/dataset-name', 'https://www.kaggle.com/datasets/owner/dataset-name'], credentials: 'Your own Kaggle username and API key, only for a private dataset.', examples: ['owner/dataset-name'] },
  ],
  formats: [{ id: 'auto', label: 'Auto detect' }, { id: 'cwc', label: 'CWC hourly CSV' }, { id: 'isd', label: 'NOAA ISD' }],
  limits: { max_mb: 300 },
};
const FORMAT_LABEL: Record<string, string> = { auto: 'Auto detect', cwc: 'CWC hourly CSV', isd: 'NOAA ISD' };
const HELP: Record<ImportProvider, string> = {
  aws: 'Paste the link of a CSV file in an Amazon S3 bucket (s3:// or https). Public files need no credentials.',
  kaggle: 'Paste a Kaggle dataset link or its owner/name. The server downloads it for you; nothing is uploaded by hand.',
};

/** Plain bucket-and-cloud mark (generic, not a vendor logo). */
function BucketIcon() {
  return (
    <svg width="56" height="56" viewBox="0 0 64 64" fill="none" stroke="#0E7490" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M20 30a10 10 0 0 1 19-4 8 8 0 0 1 5 14H19a7 7 0 0 1 1-10z" />
      <path d="M16 46h32l-3 10H19z" />
      <path d="M32 34v8M28 38l4-4 4 4" />
    </svg>);
}
/** Plain stack-of-rows dataset mark (generic, not a vendor logo). */
function DatasetIcon() {
  return (
    <svg width="56" height="56" viewBox="0 0 64 64" fill="none" stroke="#0E7490" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <ellipse cx="32" cy="16" rx="18" ry="7" />
      <path d="M14 16v14c0 4 8 7 18 7s18-3 18-7V16" />
      <path d="M14 30v14c0 4 8 7 18 7s18-3 18-7V30" />
    </svg>);
}

function ProviderCard({ id, label, example, formats, maxMb, onStarted, onError }: {
  id: ImportProvider; label: string; example: string; formats: { id: string; label?: string }[]; maxMb: number;
  onStarted: (j: ImportedJob) => void; onError: (m: string) => void;
}) {
  const { signedIn } = useAdmin();
  const [url, setUrl] = useState('');
  const [format, setFormat] = useState<ImportFormat>('auto');
  const [busy, setBusy] = useState(false);
  const [aws, setAws] = useState({ id: '', secret: '', token: '', region: 'ap-south-1' });
  const [kg, setKg] = useState({ user: '', key: '' });
  const [savedAws, setSavedAws] = useState(() => storedImportAws());
  const [savedKg, setSavedKg] = useState(() => storedKaggle());
  const [note, setNote] = useState('');

  const saveAws = () => {
    const a = { accessKeyId: aws.id.trim(), secret: aws.secret.trim(), sessionToken: aws.token.trim(), region: aws.region.trim() };
    if (!/^[A-Za-z0-9]{16,128}$/.test(a.accessKeyId)) { setNote('The access key id is letters and digits only (16 to 128 characters).'); return; }
    if (!a.secret || a.secret.length > 200 || /\s/.test(a.secret)) { setNote('Enter the secret access key without spaces (at most 200 characters).'); return; }
    if (a.sessionToken && /\s/.test(a.sessionToken)) { setNote('The session token must not contain spaces.'); return; }
    if (!/^[a-z]{2}(-[a-z]+){1,2}-[0-9]{1,2}$/.test(a.region)) { setNote('The region looks like ap-south-1.'); return; }
    rememberImportAws(a); setSavedAws(a); setAws({ ...aws, secret: '', token: '' }); setNote('Saved for this tab only.');
  };
  const forgetAws = () => { rememberImportAws(null); setSavedAws(null); setAws({ id: '', secret: '', token: '', region: 'ap-south-1' }); setNote(''); };
  const saveKg = () => {
    const username = kg.user.trim(), key = kg.key.trim();
    if (!/^[A-Za-z0-9_.-]{1,60}$/.test(username)) { setNote('The Kaggle username may contain only letters, digits, underscore, dot and hyphen.'); return; }
    if (!key || key.length > 200 || /\s/.test(key)) { setNote('Enter the API key without spaces (at most 200 characters).'); return; }
    rememberKaggle({ username, key }); setSavedKg({ username, key }); setKg({ ...kg, key: '' }); setNote('Saved for this tab only.');
  };
  const forgetKg = () => { rememberKaggle(null); setSavedKg(null); setKg({ user: '', key: '' }); setNote(''); };

  const go = async () => {
    setBusy(true);
    try { onStarted(await startImport(id, url.trim(), format)); setUrl(''); } catch (e) { onError(formatError(e)); } finally { setBusy(false); }
  };
  const usingOwn = id === 'aws' ? !!savedAws : !!savedKg;

  return (
    <Panel className="p-5 space-y-4 flex flex-col" >
      <div className="flex items-center gap-4">
        {id === 'aws' ? <BucketIcon /> : <DatasetIcon />}
        <div><h2 className="text-lg font-bold text-slate-900">{label}</h2><p className="text-sm text-slate-600">{HELP[id]}</p></div>
      </div>
      <label className="block text-xs font-bold text-slate-700">{id === 'aws' ? 'S3 link' : 'Kaggle dataset link or owner/name'}
        <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder={example} spellCheck={false} autoComplete="off"
               className={`${field} block w-full mt-1 font-mono py-2.5 text-sm`} aria-label={`${label} link`} />
        <span className="font-normal text-slate-500">Example: <span className="font-mono">{example}</span></span>
      </label>
      <label className="block text-xs font-bold text-slate-700">Format
        <select value={format} onChange={(e) => setFormat(e.target.value as ImportFormat)} className={`${field} block mt-1`} aria-label={`${label} format`}>
          {formats.map((f) => <option key={f.id} value={f.id}>{f.label ?? FORMAT_LABEL[f.id] ?? f.id}</option>)}</select>
      </label>
      <details className="border border-[#D3DCE7] rounded px-3 py-2 text-xs">
        <summary className="cursor-pointer font-bold">Use my own credentials{usingOwn && <span className="font-normal text-emerald-700"> (set for this tab)</span>}</summary>
        <div className="mt-2 space-y-2">
          {id === 'aws' ? (
            <div className="grid sm:grid-cols-2 gap-2">
              <label className="font-bold block">Access key id<input value={aws.id} onChange={(e) => setAws({ ...aws, id: e.target.value })} className={`${field} block w-full font-mono`} autoComplete="off" spellCheck={false} /></label>
              <label className="font-bold block">Secret access key<input type="password" value={aws.secret} onChange={(e) => setAws({ ...aws, secret: e.target.value })} className={`${field} block w-full`} autoComplete="off" /></label>
              <label className="font-bold block">Session token (optional)<input type="password" value={aws.token} onChange={(e) => setAws({ ...aws, token: e.target.value })} className={`${field} block w-full`} autoComplete="off" /></label>
              <label className="font-bold block">Region<input value={aws.region} onChange={(e) => setAws({ ...aws, region: e.target.value })} className={`${field} block w-full font-mono`} autoComplete="off" spellCheck={false} /></label>
            </div>) : (
            <div className="grid sm:grid-cols-2 gap-2">
              <label className="font-bold block">Kaggle username<input value={kg.user} onChange={(e) => setKg({ ...kg, user: e.target.value })} className={`${field} block w-full`} autoComplete="off" spellCheck={false} /></label>
              <label className="font-bold block">Kaggle key<input type="password" value={kg.key} onChange={(e) => setKg({ ...kg, key: e.target.value })} className={`${field} block w-full`} autoComplete="off" /></label>
            </div>)}
          <div className="flex gap-2">
            <button className={btn} onClick={id === 'aws' ? saveAws : saveKg} disabled={id === 'aws' ? !aws.id || !aws.secret : !kg.user || !kg.key}>Save for this tab</button>
            <button className={btnQuiet} onClick={id === 'aws' ? forgetAws : forgetKg} disabled={!usingOwn}>Forget</button>
          </div>
          {note && <p className="text-slate-600">{note}</p>}
          <p className="text-[10px] text-slate-500">Kept in this browser tab only (cleared when the tab closes) and sent as headers with the import request. The server uses it for that request and does not store or log it. Leave this closed for public data.</p>
        </div>
      </details>
      <div className="mt-auto flex items-center gap-3 flex-wrap">
        <button className={`${btn} px-6 py-3 text-sm`} disabled={!signedIn || busy || !url.trim()} onClick={() => void go()}>{busy ? 'Starting…' : 'Import'}</button>
        <span className="text-[11px] text-slate-500">up to {maxMb} MB per file</span>
      </div>
    </Panel>);
}

export function JobsTable({ jobs }: { jobs: ImportedJob[] }) {
  return (
    <div className="overflow-x-auto"><table className="w-full text-[11px]">
      <thead className="text-left bg-[#EDF1F7]"><tr><th className="px-2 py-1">Job</th><th className="px-2">Source</th><th className="px-2">Status</th><th className="px-2 text-right">Read</th>
        <th className="px-2 text-right">Stored</th><th className="px-2 text-right">Already stored</th><th className="px-2 text-right">Bad rows</th><th className="px-2 text-right">Stations</th></tr></thead>
      <tbody>{jobs.map((j) => (
        <tr key={j.id} className="border-t border-[#E2E8F2] align-top">
          <td className="px-2 py-1 font-mono">{j.id}</td>
          <td className="px-2">{j.filename}<div className="text-[10px] text-slate-500">{j.provider ? `${j.provider} · ` : ''}{j.source} · {(j.size_bytes / 1048576).toFixed(1)} MB{j.origin ? ` · ${j.origin}` : ''}</div></td>
          <td className="px-2 font-bold">{j.status === 'running' || j.status === 'queued' ? <span className="inline-flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" />{j.status}</span> : j.status}
            {j.error && <div className="text-red-700 font-normal">{j.error}</div>}</td>
          <td className="px-2 text-right font-mono">{num(j.rows_read)}</td><td className="px-2 text-right font-mono">{num(j.rows_inserted)}</td>
          <td className="px-2 text-right font-mono">{num(j.rows_duplicate)}</td>
          <td className="px-2 text-right font-mono" title={j.bad_samples.map((b) => `row ${b.row}: ${b.problem}`).join('\n')}>{num(j.rows_bad)}</td>
          <td className="px-2 text-right font-mono">{j.stations}</td>
        </tr>))}</tbody></table></div>);
}

export function ImportView({ onNext, onJobs }: { onNext: () => void; onJobs?: (jobs: ImportedJob[]) => void }) {
  const [sources, setSources] = useState<ImportSources>(DEFAULT_SOURCES);
  const [jobs, setJobs] = useState<ImportedJob[]>([]);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  const reload = useCallback(() => listJobs().then((r) => { setJobs(r.jobs); onJobs?.(r.jobs); }).catch((e) => setError(formatError(e))), [onJobs]);
  useEffect(() => {
    getImportSources().then(setSources).catch(() => undefined);      // the built-in help text stays if the server does not answer
    void reload();
  }, [reload]);

  const active = jobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => { void reload(); }, 2000);
    return () => window.clearInterval(t);
  }, [active, reload]);

  const provider = (id: ImportProvider) => sources.providers.find((p) => p.id === id) ?? DEFAULT_SOURCES.providers.find((p) => p.id === id)!;
  const started = (j: ImportedJob) => { setError(''); setInfo(`Import ${j.id} accepted. It is read in the background; the table below shows progress.`); setJobs((x) => [j, ...x.filter((y) => y.id !== j.id)]); };
  const doneJobs = jobs.filter((j) => j.status === 'done').length;

  return (
    <div className="space-y-4 max-w-6xl">
      {error && <Notice tone="error">{error}</Notice>}
      {info && <Notice tone="info">{info}</Notice>}
      <div className="grid md:grid-cols-2 gap-4">
        {(['aws', 'kaggle'] as const).map((id) => {
          const p = provider(id);
          return <ProviderCard key={id} id={id} label={p.label} example={p.examples[0] ?? ''} formats={sources.formats} maxMb={sources.limits.max_mb} onStarted={started} onError={setError} />;
        })}
      </div>
      <Panel className="p-4 space-y-2">
        <h2 className="text-sm font-bold text-slate-900">Imports</h2>
        {jobs.length === 0 ? <p className="text-xs text-slate-500">Nothing imported yet.</p> : <JobsTable jobs={jobs} />}
        {jobs[0] && Object.keys(jobs[0].assumptions).length > 0 && (
          <details className="text-xs text-slate-600"><summary className="cursor-pointer font-bold">Assumptions made about the latest source</summary>
            <ul className="list-disc ml-5 mt-1 space-y-0.5">{Object.entries(jobs[0].assumptions).map(([k, v]) => <li key={k}><b>{k.replace(/_/g, ' ')}:</b> {v}</li>)}</ul></details>)}
        <p className="text-[10px] text-slate-500">Stored once and never overwritten; importing the same file again adds nothing.</p>
      </Panel>
      <NextButton label="Explore & clean" onClick={onNext} disabled={doneJobs === 0} />
    </div>);
}
