// The Cleaning tab: what the dataset is (profile), the cleaning policy you control, the assistant's advice, the plan, and the proposals to
// accept or reject before anything is applied. Words come from the profile (parameter and units), so the same screen works for any
// parameter. Everything generated is badged GENERATED; interpolated values are badged IMPUTED and are never measurements.
import { useCallback, useEffect, useState } from 'react';
import { applyCleaning, askAssistant, decideCleanProposal, getDefaultPolicy, getExploreProfile, listCleanProposals, planCleaning } from './api';
import { ReplyCard } from './AssistantPanel';
import {
  BEST_CLEANING_QUESTION, NO_OVERRIDE, applyProfileDefaults, applySuggestion, buildPlanBody, canToggle, describeProfile, isFillStep, overrideValid, planBlockedReason, setEnabled,
  setParam, stepTitle, suggestionHint,
} from './cleaning';
import type { Override } from './cleaning';
import { useAdmin } from './Login';
import type { AssistantReply, CleanApplyResult, CleanPlanResult, CleanPolicy, CleanProposal, DatasetProfile, PolicyStep } from './types';
import { GeneratedBadge, ImputedBadge, Notice, Panel, btn, btnQuiet, field, formatError } from './ui';

const FILL_METHODS = ['none', 'linear', 'previous'];

function ParamInput({ step, k, v, onChange, disabled }: { step: PolicyStep; k: string; v: unknown; onChange: (v: unknown) => void; disabled: boolean }) {
  const label = k.replace(/_/g, ' ');
  const aria = `${stepTitle(step.id)} ${label}`;
  if (k === 'method' && typeof v === 'string') {
    return <label className="text-[11px] font-bold block">{label}<select value={v} disabled={disabled} onChange={(e) => onChange(e.target.value)} className={`${field} block`} aria-label={aria}>
      {(FILL_METHODS.includes(v) ? FILL_METHODS : [...FILL_METHODS, v]).map((m) => <option key={m} value={m}>{m}</option>)}</select></label>;
  }
  if (typeof v === 'number') {
    return <label className="text-[11px] font-bold block">{label}<input type="number" value={v} disabled={disabled} onChange={(e) => { const n = Number(e.target.value); if (Number.isFinite(n)) onChange(n); }} className={`${field} block w-28`} aria-label={aria} /></label>;
  }
  if (typeof v === 'boolean') {
    return <label className="text-[11px] font-bold flex items-center gap-1"><input type="checkbox" checked={v} disabled={disabled} onChange={(e) => onChange(e.target.checked)} aria-label={aria} />{label}</label>;
  }
  if (Array.isArray(v) && v.length === 2 && v.every((x) => x === null || typeof x === 'number')) {
    return (
      <div className="text-[11px] font-bold"><span className="block">{label}</span>
        <span className="flex gap-1">{[0, 1].map((i) => (
          <input key={i} type="number" value={v[i] ?? ''} disabled={disabled} aria-label={`${aria} ${i === 0 ? 'low' : 'high'}`} className={`${field} w-24`}
                 onChange={(e) => { const next = [...v]; next[i] = e.target.value === '' ? null : Number(e.target.value); onChange(next); }} />))}</span></div>);
  }
  if (typeof v === 'string') {
    return <label className="text-[11px] font-bold block">{label}<input value={v} disabled={disabled} onChange={(e) => onChange(e.target.value)} className={`${field} block w-36`} aria-label={aria} /></label>;
  }
  return <div className="text-[11px]"><span className="font-bold">{label}</span> <span className="font-mono">{JSON.stringify(v)}</span></div>;
}

