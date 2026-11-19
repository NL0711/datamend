// The data pipeline: bring in bulk station data, check it, review proposed corrections, audit what the checks called fine, freeze a training
// snapshot, and gate a model that was trained offline. Everything generated is marked generated; nothing here trains or scores a model.
import { useCallback, useEffect, useRef, useState } from 'react';
import { ClipboardCheck, Download, FileUp, Loader2, ShieldCheck } from 'lucide-react';
import {
  checkJob, decideAudit, decideProposal, downloadSnapshot, drawAudit, getPipelineStatus, ingestFile, listAudit, listJobs, listModels, listProposals,
  listSnapshots, makeProposals, makeSnapshot, promoteModel, registerModel, rollbackModel,
} from './api';
import { useAdmin } from './Login';
import type { AuditEstimate, AuditItem, IngestJob, PipelineModel, PipelineProposal, PipelineSnapshot, PipelineStatus } from './types';
import { NOT_MEASURED, Notice, Panel, formatError } from './ui';

const btn = 'px-3 py-1.5 rounded bg-teal-700 text-white text-xs font-bold disabled:opacity-40';
const btnQuiet = 'px-3 py-1.5 rounded border border-[#D3DCE7] bg-white text-xs font-bold disabled:opacity-40';
const field = 'text-xs border border-[#D3DCE7] rounded px-2 py-1.5 bg-white';
const num = (n: number) => n.toLocaleString('en-IN');

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <Panel className="p-4 space-y-3">
      <div><h2 className="text-sm font-bold text-slate-900">{title}</h2>{hint && <p className="text-xs text-slate-600 mt-0.5">{hint}</p>}</div>
      {children}
    </Panel>);
}

