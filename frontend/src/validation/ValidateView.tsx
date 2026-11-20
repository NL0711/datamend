// Step 4, Validate: run the checks on an imported dataset (optionally on the cleaned values), read the summary and the checks that did not
// run (with their reasons), and look at the run itself. Validation verdicts are rainfall-only; a non-rainfall dataset says so.
import { useEffect, useState } from 'react';
import { checkJob, getExploreProfile, getRun } from './api';
import { describeProfile } from './cleaning';
import { completenessText, pct } from './lib';
import { useAdmin } from './Login';
import { RunView } from './RunView';
import type { ImportedJob, RunFull } from './types';
import { NextButton, Notice, Panel, btn, field, formatError } from './ui';

export function ValidateView({ jobs, runId, onRun, onNext }: { jobs: ImportedJob[]; runId: number | null; onRun: (id: number | null) => void; onNext: () => void }) {
  const { signedIn } = useAdmin();
  const done = jobs.filter((j) => j.status === 'done');
  const [jobId, setJobId] = useState<number | null>(null);
  const [useClean, setUseClean] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [run, setRun] = useState<RunFull | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const job = done.find((j) => j.id === jobId) ?? done[0] ?? null;
  useEffect(() => { if (jobId === null && done[0]) setJobId(done[0].id); }, [done, jobId]);
  // choosing a job that already has a run shows that run; a run just made is shown through onRun
  const shown = runId;
  useEffect(() => { if (job?.run_id) onRun(job.run_id); }, [job?.id, job?.run_id]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setRun(null);
    if (shown === null) return;
    let live = true;
    getRun(shown).then((r) => live && setRun(r)).catch(() => undefined);
    return () => { live = false; };
  }, [shown]);
  useEffect(() => {
    setNote(null);
    if (!job) return;
    let live = true;
    getExploreProfile(job.source).then((p) => live && setNote(describeProfile(p).validationNote)).catch(() => undefined);
    return () => { live = false; };
  }, [job?.source]);   // eslint-disable-line react-hooks/exhaustive-deps

  const go = async () => {
    if (!job) return;
    setBusy(true); setError('');
    try { const r = await checkJob(job.id, useClean ? { use_clean: true } : {}); onRun(r.id); setRun(null); getRun(r.id).then(setRun).catch(() => undefined); }
    catch (e) { setError(formatError(e)); } finally { setBusy(false); }
  };

  if (done.length === 0) return <div className="space-y-3"><Notice tone="info">Import a dataset first (step 1); the checks run on what was imported.</Notice><NextButton label="Review" onClick={onNext} /></div>;
  const h = run?.report?.headline;
  return (
    <div className="space-y-3">
      {note && <Notice tone="info">{note}</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      <Panel className="p-4 space-y-3">
        <div className="flex items-end gap-3 flex-wrap">
          <label className="text-xs font-bold block">Imported dataset
            <select value={job?.id ?? ''} onChange={(e) => setJobId(Number(e.target.value))} className={`${field} block mt-1`} aria-label="imported dataset">
              {done.map((j) => <option key={j.id} value={j.id}>#{j.id} {j.filename} ({j.source}){j.run_id !== null ? ' · checked' : ''}</option>)}</select></label>
          <label className="text-xs flex items-center gap-1.5 pb-2"><input type="checkbox" checked={useClean} onChange={(e) => setUseClean(e.target.checked)} />use the cleaned values (accepted corrections), when there are any</label>
          <button className={`${btn} px-5 py-2 text-sm`} disabled={!signedIn || busy || !job} onClick={() => void go()}>{busy ? 'Running…' : job?.run_id !== null && job ? 'Run checks again' : 'Run checks'}</button>
        </div>
        {!signedIn && <p className="text-[11px] text-amber-800">Sign in to run checks.</p>}
        {h && run && (
          <div className="space-y-2">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {([['Rows', String(h.rows)], ['Stations', String(h.stations)], ['Flagged (SUSPECT)', pct(h.share_suspect)], ['UNCERTAIN', pct(h.share_uncertain)], ['Completeness', completenessText(h.completeness)]] as const).map(([k, v]) => (
                <div key={k} className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-3 py-2"><div className="text-[10px] uppercase font-mono text-slate-500">{k}</div><div className="text-sm font-bold font-mono">{v}</div></div>))}
            </div>
            {run.not_run.length > 0 && (
              <div className="text-[11px]"><span className="font-bold">Checks not run ({run.not_run.length}), with the reason:</span>
                <ul className="font-mono text-slate-600 mt-1">{run.not_run.map((n, i) => <li key={i}>{n.check}{n.station_id ? ` · ${n.station_id}` : ''}: {n.reason}</li>)}</ul></div>)}
            <p className="text-[10px] text-slate-500">{h.basis}. Thresholds are design choices, uncalibrated.</p>
          </div>)}
      </Panel>
      {shown !== null && <RunView key={shown} runId={shown} />}
      <NextButton label="Review" onClick={onNext} />
    </div>);
}
