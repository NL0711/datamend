// The validation platform shell: a rail with four items (spec section 7): Runs, Run view, Live gauge feed, Settings.
import { useState } from 'react';
import { Droplets, FileSearch, ListChecks, Radio, Settings } from 'lucide-react';
import { LiveFeedView } from './LiveFeedView';
import { RunView } from './RunView';
import { RunsView } from './RunsView';
import { SettingsView } from './SettingsView';

type Tab = 'runs' | 'run' | 'live' | 'settings';
const NAV: { id: Tab; label: string; icon: typeof ListChecks }[] = [
  { id: 'runs', label: 'Runs', icon: ListChecks },
  { id: 'run', label: 'Run view', icon: FileSearch },
  { id: 'live', label: 'Live gauge feed', icon: Radio },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export function ValidationApp() {
  const [tab, setTab] = useState<Tab>('runs');
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
        <p className="px-2 pt-4 text-[10px] text-slate-500">Prototype of the platform: rules and a neighbour check, no trained model, no real-label accuracy claimed. Uploaded runs live in demo storage that resets on restart.</p>
      </nav>
      <main className="flex-1 p-4 min-w-0">
        {tab === 'runs' && <RunsView onOpen={open} />}
        {tab === 'run' && (runId === null
          ? <p className="text-xs text-slate-600">No run selected. Open one from <button className="text-sky-700 font-bold" onClick={() => setTab('runs')}>Runs</button>.</p>
          : <RunView key={runId} runId={runId} />)}
        {tab === 'live' && <LiveFeedView onOpenRun={open} />}
        {tab === 'settings' && <SettingsView />}
      </main>
    </div>
  );
}
