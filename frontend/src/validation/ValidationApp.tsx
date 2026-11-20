// The validation platform shell: a white rail of seven numbered steps (a check mark once a step has data), a large page title with a faint
// rain touch, and the step's page. Every page ends with a "Next: <step>" button. Steps: Import, Explore & clean, Stations, Validate, Review,
// Anomalies, Models. #/app opens step 1; #/app/<step> opens a step directly.
import { useCallback, useEffect, useState } from 'react';
import { Check } from 'lucide-react';
import { getExploreStations, getReviewSummary, listJobs, listModels, listSnapshots } from './api';
import { AnomaliesView } from './AnomaliesView';
import { ExploreView } from './ExploreView';
import { ImportView } from './ImportView';
import { AdminChip } from './Login';
import { ModelsView } from './ModelsView';
import { ReviewView } from './ReviewView';
import { StationsView } from './StationsView';
import { ValidateView } from './ValidateView';
import { NO_FACTS, STEPS, doneSteps, nextStep, stepFromHash, stepHash } from './steps';
import type { StepFacts, StepId } from './steps';
import type { ImportedJob } from './types';

function DropMark() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.2c3.4 4.4 6.2 7.7 6.2 11.3a6.2 6.2 0 1 1-12.4 0c0-3.6 2.8-6.9 6.2-11.3z" fill="#0E7490" />
      <path d="M9 14.2a3.2 3.2 0 0 0 2.4 3" stroke="#fff" strokeOpacity=".8" strokeWidth="1.3" strokeLinecap="round" fill="none" />
    </svg>);
}

/** The page title: big, plain, one line under it, and a faint rain touch on the right (it stops under reduced motion). */
function PageHead({ n, title, line }: { n: number; title: string; line: string }) {
  return (
    <header className="rain-head">
      <div className="rain-layer" aria-hidden="true" />
      <div className="relative">
        <p className="text-xs font-mono text-slate-500">Step {n} of {STEPS.length}</p>
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-slate-900">{title}</h1>
        <p className="text-sm text-slate-600 mt-1.5 max-w-3xl">{line}</p>
      </div>
    </header>);
}

export function ValidationApp() {
  const [tab, setTab] = useState<StepId>(() => stepFromHash(window.location.hash));
  const [runId, setRunId] = useState<number | null>(null);
  const [jobs, setJobs] = useState<ImportedJob[]>([]);
  const [facts, setFacts] = useState<StepFacts>(NO_FACTS);

  const go = useCallback((id: StepId) => { setTab(id); if (window.location.hash !== stepHash(id)) window.location.hash = stepHash(id); window.scrollTo?.(0, 0); }, []);
  useEffect(() => {
    const on = () => setTab(stepFromHash(window.location.hash));
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);

  const jobFacts = (j: ImportedJob[]) => ({ jobsDone: j.filter((x) => x.status === 'done').length, jobsChecked: j.filter((x) => x.run_id !== null).length });
  // what the platform holds, asked again whenever the step changes (counts only)
  const reload = useCallback(() => {
    listJobs().then((r) => { setJobs(r.jobs); setFacts((f) => ({ ...f, ...jobFacts(r.jobs) })); }).catch(() => undefined);
    getExploreStations().then((r) => setFacts((f) => ({ ...f, locatedStations: r.located }))).catch(() => undefined);
    getReviewSummary().then((r) => setFacts((f) => ({ ...f, reviewedRows: r.reviewed_rows }))).catch(() => undefined);
    listSnapshots().then((r) => setFacts((f) => ({ ...f, snapshots: r.snapshots.length }))).catch(() => undefined);
    listModels().then((r) => setFacts((f) => ({ ...f, models: r.models.length }))).catch(() => undefined);
  }, []);
  useEffect(reload, [tab, reload]);

  const onJobs = useCallback((j: ImportedJob[]) => { setJobs(j); setFacts((f) => ({ ...f, ...jobFacts(j) })); }, []);
  const explored = useCallback(() => setFacts((f) => (f.explored ? f : { ...f, explored: true })), []);
  const anomaliesOpened = useCallback(() => setFacts((f) => (f.anomaliesOpened ? f : { ...f, anomaliesOpened: true })), []);
  const pickRun = useCallback((id: number | null) => { setRunId(id); if (id !== null) reload(); }, [reload]);

  const done = doneSteps(facts);
  const stepIndex = Math.max(0, STEPS.findIndex((s) => s.id === tab));
  const step = STEPS[stepIndex];
  const next = (id: StepId) => { const n = nextStep(id); if (n) go(n.id); };

  return (
    <div className="rain-app min-h-screen flex flex-col md:flex-row text-slate-900">
      <nav className="rain-nav md:w-60 md:shrink-0 md:h-screen md:sticky md:top-0 p-3 flex md:block gap-1 overflow-x-auto md:overflow-y-auto" aria-label="steps">
        <a href="#/" title="Back to the home page" className="hidden md:flex items-center gap-2.5 px-3 pt-2 pb-3">
          <DropMark />
          <div className="leading-tight"><div className="font-semibold text-slate-900 text-[15px]">DataMend</div><div className="text-[11px] text-slate-500">Rainfall validation</div></div>
        </a>
        <ol className="flex md:block gap-1 list-none m-0 p-0">
          {STEPS.map((s, i) => (
            <li key={s.id} className="shrink-0 md:shrink">
              <button onClick={() => go(s.id)} aria-current={tab === s.id ? 'step' : undefined} className="rain-nav-item rain-step md:mb-0.5">
                <span className={`rain-step-dot ${done[s.id] ? 'is-done' : ''}`} aria-hidden="true">{done[s.id] ? <Check className="w-3 h-3" /> : i + 1}</span>
                <span>{s.label}</span>
                <span className="sr-only">{done[s.id] ? ' (has data)' : ' (no data yet)'}</span>
              </button>
            </li>))}
        </ol>
        <div className="hidden md:block"><AdminChip onSignIn={() => { window.location.hash = '#/login'; }} /></div>
      </nav>
      <main className="flex-1 px-4 py-6 md:px-10 md:py-8 min-w-0 max-w-[1400px] space-y-6">
        <PageHead n={stepIndex + 1} title={step.label} line={step.line} />
        {tab === 'import' && <ImportView onNext={() => next('import')} onJobs={onJobs} />}
        {tab === 'explore' && <ExploreView jobs={jobs} onExplored={explored} onNext={() => next('explore')} />}
        {tab === 'stations' && <StationsView onNext={() => next('stations')} />}
        {tab === 'validate' && <ValidateView jobs={jobs} runId={runId} onRun={pickRun} onNext={() => next('validate')} />}
        {tab === 'review' && <ReviewView runId={runId} onNext={() => next('review')} />}
        {tab === 'anomalies' && <AnomaliesView jobs={jobs} runId={runId} onRun={pickRun} onOpened={anomaliesOpened} onNext={() => next('anomalies')} />}
        {tab === 'models' && <ModelsView onOpenRun={(id) => { pickRun(id); go('anomalies'); }} />}
      </main>
    </div>
  );
}
