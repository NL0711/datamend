// The validation platform shell. The rail has the original four items of the spec (Runs, Run view, Live gauge feed, Settings) plus the
// rainfall-relevant views brought back from the old dashboard at the owner's request: Overview, Data Explorer, Review queue (the admin
// review loop), Anomaly Lab (synthetic faults) and Locations (place lookup). The old Sensor Health and alerting views stay out: they were
// about hardware health trends and notifications, which are outside this platform.
import { useState } from 'react';
import { Compass, Database, Droplets, FileSearch, FlaskConical, ListChecks, MapPin, Radio, Settings, ShieldCheck } from 'lucide-react';
import { ExplorerView } from './ExplorerView';
import { LabView } from './LabView';
import { LiveFeedView } from './LiveFeedView';
import { OverviewView, Tab } from './OverviewView';
import { PlacesView } from './PlacesView';
import { ReviewView } from './ReviewView';
import { RunView } from './RunView';
import { RunsView } from './RunsView';
import { SettingsView } from './SettingsView';

const NAV: { id: Tab; label: string; icon: typeof ListChecks }[] = [
  { id: 'overview', label: 'Overview', icon: Compass },
  { id: 'runs', label: 'Runs', icon: ListChecks },
  { id: 'run', label: 'Run view', icon: FileSearch },
  { id: 'explorer', label: 'Data explorer', icon: Database },
  { id: 'review', label: 'Review queue', icon: ShieldCheck },
  { id: 'lab', label: 'Anomaly lab', icon: FlaskConical },
  { id: 'places', label: 'Locations', icon: MapPin },
  { id: 'live', label: 'Live gauge feed', icon: Radio },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export function ValidationApp() {
  const [tab, setTab] = useState<Tab>('overview');
  const [runId, setRunId] = useState<number | null>(null);
  const open = (id: number) => { setRunId(id); setTab('run'); };

  return (
    <div className="min-h-screen flex bg-[#F4F6FA] text-slate-900">
      <nav className="w-52 shrink-0 bg-white border-r border-[#D3DCE7] p-3 space-y-1" aria-label="main">
        <div className="flex items-center gap-2 px-2 py-3 font-bold"><Droplets className="w-5 h-5 text-sky-600" />DataMend<span className="text-[10px] font-mono text-slate-500 font-normal">rainfall validation</span></div>
        {NAV.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setTab(id)} aria-current={tab === id ? 'page' : undefined}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded text-xs font-bold text-left ${tab === id ? 'bg-sky-600 text-white' : 'text-slate-600 hover:bg-[#F4F6FA]'}`}>
            <Icon className="w-4 h-4" />{label}</button>))}
      </nav>
      <main className="flex-1 p-4 min-w-0">
        {tab === 'overview' && <OverviewView onOpenRun={open} go={setTab} />}
        {tab === 'runs' && <RunsView onOpen={open} />}
        {tab === 'run' && (runId === null
          ? <p className="text-xs text-slate-600">No run selected. Open one from <button className="text-sky-700 font-bold" onClick={() => setTab('runs')}>Runs</button>.</p>
          : <RunView key={runId} runId={runId} />)}
        {tab === 'explorer' && <ExplorerView key={runId ?? 'none'} initialRunId={runId} />}
        {tab === 'review' && <ReviewView />}
        {tab === 'lab' && <LabView onOpenRun={open} />}
        {tab === 'places' && <PlacesView />}
        {tab === 'live' && <LiveFeedView onOpenRun={open} />}
        {tab === 'settings' && <SettingsView />}
      </main>
    </div>
  );
}