export function PipelineView({ onOpenRun }: { onOpenRun: (id: number) => void }) {
  const { signedIn } = useAdmin();
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [runId, setRunId] = useState<number | null>(null);
  const [proposals, setProposals] = useState<PipelineProposal[]>([]);
  const [audit, setAudit] = useState<{ items: AuditItem[]; estimate: AuditEstimate } | null>(null);
  const [snaps, setSnaps] = useState<PipelineSnapshot[]>([]);
  const [models, setModels] = useState<PipelineModel[]>([]);
  const [msg, setMsg] = useState<{ tone: 'info' | 'error' | 'warn'; text: string } | null>(null);
  const [busy, setBusy] = useState('');
  const [cut, setCut] = useState(new Date().toISOString().slice(0, 10));
  const [allowTest, setAllowTest] = useState(false);
  const [reg, setReg] = useState({ name: 'stnet', version: '', metrics: '' });
  const fileRef = useRef<HTMLInputElement | null>(null);

  const fail = (e: unknown) => setMsg({ tone: 'error', text: formatError(e) });
  const refresh = useCallback(() => {
    getPipelineStatus().then(setStatus).catch(fail);
    listJobs().then((r) => setJobs(r.jobs)).catch(fail);
    listSnapshots().then((r) => setSnaps(r.snapshots)).catch(fail);
    listModels().then((r) => setModels(r.models)).catch(fail);
  }, []);
  useEffect(refresh, [refresh]);

  // while a job is queued or running, look again every 2 seconds
  const active = jobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => {
      listJobs().then((r) => { setJobs(r.jobs); if (!r.jobs.some((j) => j.status === 'queued' || j.status === 'running')) refresh(); }).catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(t);
  }, [active, refresh]);

  const loadRun = useCallback((id: number) => {
    setRunId(id);
    listProposals(id, 'all').then((r) => setProposals(r.proposals)).catch(fail);
    listAudit(id).then(setAudit).catch(fail);
  }, []);

  const run = async (label: string, fn: () => Promise<unknown>, done?: string) => {
    setBusy(label); setMsg(null);
    try { await fn(); if (done) setMsg({ tone: 'info', text: done }); } catch (e) { fail(e); } finally { setBusy(''); refresh(); }
  };

  const upload = () => {
    const f = fileRef.current?.files?.[0];
    if (!f) { setMsg({ tone: 'warn', text: 'Choose a CSV file first.' }); return; }
    void run('upload', async () => { const j = await ingestFile(f, status?.sources[0] ?? 'cwc'); setJobs((x) => [j, ...x]); }, 'Accepted. The file is read in the background; the job row shows progress.');
  };

  const regModel = () => {
    let metrics: Record<string, unknown>;
    try { metrics = JSON.parse(reg.metrics); } catch { setMsg({ tone: 'error', text: 'Metrics must be valid JSON.' }); return; }
    void run('register', () => registerModel({ name: reg.name, version: reg.version, metrics }), 'Registered as a challenger. Promotion runs the gate.');
  };

  return (
    <div className="space-y-4 max-w-6xl">
      {msg && <Notice tone={msg.tone}>{msg.text}</Notice>}
      {status && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {([['Observations', num(status.observations)], ['Stations', num(status.stations)], ['Ingest jobs', num(status.jobs)],
             ['Proposals waiting', num(status.proposals_pending)], ['Champion model', status.champions[0] ? `${status.champions[0].name} ${status.champions[0].version}` : 'none']] as const).map(([k, v]) => (
            <Panel key={k} className="px-3 py-2"><div className="text-[10px] uppercase font-mono text-slate-500">{k}</div><div className="text-sm font-bold font-mono truncate">{v}</div></Panel>))}
        </div>)}
      {status && (
        <div className={`rounded px-3 py-2 text-xs ${NOT_MEASURED}`}>
          <b>Not built yet:</b> {status.not_implemented.join('; ')}.
        </div>)}
      {!signedIn && <Notice tone="warn">Sign in to change anything here.</Notice>}

      <Section title="1. Bring data in" hint={`CSV in the CWC hourly format, up to ${status?.max_upload_mb ?? 300} MB. Stored once and never overwritten; uploading the same file again adds nothing.`}>
        <div className="flex items-center gap-2 flex-wrap">
          <input ref={fileRef} type="file" accept=".csv,text/csv" className={field} aria-label="data file" />
          <button className={btn} disabled={!signedIn || busy === 'upload'} onClick={upload}><FileUp className="w-3.5 h-3.5 inline mr-1" />Upload</button>
        </div>
        {jobs.length > 0 && (
          <div className="overflow-x-auto"><table className="w-full text-[11px]">
            <thead className="text-left bg-[#EDF1F7]"><tr><th className="px-2 py-1">Job</th><th className="px-2">File</th><th className="px-2">Status</th><th className="px-2 text-right">Read</th>
              <th className="px-2 text-right">Stored</th><th className="px-2 text-right">Already stored</th><th className="px-2 text-right">Bad rows</th><th className="px-2 text-right">Stations</th><th className="px-2" /></tr></thead>
            <tbody>{jobs.map((j) => (
              <tr key={j.id} className="border-t border-[#E2E8F2] align-top">
                <td className="px-2 py-1 font-mono">{j.id}</td>
                <td className="px-2">{j.filename}<div className="text-[10px] text-slate-500">{j.source} · {(j.size_bytes / 1048576).toFixed(1)} MB</div></td>
                <td className="px-2 font-bold">{j.status === 'running' || j.status === 'queued' ? <span className="inline-flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" />{j.status}</span> : j.status}
                  {j.error && <div className="text-red-700 font-normal">{j.error}</div>}</td>
                <td className="px-2 text-right font-mono">{num(j.rows_read)}</td><td className="px-2 text-right font-mono">{num(j.rows_inserted)}</td>
                <td className="px-2 text-right font-mono">{num(j.rows_duplicate)}</td>
                <td className="px-2 text-right font-mono" title={j.bad_samples.map((b) => `row ${b.row}: ${b.problem}`).join('\n')}>{num(j.rows_bad)}</td>
                <td className="px-2 text-right font-mono">{j.stations}</td>
                <td className="px-2 whitespace-nowrap">
                  {j.status === 'done' && j.run_id === null && <button className={btn} disabled={!signedIn || !!busy} onClick={() => void run('check' + j.id, async () => { const r = await checkJob(j.id); loadRun(r.id); }, 'Checked. Open the run, or review the proposals below.')}><ShieldCheck className="w-3 h-3 inline mr-1" />Check</button>}
                  {j.run_id !== null && <><button className={btnQuiet} onClick={() => onOpenRun(j.run_id as number)}>Open run</button> <button className={btnQuiet} onClick={() => loadRun(j.run_id as number)}>Review here</button></>}
                </td>
              </tr>))}</tbody></table></div>)}
        {jobs[0] && Object.keys(jobs[0].assumptions).length > 0 && (
          <details className="text-xs text-slate-600"><summary className="cursor-pointer font-bold">Assumptions made about this source</summary>
            <ul className="list-disc ml-5 mt-1 space-y-0.5">{Object.entries(jobs[0].assumptions).map(([k, v]) => <li key={k}><b>{k.replace(/_/g, ' ')}:</b> {v}</li>)}</ul></details>)}
      </Section>

      <Section title="2. Review proposals and audit what the checks called fine"
               hint={runId === null ? 'Check a finished job, or press Review here on a job, to work on its run.' : `Run ${runId}. Proposals are generated suggestions: they change nothing until you accept one, and the original value is always kept.`}>
        {runId !== null && (
          <>
            <div className="flex gap-2 flex-wrap">
              <button className={btn} disabled={!signedIn || !!busy} onClick={() => void run('proposals', async () => { await makeProposals(runId); loadRun(runId); }, 'Proposals generated by the rule-based baseline (the AI proposer is not built).')}>Generate proposals</button>
              <button className={btnQuiet} disabled={!signedIn || !!busy} onClick={() => void run('audit', async () => { await drawAudit(runId, 30); loadRun(runId); }, 'A random sample of 30 unflagged days was drawn.')}>Draw audit sample (30)</button>
              <button className={btnQuiet} onClick={() => onOpenRun(runId)}>Open run</button>
            </div>
            {proposals.length === 0 ? <p className="text-xs text-slate-500">No proposals for this run yet.</p> : (
              <ul className="space-y-2">{proposals.map((p) => (
                <li key={p.id} className={`rounded px-3 py-2 text-xs ${NOT_MEASURED}`}>
                  <div className="flex items-center gap-2 flex-wrap"><span className="font-mono font-bold">GENERATED</span><span className="font-mono">{p.station_id}</span>
                    <span className="font-mono text-slate-500">{p.kind}{p.original_mm !== null ? ` · ${p.original_mm} mm` : ''}</span><span className="ml-auto font-mono">{p.status}</span></div>
                  <p className="mt-1">{p.text}</p>
                  {p.status === 'pending' && (
                    <div className="mt-2 flex gap-2"><button className={btn} disabled={!signedIn || !!busy} onClick={() => void run('p' + p.id, async () => { await decideProposal(p.id, true); loadRun(runId); })}>Accept</button>
                      <button className={btnQuiet} disabled={!signedIn || !!busy} onClick={() => void run('p' + p.id, async () => { await decideProposal(p.id, false); loadRun(runId); })}>Reject</button></div>)}
                </li>))}</ul>)}
            {audit && audit.items.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs"><b>Audit sample.</b> {audit.estimate.decided} judged of {audit.estimate.drawn}
                  {audit.estimate.missed_fault_rate !== null && <> · missed-fault rate <b className="font-mono">{(audit.estimate.missed_fault_rate * 100).toFixed(1)}%</b>
                    {audit.estimate.interval_95 && <> (95% {(audit.estimate.interval_95[0] * 100).toFixed(1)} to {(audit.estimate.interval_95[1] * 100).toFixed(1)}%)</>}</>}
                  <span className="block text-slate-500">{audit.estimate.note}</span></div>
                <ul className="grid md:grid-cols-2 gap-1">{audit.items.map((a) => (
                  <li key={a.id} className="flex items-center gap-2 text-[11px] border border-[#E2E8F2] rounded px-2 py-1">
                    <span className="font-mono truncate flex-1" title={a.station_id}>{a.station_id} · row {a.row_ref}</span>
                    {a.decision ? <span className="font-bold">{a.decision}</span> : (['ok', 'missed_fault', 'unsure'] as const).map((d) => (
                      <button key={d} className={btnQuiet} disabled={!signedIn || !!busy} onClick={() => void run('a' + a.id, async () => { await decideAudit(a.id, d); loadRun(runId); })}>{d === 'missed_fault' ? 'missed' : d}</button>))}
                  </li>))}</ul>
              </div>)}
          </>)}
      </Section>

      <Section title="3. Freeze a training snapshot" hint="Labelled days up to a cut day, for one offline training run. Reviewer decisions only; unreviewed rows are never treated as clean. The locked test years 2018 to 2025 are left out unless you override.">
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-xs font-bold">Cut day <input type="date" value={cut} onChange={(e) => setCut(e.target.value)} className={field} /></label>
          <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={allowTest} onChange={(e) => setAllowTest(e.target.checked)} />include the locked test years (breaks the protocol)</label>
          <button className={btn} disabled={!signedIn || !!busy} onClick={() => void run('snap', () => makeSnapshot(cut, allowTest), 'Snapshot created.')}><ClipboardCheck className="w-3.5 h-3.5 inline mr-1" />Create snapshot</button>
        </div>
        {snaps.length > 0 && (
          <ul className="space-y-1">{snaps.map((s) => (
            <li key={s.id} className="flex items-center gap-3 text-[11px] border border-[#E2E8F2] rounded px-2 py-1 flex-wrap">
              <span className="font-mono font-bold">#{s.id}</span><span>cut {s.cut_day}</span><span className="font-mono">{num(s.n_rows)} rows</span>
              <span className="text-slate-500">{Object.entries(s.manifest.label_counts).map(([k, v]) => `${k} ${v}`).join(', ') || 'no labels'} · excluded years {s.manifest.excluded_years.length ? `${s.manifest.excluded_years[0]} to ${s.manifest.excluded_years[s.manifest.excluded_years.length - 1]}` : 'none'}</span>
              <span className="font-mono text-slate-400 truncate" title={s.sha256}>{s.sha256.slice(0, 12)}</span>
              <button className={`${btnQuiet} ml-auto`} onClick={() => void downloadSnapshot(s.id).catch(fail)}><Download className="w-3 h-3 inline mr-1" />JSONL</button>
            </li>))}</ul>)}
      </Section>

      <Section title="4. Models trained offline" hint="Train on a snapshot elsewhere (Kaggle or a GPU machine), then register the model with its metrics. The metrics are declared by the training job and are not verified here. A candidate becomes champion only when the gate passes.">
        <div className="flex items-end gap-2 flex-wrap">
          <label className="text-xs font-bold block">Name <input value={reg.name} onChange={(e) => setReg({ ...reg, name: e.target.value })} className={`${field} block w-28`} /></label>
          <label className="text-xs font-bold block">Version <input value={reg.version} onChange={(e) => setReg({ ...reg, version: e.target.value })} className={`${field} block w-20`} /></label>
          <label className="text-xs font-bold block flex-1 min-w-[16rem]">Metrics (JSON) <input value={reg.metrics} onChange={(e) => setReg({ ...reg, metrics: e.target.value })} className={`${field} block w-full font-mono`}
            placeholder='{"recall_at_budget":0.6,"false_alarms_per_1000":4,"protected_extremes_flagged":2,"false_alarm_budget_per_1000":5,"frozen_protocol":true,"test_years_untouched":true}' /></label>
          <button className={btn} disabled={!signedIn || !!busy || !reg.version || !reg.metrics} onClick={regModel}>Register</button>
        </div>
        {models.length > 0 && (
          <ul className="space-y-2">{models.map((m) => (
            <li key={m.id} className="border border-[#E2E8F2] rounded px-3 py-2 text-xs space-y-1">
              <div className="flex items-center gap-2 flex-wrap"><b>{m.name} {m.version}</b>
                <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono font-bold ${m.alias === 'champion' ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : m.alias === 'rejected' ? 'border-red-300 bg-red-50 text-red-700' : 'border-slate-300 bg-slate-50 text-slate-700'}`}>{m.alias}</span>
                {m.alias === 'challenger' && <button className={btn} disabled={!signedIn || !!busy} onClick={() => void run('promote' + m.id, () => promoteModel(m.id), 'Gate run. See the result on the model.')}>Run the gate</button>}
                {m.alias === 'champion' && <button className={btnQuiet} disabled={!signedIn || !!busy} onClick={() => void run('rollback', () => rollbackModel(m.name), 'Rolled back to the previous champion.')}>Roll back</button>}</div>
              {m.gate && <ul className="font-mono text-[11px]">{m.gate.checks.map((c) => <li key={c.rule} className={c.passed ? 'text-emerald-700' : 'text-red-700'}>{c.passed ? 'pass' : 'FAIL'} · {c.rule}: {c.detail}</li>)}</ul>}
              <div className="text-[10px] text-slate-500">{m.metrics_basis}</div>
            </li>))}</ul>)}
      </Section>
    </div>
  );
}
