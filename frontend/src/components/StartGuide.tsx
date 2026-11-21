// "Start here" on the Overview: what the platform is in one line, then four steps with a button each. Stays until dismissed (remembered in
// localStorage); "Show the guide" in the legend brings it back.
import { useState } from 'react';
import { GUIDE_INTRO, GUIDE_STEPS, dismissGuide, isGuideDismissed } from '../validation/guide';
import type { PageId } from '../validation/shell';
import { openStationPicker } from './PageIntro';

const store = (): Storage | null => { try { return window.localStorage; } catch { return null; } };

export function StartGuide({ onNavigate }: { onNavigate: (p: PageId) => void }) {
  const [hidden, setHidden] = useState(() => isGuideDismissed(store()));
  if (hidden) return null;
  return (
    <section className="bg-[#FFFFFF] border border-sky-500/50 rounded-xl p-4 shadow-sm space-y-3" aria-label="Start here" data-testid="start-guide">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900">Start here</h3>
          <p className="text-xs text-slate-700 mt-0.5">{GUIDE_INTRO}</p>
        </div>
        <button onClick={() => { dismissGuide(store()); setHidden(true); }} className="text-xs font-semibold text-slate-600 hover:text-slate-900 shrink-0 underline">
          Got it, hide this
        </button>
      </div>
      <ol className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        {GUIDE_STEPS.map((s) => (
          <li key={s.n} className="border border-[#D3DCE7] bg-[#F4F6FA] rounded-lg p-3 flex flex-col gap-2">
            <div className="text-xs font-bold text-slate-900"><span className="font-mono text-sky-700">{s.n}.</span> {s.title}</div>
            <p className="text-[11px] text-slate-600 flex-1">{s.text}</p>
            <button
              onClick={() => (s.target === 'pick-station' ? openStationPicker() : onNavigate(s.target))}
              className="self-start px-3 py-1.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg shadow"
            >
              {s.button}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
