// The validation platform shell: a white rail, a large page title with a faint rain touch (never over the data),
// and the views. The rail has the original four items of the spec (Runs, Run view, Live gauge feed, Settings) plus the rainfall-relevant
// views brought back from the old dashboard: Overview, Station network, Data Explorer, Review queue (the admin review loop), Anomaly Lab
// (synthetic faults) and Locations (place lookup). The old Sensor Health and alerting views stay out: they were about hardware health
// trends and notifications, which are outside this platform.
import { useState } from 'react';
import { Compass, Database, FileSearch, FlaskConical, ListChecks, MapPin, Network, Radio, Settings, ShieldCheck } from 'lucide-react';
import { ExplorerView } from './ExplorerView';
import { LabView } from './LabView';
import { LiveFeedView } from './LiveFeedView';
import { NetworkView } from './NetworkView';
import { OverviewView, Tab } from './OverviewView';
import { PlacesView } from './PlacesView';
import { ReviewView } from './ReviewView';
import { RunView } from './RunView';
import { RunsView } from './RunsView';
import { SettingsView } from './SettingsView';

const NAV: { id: Tab; label: string; icon: typeof ListChecks }[] = [
  { id: 'overview', label: 'Overview', icon: Compass },
  { id: 'network', label: 'Station network', icon: Network },
  { id: 'runs', label: 'Runs', icon: ListChecks },
  { id: 'run', label: 'Run view', icon: FileSearch },
  { id: 'explorer', label: 'Data explorer', icon: Database },
  { id: 'review', label: 'Review queue', icon: ShieldCheck },
  { id: 'lab', label: 'Anomaly lab', icon: FlaskConical },
  { id: 'places', label: 'Locations', icon: MapPin },
  { id: 'live', label: 'Live gauge feed', icon: Radio },
  { id: 'settings', label: 'Settings', icon: Settings },
];

/** One plain line per page, under its title in the sky band. */
const HEADINGS: Record<Tab, string> = {
  overview: 'What the platform holds right now: runs, verdicts and the live feed.',
  network: 'Every gauge and IMD station on the map, and where each one is in check, flag and audit.',
  runs: 'Each upload, replay and live rain day, with its report.',
  run: 'One run: the series, its flags and the evidence behind each.',
  explorer: 'Browse the rows of a run by station, time and verdict.',
  review: 'Flagged rows waiting for a reviewer\'s decision.',
  lab: 'Generate synthetic faults and see whether the checks catch them.',
  places: 'Look up a point on the RF25 grid, and browse the gauge catalogue.',
  live: 'Weather Union rain gauges, polled within a daily call budget.',
  settings: 'The live feed, the AI narrator and admin access.',
};

/** Rail groups: the items stay in the same order, the group labels only help the eye. */
const GROUPS: { label: string; ids: Tab[] }[] = [
  { label: 'Monitor', ids: ['overview', 'network', 'live'] },
  { label: 'Validate', ids: ['runs', 'run', 'explorer', 'review'] },
  { label: 'Tools', ids: ['lab', 'places', 'settings'] },
];

function DropMark() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 2.2c3.4 4.4 6.2 7.7 6.2 11.3a6.2 6.2 0 1 1-12.4 0c0-3.6 2.8-6.9 6.2-11.3z" fill="#0E7490" />
      <path d="M9 14.2a3.2 3.2 0 0 0 2.4 3" stroke="#fff" strokeOpacity=".8" strokeWidth="1.3" strokeLinecap="round" fill="none" />
    </svg>);
}

/** The page title: big, plain, one line under it, and a faint rain touch on the right (it stops under reduced motion). */
function PageHead({ title, line }: { title: string; line: string }) {
  return (
    <header className="rain-head">
      <div className="rain-layer" aria-hidden="true" />
      <div className="relative">
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight text-slate-900">{title}</h1>
        <p className="text-sm text-slate-600 mt-1.5 max-w-3xl">{line}</p>
      </div>
    </header>);
}

export function ValidationApp() {
  const [tab, setTab] = useState<Tab>('overview');
  const [runId, setRunId] = useState<number | null>(null);
  const [auditStation, setAuditStation] = useState('');
  const open = (id: number) => { setRunId(id); setTab('run'); };
  const audit = (station: string) => { setAuditStation(station); setTab('review'); };
  const title = NAV.find((n) => n.id === tab)?.label ?? '';

  return (
    <div className="rain-app min-h-screen flex flex-col md:flex-row text-slate-900">
      <nav className="rain-nav md:w-60 md:shrink-0 md:h-screen md:sticky md:top-0 p-3 flex md:block gap-1 overflow-x-auto md:overflow-y-auto" aria-label="main">
        <div className="hidden md:flex items-center gap-2.5 px-3 pt-2 pb-3">
          <DropMark />
          <div className="leading-tight"><div className="font-semibold text-slate-900 text-[15px]">DataMend</div><div className="text-[11px] text-slate-500">Rainfall validation</div></div>
        </div>
        {GROUPS.map((g) => (
          <div key={g.label} className="flex md:block gap-1">
            <div className="rain-nav-group hidden md:block">{g.label}</div>
            {g.ids.map((id) => {
              const item = NAV.find((n) => n.id === id) as (typeof NAV)[number];
              const Icon = item.icon;
              return (
                <button key={id} onClick={() => { if (id === 'review') setAuditStation(''); setTab(id); }} aria-current={tab === id ? 'page' : undefined} className="rain-nav-item md:mb-0.5">
                  <Icon className="w-4 h-4" />{item.label}</button>);
            })}
          </div>))}
      </nav>
      <main className="flex-1 px-4 py-6 md:px-10 md:py-8 min-w-0 max-w-[1400px] space-y-6">
        <PageHead title={title} line={HEADINGS[tab]} />
        {tab === 'overview' && <OverviewView onOpenRun={open} go={setTab} />}
        {tab === 'network' && <NetworkView onAudit={audit} onOpenRun={open} go={setTab} />}
        {tab === 'runs' && <RunsView onOpen={open} />}
        {tab === 'run' && (runId === null
          ? <p className="text-xs text-slate-600">No run selected. Open one from <button className="text-sky-700 font-bold" onClick={() => setTab('runs')}>Runs</button>.</p>
          : <RunView key={runId} runId={runId} />)}
        {tab === 'explorer' && <ExplorerView key={runId ?? 'none'} initialRunId={runId} />}
        {tab === 'review' && <ReviewView key={auditStation || 'all'} station={auditStation} onClearStation={() => setAuditStation('')} />}
        {tab === 'lab' && <LabView onOpenRun={open} />}
        {tab === 'places' && <PlacesView />}
        {tab === 'live' && <LiveFeedView onOpenRun={open} />}
        {tab === 'settings' && <SettingsView />}
      </main>
    </div>
  );
}