function PolicyEditor({ policy, onPolicy, override, onOverride }: { policy: CleanPolicy; onPolicy: (p: CleanPolicy) => void; override: Override; onOverride: (o: Override) => void }) {
  const lockedSteps = policy.steps.filter((s) => s.locked);
  return (
    <div className="space-y-2">
      <ol className="space-y-2">
        {policy.steps.map((s, i) => {
          const unlocked = canToggle(s, override);
          return (
            <li key={s.id} className={`rounded border px-3 py-2 ${s.locked && !s.enabled ? 'border-amber-300 bg-amber-50' : 'border-[#D3DCE7]'}`}>
              <div className="flex items-center gap-3 flex-wrap">
                <span className="w-5 h-5 rounded-full bg-slate-200 text-[10px] font-bold flex items-center justify-center">{i + 1}</span>
                <label className="flex items-center gap-2 text-xs font-bold">
                  <input type="checkbox" role="switch" checked={s.enabled} disabled={s.locked && !unlocked && !s.enabled} aria-label={`${stepTitle(s.id)} switch`}
                         onChange={(e) => onPolicy(setEnabled(policy, s.id, e.target.checked, override))} />
                  {stepTitle(s.id)}</label>
                {s.locked && <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border border-amber-400 bg-amber-100 text-amber-900">{s.enabled ? 'OVERRIDDEN' : 'LOCKED OFF'}</span>}
                {isFillStep(s) && s.enabled && <ImputedBadge />}
                <span className="flex gap-3 flex-wrap ml-auto items-end">{Object.entries(s.params).map(([k, v]) => (
                  <ParamInput key={k} step={s} k={k} v={v} disabled={!s.enabled} onChange={(nv) => onPolicy(setParam(policy, s.id, k, nv))} />))}</span>
              </div>
              {s.locked && s.locked_reason && <p className="text-[11px] text-amber-900 mt-1" data-testid={`lock-${s.id}`}>Locked: {s.locked_reason}.</p>}
            </li>);
        })}
      </ol>
      {lockedSteps.length > 0 && (
        <div className="rounded border border-amber-300 px-3 py-2 space-y-1.5 text-xs">
          <label className="flex items-start gap-2 font-bold"><input type="checkbox" className="mt-0.5" checked={override.ack} onChange={(e) => onOverride({ ...override, ack: e.target.checked })} />
            <span>I understand, override <span className="font-normal">(lets you switch on {lockedSteps.map((s) => stepTitle(s.id).toLowerCase()).join(', ')}; your reason is stored with the plan)</span></span></label>
          <input value={override.reason} disabled={!override.ack} onChange={(e) => onOverride({ ...override, reason: e.target.value })} className={`${field} w-full`} aria-label="override reason"
                 placeholder="Why is this safe? For example: the supplier confirmed that missing hours are not dry hours." />
          {override.ack && !overrideValid(override) && <p className="text-[11px] text-amber-900">Type a reason (at least 5 characters) to unlock the switch.</p>}
        </div>)}
    </div>);
}

export function CleaningPanel({ sources }: { sources: string[] }) {
  const { signedIn } = useAdmin();
  const [source, setSource] = useState(sources[0] ?? '');
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [policy, setPolicy] = useState<CleanPolicy | null>(null);
  const [override, setOverride] = useState<Override>(NO_OVERRIDE);
  const [advice, setAdvice] = useState<AssistantReply | null>(null);
  const [adviceNote, setAdviceNote] = useState('');
  const [plan, setPlan] = useState<CleanPlanResult | null>(null);
  const [proposals, setProposals] = useState<CleanProposal[]>([]);
  const [applied, setApplied] = useState<CleanApplyResult | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => { if (!source && sources[0]) setSource(sources[0]); }, [sources, source]);
  useEffect(() => {
    if (!source) return;
    setProfile(null); setPolicy(null); setOverride(NO_OVERRIDE); setAdvice(null); setPlan(null); setProposals([]); setApplied(null); setError('');
    let live = true;
    Promise.all([getExploreProfile(source), getDefaultPolicy(source)])
      .then(([p, d]) => { if (live) { setProfile(p); setPolicy(applyProfileDefaults(d, p)); } })
      .catch((e) => live && setError(formatError(e)));
    return () => { live = false; };
  }, [source]);

  const loadProposals = useCallback(() => listCleanProposals({ limit: 200 }).then((r) => setProposals(r.proposals)), []);
  const run = async (label: string, fn: () => Promise<unknown>) => { setBusy(label); setError(''); try { await fn(); } catch (e) { setError(formatError(e)); } finally { setBusy(''); } };

  // when the override stops being valid, a locked step that was switched on goes back off
  const changeOverride = (o: Override) => {
    setOverride(o);
    if (!overrideValid(o) && policy) setPolicy({ steps: policy.steps.map((s) => (s.locked ? { ...s, enabled: false } : s)) });
  };

  const view = profile ? describeProfile(profile) : null;
  const blocked = policy ? planBlockedReason(policy, override) : null;
  const pending = proposals.filter((p) => p.status === 'pending');
  const u = view && view.units !== 'unknown' ? ` ${view.units}` : '';

  const ask = () => void run('ask', async () => {
    setAdviceNote('');
    setAdvice(await askAssistant(BEST_CLEANING_QUESTION, [], null));
  });
  const useSuggestion = () => {
    if (!policy) return;
    const r = applySuggestion(policy, suggestionHint(advice));
    setPolicy(r.policy);
    setAdviceNote(r.ignored.length ? `Applied to the editor. Left out: ${r.ignored.join('; ')}.` : 'Applied to the editor. Nothing is planned until you press Plan cleaning.');
  };
  const doPlan = () => policy && void run('plan', async () => {
    setApplied(null);
    setPlan(await planCleaning(buildPlanBody(source, policy, override)));
    await loadProposals();
  });
  const decide = (id: number, accept: boolean) => void run('d' + id, async () => { await decideCleanProposal(id, accept); await loadProposals(); });
  const acceptAll = () => void run('all', async () => { for (const p of pending) await decideCleanProposal(p.id, true); await loadProposals(); });
  const apply = () => void run('apply', async () => { setApplied(await applyCleaning()); await loadProposals(); });

  if (sources.length === 0) return <Notice tone="info">Import a dataset first (step 1); cleaning works on what was imported.</Notice>;

  return (
    <div className="space-y-3">
      {error && <Notice tone="error">{error}</Notice>}
      {!signedIn && <Notice tone="warn">Sign in to plan, accept or apply cleaning.</Notice>}
      <label className="text-xs font-bold block">Dataset (source)
        <select value={source} onChange={(e) => setSource(e.target.value)} className={`${field} block mt-1`} aria-label="source to clean">{sources.map((s) => <option key={s} value={s}>{s}</option>)}</select></label>

      <Panel className="p-3 space-y-2" >
        <h3 className="text-sm font-bold text-slate-900">Dataset profile</h3>
        {!view ? <p className="text-xs text-slate-500">Loading the profile…</p> : (
          <>
            <dl className="grid grid-cols-2 md:grid-cols-3 gap-2 text-[11px]">
              {([['Parameter', view.parameter], ['Kind', view.kind], ['Zero values', view.zeros], ['Cadence', view.cadence], ['Units', view.units], ['Valid range', view.range], ['Missing-value codes', view.missing]] as const).map(([k, v]) => (
                <div key={k} className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-2 py-1"><dt className="text-[10px] uppercase font-mono text-slate-500">{k}</dt><dd className="font-mono">{v}</dd></div>))}
            </dl>
            {profile && profile.evidence.length > 0 && (
              <div><div className="text-[10px] uppercase font-mono text-slate-500">Evidence (detected from the data, basis: derived)</div>
                <ul className="list-disc ml-4 text-xs text-slate-700">{profile.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul></div>)}
            {profile?.notes && <p className="text-[11px] text-slate-600">{profile.notes}</p>}
            {view.validationNote && <Notice tone="info">{view.validationNote}</Notice>}
          </>)}
      </Panel>

      <Panel className="p-3 space-y-3">
        <div><h3 className="text-sm font-bold text-slate-900">Cleaning policy</h3>
          <p className="text-[11px] text-slate-600">Steps run in this order. Defaults come from the profile above; nothing changes your data until you plan, accept and apply.</p></div>
        {!policy ? <p className="text-xs text-slate-500">Loading the policy…</p> : <PolicyEditor policy={policy} onPolicy={setPolicy} override={override} onOverride={changeOverride} />}

        <div className="border-t border-[#E2E8F2] pt-2 space-y-2">
          <button className={btnQuiet} disabled={busy === 'ask'} onClick={ask}>{busy === 'ask' ? 'Asking…' : 'Ask the assistant: what is the best cleaning for my data?'}</button>
          {advice && (
            <ReplyCard reply={advice}>
              {advice.cleaning?.plan_hint ? <button className={btn} onClick={useSuggestion} disabled={!policy}>Use this suggestion</button>
                : <p className="text-[11px] text-slate-500">The assistant proposed no policy change.</p>}
              {adviceNote && <p className="text-[11px] text-slate-700">{adviceNote}</p>}
            </ReplyCard>)}
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <button className={`${btn} px-4 py-2 text-sm`} disabled={!signedIn || !policy || !!blocked || busy === 'plan'} onClick={doPlan}>{busy === 'plan' ? 'Planning…' : 'Plan cleaning'}</button>
          {blocked && <span className="text-[11px] text-amber-900">{blocked}</span>}
        </div>
      </Panel>

      {plan && plan.skipped.length > 0 && (
        <div className="rounded border-2 border-amber-400 bg-amber-50 px-3 py-2 text-xs text-amber-950 space-y-1" role="alert" data-testid="refused">
          <div className="font-bold">Some data was not touched</div>
          <ul className="list-disc ml-4">{plan.skipped.map((s, i) => <li key={i}><b>{s.station_key}</b>: {s.reason} ({s.count.toLocaleString('en-IN')} affected)</li>)}</ul>
        </div>)}

      {(plan || proposals.length > 0) && (
        <Panel className="p-3 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-sm font-bold text-slate-900">Proposals</h3><GeneratedBadge />
            <span className="text-[11px] font-mono text-slate-500">{plan ? `${plan.created} created · ` : ''}{pending.length} pending of {proposals.length}</span>
            <span className="ml-auto flex gap-2">
              <button className={btnQuiet} disabled={!signedIn || pending.length === 0 || !!busy} onClick={acceptAll}>Accept all pending ({pending.length})</button>
              <button className={btn} disabled={!signedIn || !!busy || proposals.every((p) => p.status === 'pending')} onClick={apply}>Apply</button>
            </span>
          </div>
          {applied && <Notice tone="info">Applied: {applied.accepted} accepted, {applied.interpolated} interpolated (imputed), {applied.excluded} excluded. The original values are kept; corrections are stored separately.</Notice>}
          {proposals.length === 0 ? <p className="text-xs text-slate-500">No proposals: nothing in this policy needed a change.</p> : (
            <ul className="space-y-2 max-h-[32rem] overflow-y-auto">{proposals.map((p) => (
              <li key={p.id} className="rounded border border-dashed border-slate-400 bg-slate-50 px-3 py-2 text-xs space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono font-bold">{p.station_key}</span><span className="font-mono text-slate-500">{p.at}</span>
                  <span className="font-mono">{p.kind}</span>{p.kind === 'interpolate' && <ImputedBadge />}
                  <span className="font-mono">{p.original === null ? 'missing' : `${p.original}${u}`} → {p.kind === 'exclude' ? 'excluded' : p.proposed === null ? '?' : `${p.proposed}${u}`}</span>
                  <span className="font-mono text-slate-500">{p.method} · basis: {p.basis}</span><span className="ml-auto font-mono font-bold">{p.status}</span></div>
                <p className="text-slate-800">{p.why}</p>
                {p.neighbours.length > 0 && <p className="text-[11px] font-mono text-slate-600">neighbours: {p.neighbours.map((n) => `${n.at} = ${n.value ?? 'missing'}`).join(' · ')}</p>}
                {p.status === 'pending' && (
                  <div className="flex gap-2"><button className={btn} disabled={!signedIn || !!busy} onClick={() => decide(p.id, true)}>Accept</button>
                    <button className={btnQuiet} disabled={!signedIn || !!busy} onClick={() => decide(p.id, false)}>Reject</button></div>)}
              </li>))}</ul>)}
          <p className="text-[10px] text-slate-500">Proposals are suggestions generated by rules. Interpolated values are imputed, never measured. Accepting records your decision; Apply writes the accepted ones as separate corrected values.</p>
        </Panel>)}
    </div>);
}
