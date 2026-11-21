// Agent page: pick what the agent reads (the station's live feed or its newest uploaded file), ask about the SELECTED station and read the generated
// answer. The event log of the task ("why") sits under the answer, folded. PROTOTYPE of a sandboxed, bounded decision-support agent: it only explains.
import { useCallback, useEffect, useState } from 'react';
import { askAgent, fetchAgentEvents, fetchAgentStatus, isAuthError } from '../services/api';
import type { AgentEventRow, AgentStatus, AgentTaskResult } from '../services/api';
import { useStation } from '../validation/StationContext';
import { AuthNotice } from './AuthNotice';
import { openStationPicker } from './PageIntro';
import { agentErrorText, describeEvent, isTransient, statusWords } from './agentText';

const card = 'bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg space-y-2';
const h3 = 'text-xs font-bold uppercase tracking-wider text-slate-900 font-mono';

type Source = 'live' | 'file';
const DEFAULT_TEXT: Record<Source, string> = {
  live: 'Comment on the current live feed of this station.',
  file: 'Why is the latest flag at this station there, and what should a reviewer do?',
};
const HELP: Record<Source, string> = {
  live: "The agent reads this station's latest stored readings and detections from the live stream, from a snapshot taken when you ask.",
  file: "The agent reads this station's newest uploaded-file run and its highest-scored flagged row. It needs a file imported on the Import page.",
};

export function AgentView() {
  const { stationId } = useStation();
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [source, setSource] = useState<Source>('live');
  const [text, setText] = useState(DEFAULT_TEXT.live);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needSignIn, setNeedSignIn] = useState(false);
  const [result, setResult] = useState<AgentTaskResult | null>(null);
  const [events, setEvents] = useState<AgentEventRow[] | null>(null);

  const fail = (e: unknown) => { setNeedSignIn(isAuthError(e)); setError(agentErrorText(e)); };

  useEffect(() => { fetchAgentStatus().then(setStatus).catch(fail); }, []);
  useEffect(() => { setResult(null); setEvents(null); setError(null); setNeedSignIn(false); }, [stationId]);

  const choose = (s: Source) => {
    setSource(s); setText(DEFAULT_TEXT[s]); setResult(null); setEvents(null); setError(null);
  };

  const ask = useCallback(async () => {
    if (!stationId) return;
    setBusy(true); setError(null); setNeedSignIn(false); setEvents(null);
    try {
      let r: AgentTaskResult;
      try {
        r = await askAgent(stationId, text, source);
      } catch (first) {
        if (!isTransient(first)) throw first;
        await new Promise((res) => setTimeout(res, 6000));       // a sleeping free-plan server: give it a moment, then ask once more
        r = await askAgent(stationId, text, source);
      }
      setResult(r);
      setEvents((await fetchAgentEvents(r.task_id)).events);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [stationId, text, source]);

  const seg = (on: boolean) => `px-3 py-1.5 rounded-md text-xs font-mono font-bold ${on ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`;

  return (
    <div className="space-y-4" data-testid="agent-view">
      <div className={card}>
        <h3 className={h3}>Agent (PROTOTYPE)</h3>
        <p className="text-xs text-slate-600">
          A prototype of a sandboxed, bounded decision-support agent. It reads this station's results through read-only tools and writes an explanation (generated text).
          It never changes a verdict, score, evidence or raw data.
        </p>
        {status && (status.connected
          ? <p className="text-xs font-mono text-slate-700">Agent connected.</p>
          : <p role="status" className="text-xs font-mono text-amber-800">Agent not connected. The rule-based explanation still works.</p>)}
      </div>

      <div className={card}>
        <h3 className={h3}>Ask about {stationId ?? 'a station'}</h3>
        {!stationId && (
          <div className="flex items-center gap-3">
            <p className="text-xs text-slate-600">The agent answers about one station. Pick a station first.</p>
            <button onClick={openStationPicker} className="px-3 py-1.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg shadow">Pick a station</button>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs font-mono text-slate-600">Read from</span>
          <div className="inline-flex rounded-lg bg-slate-100 p-0.5" role="tablist" aria-label="What the agent reads">
            <button role="tab" aria-selected={source === 'live'} className={seg(source === 'live')} onClick={() => choose('live')}>Live feed</button>
            <button role="tab" aria-selected={source === 'file'} className={seg(source === 'file')} onClick={() => choose('file')}>Uploaded file</button>
          </div>
        </div>
        <p className="text-xs text-slate-600">{HELP[source]}</p>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={1000} aria-label="Question for the agent"
          className="w-full text-xs border border-[#D3DCE7] rounded-lg p-2 font-mono" />
        <button onClick={ask} disabled={!stationId || busy || !text.trim()} className="px-3 py-2 bg-sky-500 hover:bg-sky-400 disabled:opacity-50 text-slate-950 font-mono font-bold text-xs rounded-lg shadow">
          {busy ? 'Working...' : 'Ask the agent'}
        </button>
        {needSignIn && <AuthNotice text="Asking the agent needs an admin sign-in." />}
        {error && !needSignIn && <p role="alert" className="text-xs text-red-700 font-mono">{error}</p>}
      </div>

      {result && (
        <div className={card}>
          <h3 className={h3}>Answer</h3>
          <p className="text-xs font-mono text-slate-700">{statusWords(result.status)}</p>
          {result.abstain_reason && <p className="text-xs text-slate-600">Reason: {result.abstain_reason}</p>}
          {result.live && (
            <p className="text-xs font-mono text-slate-600">
              Feed {result.live.feed_state_at_perception}{result.live.feed_state_at_gate && result.live.feed_state_at_gate !== result.live.feed_state_at_perception ? `, then ${result.live.feed_state_at_gate}` : ''}
              {' · '}{result.live.n_readings} readings read{result.live.last_reading_at ? `, last at ${result.live.last_reading_at}` : ''}
              {' · '}last verdict {result.live.last_verdict ?? 'none'} · {result.live.detections_in_window} detections in the window
              {' · '}checks not run: {result.live.checks_not_run_available === false ? 'not available' : 'see the comment'}
              {result.live.model_score_present ? ` · model score present (${result.live.model_score_label})` : ''}
              {' · '}snapshot up to reading {result.live.snapshot.cutoff_id}
            </p>
          )}
          {result.explanation && (
            <div>
              <span className="text-[10px] font-mono font-bold uppercase text-amber-800">generated by the model; not evidence</span>
              <p className="text-sm text-slate-800 whitespace-pre-wrap">{result.explanation.text}</p>
            </div>
          )}
          {result.baseline_explanation && (
            <div>
              <span className="text-[10px] font-mono font-bold uppercase text-amber-800">generated by fixed rules ({result.baseline_generator}); no language model</span>
              <p className="text-sm text-slate-800 whitespace-pre-wrap">{result.baseline_explanation}</p>
            </div>
          )}
          {events && (
            <details className="text-xs">
              <summary className="cursor-pointer font-mono font-bold text-slate-600">Why: event log of this task</summary>
              <ol className="mt-2 space-y-1 font-mono">
                {events.map((e) => (
                  <li key={e.id} className="border-l-2 border-sky-400 pl-2">
                    <b>{e.step}. {e.node}</b>{e.model_id ? ` (${e.model_id})` : ''} <span className="text-slate-500">{e.time_utc}</span>
                    <div className="text-slate-700">{describeEvent(e)}</div>
                    {e.gate_result && <div className="text-slate-700">gate: {e.gate_result.ok ? 'approved' : 'refused'}. {e.gate_result.reason}</div>}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
