import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../services/api';

type Quantity = { value: number | null; unit: string; basis: string };
type Evidence = {
  row_ref: string; verdict: string; rule_score: number; severity: string;
  limitations: string[]; not_run: string[];
  checks_run: string[];
  checks: { check: string; reason: string; observed: Quantity;
    threshold: { description: string; why: string; parameters: Record<string, Quantity> } }[];
};
type Snapshot = { evidence_hash: string; evidence: Evidence };
type Explanation = { text: string; model_id: string; generated: true };
type ExplanationResult = Snapshot & { id: string; baseline: Explanation; narrator: Explanation | null; narrator_status: string };
type Station = { station_id: string; place: string };

async function request<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/rainfall${path}`, {
    ...init, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  });
  if (!response.ok) {
    if (response.status === 503) throw new Error('Live rainfall feed is off. Configure a Weather Union key and city on the backend.');
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status}).`);
  }
  return response.json();
}

export function RainfallReasoningView() {
  const [stations, setStations] = useState<Station[]>([]);
  const [station, setStation] = useState('');
  const [token, setToken] = useState('');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [result, setResult] = useState<ExplanationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);

  useEffect(() => {
    let live = true;
    request<{ stations: Station[] }>('/stations', '').then(data => {
      if (live) { setStations(data.stations); setStation(data.stations[0]?.station_id || ''); }
    }).catch(err => { if (live) setError(String(err.message)); });
    return () => { live = false; generation.current++; };
  }, []);

  function reset(nextStation: string) {
    generation.current++;
    setStation(nextStation); setSnapshot(null); setResult(null); setError(''); setBusy(false);
  }

  async function load() {
    const current = ++generation.current;
    setBusy(true); setError(''); setResult(null); setSnapshot(null);
    try {
      const data = await request<Snapshot>(`/stations/${encodeURIComponent(station)}/evidence`, token);
      if (current === generation.current) setSnapshot(data);
    } catch (err) { if (current === generation.current) setError((err as Error).message); }
    finally { if (current === generation.current) setBusy(false); }
  }

  async function explain(useNarrator: boolean) {
    if (!snapshot) return;
    const current = ++generation.current;
    setBusy(true); setError('');
    try {
      const data = await request<ExplanationResult>(`/stations/${encodeURIComponent(station)}/explanations`, token, {
        method: 'POST', body: JSON.stringify({ evidence_hash: snapshot.evidence_hash, use_narrator: useNarrator }),
      });
      if (current === generation.current) setResult(data);
    } catch (err) { if (current === generation.current) setError((err as Error).message); }
    finally { if (current === generation.current) setBusy(false); }
  }

  const evidence = result?.evidence || snapshot?.evidence;
  const button = 'rounded-lg bg-sky-700 px-4 py-2 text-sm font-medium text-white disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-700';
  return <section className="space-y-5 text-slate-900 [overflow-wrap:anywhere]" aria-busy={busy}>
    <div>
      <h1 className="text-xl font-semibold">Explainable Reasoning and Decision Making in AI</h1>
      <p className="mt-2 text-sm text-slate-600">Inspect the rainfall checks behind a decision. Generated explanations describe the evidence; they cannot change the verdict.</p>
    </div>
    <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-300 bg-white p-4">
      <label className="flex flex-col gap-1 text-sm">Rain gauge
        <select value={station} onChange={e => reset(e.target.value)} className="rounded border border-slate-300 p-2">
          {!stations.length && <option value="">No live gauges available</option>}
          {stations.map(s => <option key={s.station_id} value={s.station_id}>{s.place}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-1 text-sm">Evidence token, if configured
        <input type="password" autoComplete="off" value={token} onChange={e => { reset(station); setToken(e.target.value); }} className="rounded border border-slate-300 p-2" />
      </label>
      <button className={button} disabled={!station || busy} onClick={load}>Load latest evidence</button>
      <span role="status" className="text-sm text-slate-600">{busy ? 'Working… AI requests may take up to 20 seconds.' : ''}</span>
    </div>
    {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-800">{error}</p>}
    {evidence && <>
      <div className="rounded-xl border border-slate-300 bg-white p-4">
        <h2 className="font-semibold">Decision: {evidence.verdict}</h2>
        <p className="mt-1 text-sm">Rule score {evidence.rule_score} · {evidence.severity} severity · Uncalibrated, not a probability</p>
        <p className="mt-1 break-all text-xs text-slate-500">Reading: {evidence.row_ref}</p>
        <h3 className="mt-4 font-medium">Evidence behind the decision</h3>
        {!evidence.checks.length && <p className="mt-2 text-sm">No available check fired. This does not prove the reading is correct.</p>}
        {evidence.checks.map(check => <article key={check.check} className="mt-3 border-t border-slate-200 pt-3 text-sm">
          <h4 className="font-semibold">{check.check.replace(/_/g, ' ')}</h4>
          <p>{check.reason}</p>
          <p>Observed: {check.observed.value ?? 'unavailable'} {check.observed.unit} ({check.observed.basis})</p>
          <p>{check.threshold.description} {check.threshold.why}</p>
          <ul className="ml-5 list-disc">{Object.entries(check.threshold.parameters).map(([key, q]) => <li key={key}>{key.replace(/_/g, ' ')}: {q.value} {q.unit} ({q.basis})</li>)}</ul>
        </article>)}
        <h3 className="mt-4 font-medium">Limits and checks not run</h3>
        <p className="mt-2 text-sm">Checks run: {evidence.checks_run.map(name => name.replace(/_/g, ' ')).join(', ')}</p>
        <ul className="ml-5 mt-2 list-disc text-sm">{[...evidence.limitations, ...evidence.not_run].map(text => <li key={text}>{text.replace(/_/g, ' ')}</li>)}</ul>
        <details className="mt-4 text-sm"><summary className="cursor-pointer">Full evidence, including history and neighbours</summary>
          <pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all bg-slate-50 p-3 text-xs">{JSON.stringify(evidence, null, 2)}</pre>
        </details>
      </div>
      <div className="flex flex-wrap gap-3">
        <button className={button} disabled={busy} onClick={() => explain(false)}>Explain with template</button>
        <button className={button} disabled={busy} onClick={() => explain(true)}>Request AI explanation</button>
      </div>
    </>}
    {result && <div className="space-y-4 rounded-xl border border-slate-300 bg-white p-4" aria-live="polite">
      <h2 className="font-semibold">Template explanation · generated</h2>
      <p className="text-sm leading-relaxed">{result.baseline.text}</p>
      <p className="text-xs text-slate-600">Generator: {result.baseline.model_id}</p>
      <p role="status" className="text-sm">{result.narrator_status}</p>
      {result.narrator && <>
        <h2 className="font-semibold">AI-generated explanation · verify against evidence</h2>
        <p className="text-sm leading-relaxed">{result.narrator.text}</p>
        <p className="text-xs text-slate-600">Generator: {result.narrator.model_id}</p>
      </>}
      <p className="text-xs text-slate-600">Explanation saved separately from the decision. Demo storage may reset when the server restarts.</p>
    </div>}
  </section>;
}
