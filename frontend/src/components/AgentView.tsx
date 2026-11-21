// Agent page: ask about the SELECTED station, read the generated answer, accept or dismiss what the agent proposed, and open the "why" view
// (the append-only event log of the task). PROTOTYPE of a sandboxed, bounded decision-support agent: it proposes, a human accepts.
import { useCallback, useEffect, useState } from 'react';
import { askAgent, decideAgentProposal, fetchAgentEvents, fetchAgentProposals, fetchAgentStatus, isAuthError } from '../services/api';
import type { AgentEventRow, AgentProposal, AgentStatus, AgentTaskResult } from '../services/api';
import { useStation } from '../validation/StationContext';
import { AuthNotice } from './AuthNotice';
import { openStationPicker } from './PageIntro';
import { agentErrorText, describeEvent, describeProposal, isTransient, statusWords } from './agentText';

const card = 'bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg space-y-2';
const h3 = 'text-xs font-bold uppercase tracking-wider text-slate-900 font-mono';

export function AgentView() {
  const { stationId } = useStation();
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [text, setText] = useState('Why is the latest flag at this station there, and what should a reviewer do?');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needSignIn, setNeedSignIn] = useState(false);
  const [result, setResult] = useState<AgentTaskResult | null>(null);
  const [proposals, setProposals] = useState<AgentProposal[]>([]);
  const [events, setEvents] = useState<AgentEventRow[] | null>(null);

  const fail = (e: unknown) => { setNeedSignIn(isAuthError(e)); setError(agentErrorText(e)); };

  useEffect(() => { fetchAgentStatus().then(setStatus).catch(fail); }, []);
  useEffect(() => {
    setResult(null); setEvents(null); setError(null); setNeedSignIn(false);
    if (stationId) fetchAgentProposals(stationId).then((r) => setProposals(r.proposals)).catch(() => setProposals([]));
    else setProposals([]);
  }, [stationId]);

  const ask = useCallback(async () => {
    if (!stationId) return;
    setBusy(true); setError(null); setNeedSignIn(false); setEvents(null);
    try {
      let r: AgentTaskResult;
      try {
        r = await askAgent(stationId, text);
      } catch (first) {
        if (!isTransient(first)) throw first;
        await new Promise((res) => setTimeout(res, 6000));       // a sleeping free-plan server: give it a moment, then ask once more
        r = await askAgent(stationId, text);
      }
      setResult(r);
      setProposals((await fetchAgentProposals(stationId)).proposals);
      setEvents((await fetchAgentEvents(r.task_id)).events);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [stationId, text]);

  const commentLive = useCallback(async () => {
    if (!stationId) return;
    setBusy(true); setError(null); setNeedSignIn(false); setEvents(null);
    try {
      const r = await askAgent(stationId, 'Comment on the current live feed of this station.', 'live');
      setResult(r);
      setEvents((await fetchAgentEvents(r.task_id)).events);
    } catch (e) { fail(e); } finally { setBusy(false); }
  }, [stationId]);

  const decide = async (id: number, d: 'accept' | 'dismiss') => {
    setError(null);
    try {
      await decideAgentProposal(id, d);
      if (stationId) setProposals((await fetchAgentProposals(stationId)).proposals);
    } catch (e) { fail(e); }
  };

  return (
    <div className="space-y-4" data-testid="agent-view">
      <div className={card}>
        <h3 className={h3}>Agent (PROTOTYPE)</h3>
        <p className="text-xs text-slate-600">
          A prototype of a sandboxed, bounded decision-support agent. It reads this station's results through read-only tools, writes an explanation (generated text) and may
          propose a reviewer label, a note, an alert acknowledgement, a re-run or a question. It never changes a verdict, score, evidence or raw data, and a human accepts every proposal.
        </p>
        {status && (status.connected
          ? <p className="text-xs font-mono text-slate-700">Agent connected.</p>
          : <p role="status" className="text-xs font-mono text-amber-800">Agent not connected. The rule-based explanation still works.</p>)}
      </div>

      <div className={card}>
        <h3 className={h3}>Live feed of {stationId ?? 'a station'}</h3>
        <p className="text-xs text-slate-600">
          The agent reads the latest stored readings and detections of this station from the live stream (read-only tools), and says what they show.
          It works from a snapshot, so the comment is about that moment, not a running commentary.
        </p>
        <button onClick={commentLive} disabled={!stationId || busy} className="px-3 py-2 bg-sky-500 hover:bg-sky-400 disabled:opacity-50 text-slate-950 font-mono font-bold text-xs rounded-lg shadow">
          {busy ? 'Working...' : 'Comment on the live feed'}
        </button>
      </div>

      <div className={card}>
        <h3 className={h3}>Ask about {stationId ?? 'a station'}</h3>
        {!stationId && (
          <div className="flex items-center gap-3">
            <p className="text-xs text-slate-600">The agent answers about one station. Pick a station first.</p>
            <button onClick={openStationPicker} className="px-3 py-1.5 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg shadow">Pick a station</button>
          </div>
        )}
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
          {result.outcome && <p className="text-xs font-mono text-slate-700">Outcome (real): {result.outcome.status}. {result.outcome.detail}</p>}
          {result.rejected_alternatives.length > 0 && (
            <ul className="text-xs text-slate-600 list-disc pl-4">
              {result.rejected_alternatives.map((r, i) => <li key={i}>Not chosen: {r.action ?? '(malformed)'}: {r.reason}</li>)}
            </ul>
          )}
        </div>
      )}

      <div className={card}>
        <h3 className={h3}>Proposed actions (a human accepts)</h3>
        {proposals.length === 0 && <p className="text-xs text-slate-600">{stationId ? 'Nothing proposed for this station yet. Ask the agent a question above and any proposal appears here.' : 'Pick a station to see what the agent proposed for it.'}</p>}
        <ul className="space-y-1">
          {proposals.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono border border-[#D3DCE7] rounded-lg p-2">
              <span>#{p.id} {describeProposal(p)} <em className="text-slate-500">[{p.status}, generated]</em></span>
              {p.status === 'proposed' && (
                <span className="flex gap-2">
                  <button onClick={() => decide(p.id, 'accept')} className="px-2 py-1 rounded bg-sky-500 text-slate-950 font-bold">Accept</button>
                  <button onClick={() => decide(p.id, 'dismiss')} className="px-2 py-1 rounded border border-[#D3DCE7]">Dismiss</button>
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      {events && (
        <div className={card}>
          <h3 className={h3}>Why: event log of this task (append-only)</h3>
          <ol className="space-y-1 text-xs font-mono">
            {events.map((e) => (
              <li key={e.id} className="border-l-2 border-sky-400 pl-2">
                <b>{e.step}. {e.node}</b>{e.model_id ? ` (${e.model_id})` : ''} <span className="text-slate-500">{e.time_utc}</span>
                <div className="text-slate-700">{describeEvent(e)}</div>
                {e.gate_result && <div className="text-slate-700">gate: {e.gate_result.ok ? 'approved' : 'refused'}. {e.gate_result.reason}</div>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
