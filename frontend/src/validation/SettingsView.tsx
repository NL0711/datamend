// Settings: the Weather Union feed (key, city, interval, accumulation mode) and the AI narrator (URL, token). Saving needs the admin sign-in
// (Login.tsx); the session is kept for this browser tab only. Secrets are write-only: the server never sends them back.
import { useCallback, useEffect, useState } from 'react';
import { getSettings, saveSettings, testFeed } from './api';
import { LoginForm, signOut, useAdmin } from './Login';
import { buildSettingsUpdate } from './lib';
import type { FeedTestResult, SettingsState } from './types';
import { Notice, Panel, formatError } from './ui';

const field = 'text-xs border border-[#D3DCE7] rounded px-2 py-1.5 w-full disabled:bg-slate-100';
const Label = ({ children, hint }: { children: React.ReactNode; hint?: string }) => (
  <label className="text-[11px] font-bold text-slate-700 block space-y-1"><span>{children}</span>{hint && <span className="block font-normal text-slate-500">{hint}</span>}</label>
);

export function SettingsView() {
  const [state, setState] = useState<SettingsState | null>(null);
  const { token, email, signedIn } = useAdmin();
  const [form, setForm] = useState({ apiKey: '', city: '', intervalMinutes: '', mode: '', narratorUrl: '', narratorToken: '' });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'info' | 'error' | 'warn'; text: string } | null>(null);
  const [test, setTest] = useState<FeedTestResult | null>(null);

  const load = useCallback(() => getSettings().then((s) => {
    setState(s);
    setForm((f) => ({ ...f, city: s.weather_union.city, mode: s.weather_union.accumulation_mode, narratorUrl: s.narrator.url,
                      intervalMinutes: String(s.weather_union.poll_interval_seconds / 60) }));
  }).catch((e) => setMessage({ tone: 'error', text: formatError(e) })), []);
  useEffect(() => { void load(); }, [load]);

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async (clear: string[] = []) => {
    if (!state) return;
    const update = buildSettingsUpdate(form, state, clear);
    if (!update) { setMessage({ tone: 'info', text: 'Nothing changed.' }); return; }
    setBusy(true); setMessage(null); setTest(null);
    try {
      const next = await saveSettings(update, token);
      setState(next);
      setForm((f) => ({ ...f, apiKey: '', narratorToken: '', city: next.weather_union.city, mode: next.weather_union.accumulation_mode,
                        narratorUrl: next.narrator.url, intervalMinutes: String(next.weather_union.poll_interval_seconds / 60) }));
      setMessage(next.feed_error ? { tone: 'warn', text: `Saved, but ${next.feed_error}.` }
        : { tone: 'info', text: `Saved: ${(next.saved ?? []).join(', ').replace(/_/g, ' ')}.${next.feed_running ? ' The live feed was restarted with the new settings.' : ''}` });
    } catch (e) { setMessage({ tone: 'error', text: formatError(e) }); } finally { setBusy(false); }
  };

  const runTest = async () => {
    setBusy(true); setTest(null); setMessage(null);
    try { setTest(await testFeed(token)); } catch (e) { setMessage({ tone: 'error', text: formatError(e) }); } finally { setBusy(false); }
  };

  if (!state) return message ? <Notice tone={message.tone}>{message.text}</Notice> : <p className="text-xs text-slate-500">Loading…</p>;
  const wu = state.weather_union;
  const can = state.editing_enabled && signedIn && !busy;

  return (
    <div className="space-y-3 max-w-3xl">
      {!state.editing_enabled && (
        <Notice tone="warn">Admin sign-in is switched off on this server. Set <span className="font-mono">ADMIN_PASSWORD</span> (and <span className="font-mono">ADMIN_EMAIL</span>) in
          the server's environment and restart. Until then you can read the settings here and change them in the environment.</Notice>)}
      {message && <Notice tone={message.tone}>{message.text}</Notice>}

      {state.editing_enabled && (
        <Panel className="p-4 space-y-2">
          {signedIn ? (
            <div className="flex items-center gap-3 flex-wrap text-sm">
              <span>Signed in as <b>{email}</b>. You can change the settings below.</span>
              <button onClick={() => void signOut()} className="px-3 py-1.5 rounded border border-slate-300 bg-white text-xs font-semibold">Sign out</button>
            </div>)
            : <LoginForm why="Sign in as the admin to change settings. Reading never needs it." />}
        </Panel>)}

      <Panel className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-bold text-slate-900">Weather Union live feed</h2>
          <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-bold ${state.feed_running ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : 'border-slate-300 bg-slate-100 text-slate-600'}`}>
            {state.feed_running ? 'RUNNING' : wu.enabled ? 'CONFIGURED, NOT RUNNING' : 'OFF'}</span>
        </div>
        {state.feed && <p className="text-[11px] font-mono text-slate-600">{state.feed.stations} stations · poll every {Math.round(state.feed.poll_interval_seconds / 60)} min · {state.feed.calls_used_today} calls used, {state.feed.calls_remaining_today} left today · last poll {state.feed.last_poll_at ?? 'none yet'}{state.feed.last_error ? ` · ${state.feed.last_error}` : ''}</p>}
        <div className="grid md:grid-cols-2 gap-3">
          <div><Label hint={wu.api_key_set ? `A key is set (from ${wu.api_key_source}). Type to replace it; the key is never shown.` : 'Free key from weatherunion.com/dashboard.'}>API key</Label>
            <input type="password" value={form.apiKey} onChange={set('apiKey')} disabled={!state.editing_enabled} placeholder={wu.api_key_set ? '•••••••• (set)' : 'not set'} autoComplete="off" className={field} aria-label="Weather Union API key" /></div>
          <div><Label hint="The 9 stations closest to the city centre are polled.">City</Label>
            <select value={form.city} onChange={set('city')} disabled={!state.editing_enabled} className={field} aria-label="city">
              <option value="">not set</option>{state.cities.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div><Label hint={`Between ${state.interval_limits_seconds[0] / 60} and ${state.interval_limits_seconds[1] / 60} minutes; raised automatically if the daily call budget would be exceeded.`}>Poll interval (minutes)</Label>
            <input value={form.intervalMinutes} onChange={set('intervalMinutes')} inputMode="decimal" disabled={!state.editing_enabled} className={field} aria-label="poll interval in minutes" /></div>
          <div><Label hint="The provider does not document it, so it stays UNCONFIRMED until the raw log is checked when it rains.">Accumulation mode</Label>
            <select value={form.mode} onChange={set('mode')} disabled={!state.editing_enabled} className={field} aria-label="accumulation mode">
              {state.accumulation_modes.map((m) => <option key={m} value={m}>{m}</option>)}</select></div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button disabled={!can} onClick={() => void save()} className="px-3 py-1.5 rounded bg-teal-700 text-white text-xs font-bold disabled:opacity-40">{busy ? 'Working…' : 'Save and apply'}</button>
          <button disabled={!can || !wu.api_key_set || !wu.city} onClick={() => void runTest()} title="makes one call to Weather Union" className="px-3 py-1.5 rounded border border-sky-300 text-sky-800 text-xs font-bold disabled:opacity-40">Test connection</button>
          {wu.api_key_source === 'runtime' && <button disabled={!can} onClick={() => void save(['weather_union_api_key'])} className="px-2 py-1 text-[11px] text-red-700 underline disabled:opacity-40">Remove the saved key</button>}
        </div>
        {test && <Notice tone={test.ok ? 'info' : 'error'}>{test.message}{test.place ? ` · ${test.place}` : ''}</Notice>}
      </Panel>

      <Panel className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-bold text-slate-900">AI narrator</h2>
          <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-bold ${state.narrator.connected ? 'border-teal-300 bg-teal-50 text-teal-800' : 'border-slate-300 bg-slate-100 text-slate-600'}`}>
            {state.narrator.connected ? 'URL SET' : 'NOT CONNECTED'}</span>
          {state.gemini && (
            <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-bold ${state.gemini.active ? 'border-teal-300 bg-teal-50 text-teal-800' : 'border-slate-300 bg-slate-100 text-slate-600'}`}>
              {state.gemini.active ? `GEMINI ACTIVE · ${state.gemini.model}` : state.gemini.key_set ? 'GEMINI KEY SET (narrator URL takes precedence)' : 'GEMINI KEY NOT SET'}</span>)}
        </div>
        <p className="text-[11px] text-slate-600">Interim LLM layer: with <span className="font-mono">GEMINI_API_KEY</span> set in the server's .env (never in this page) the chat, "Explain (AI)" and "Propose with AI" use Gemini; a narrator URL below takes precedence. Only the evidence of a row and your question are sent.</p>
        <p className="text-[11px] text-slate-600">The AI team's narrator is NOT IMPLEMENTED here yet; the chat and "Explain (AI)" use whatever service you point this at. The platform sends it the evidence of a row and a question, nothing else. A narrator on localhost or a private network is refused unless the server has <span className="font-mono">NARRATOR_ALLOW_PRIVATE=true</span>.</p>
        <div className="grid md:grid-cols-2 gap-3">
          <div><Label>Narrator URL</Label>
            <input value={form.narratorUrl} onChange={set('narratorUrl')} disabled={!state.editing_enabled} placeholder="https://…" className={field} aria-label="narrator URL" /></div>
          <div><Label hint={state.narrator.token_set ? 'A token is set. Type to replace it; never shown.' : 'Optional bearer token.'}>Token</Label>
            <input type="password" value={form.narratorToken} onChange={set('narratorToken')} disabled={!state.editing_enabled} placeholder={state.narrator.token_set ? '•••••••• (set)' : 'not set'} autoComplete="off" className={field} aria-label="narrator token" /></div>
        </div>
        <div className="flex items-center gap-2">
          <button disabled={!can} onClick={() => void save()} className="px-3 py-1.5 rounded bg-teal-700 text-white text-xs font-bold disabled:opacity-40">Save narrator</button>
          {state.narrator.url_source === 'runtime' && <button disabled={!can} onClick={() => void save(['narrator_url', 'narrator_token'])} className="px-2 py-1 text-[11px] text-red-700 underline disabled:opacity-40">Disconnect</button>}
        </div>
      </Panel>
    </div>
  );
}
