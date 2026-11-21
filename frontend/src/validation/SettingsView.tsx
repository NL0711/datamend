// Settings: the weather data source (provider, one API key, city, interval) and MCP access for other people's agents. Saving uses the signed-in
// session. The API key is write-only: the server never sends it back. The AI chat's narrator is set on the server (NARRATOR_URL), not here.
import { useCallback, useEffect, useState } from 'react';
import { CloudSun } from 'lucide-react';
import { getSettings, saveSettings, storedToken, testFeed } from './api';
import { buildSettingsUpdate } from './lib';
import { McpAccess } from './McpAccess';
import type { FeedTestResult, SettingsState } from './types';
import { Notice, Panel, formatError } from './ui';

const field = 'text-xs border border-[#D3DCE7] rounded px-2 py-1.5 w-full disabled:bg-slate-100';
const Label = ({ children, hint }: { children: React.ReactNode; hint?: string }) => (
  <label className="text-[11px] font-bold text-slate-700 block space-y-1"><span>{children}</span>{hint && <span className="block font-normal text-slate-500">{hint}</span>}</label>
);

export function SettingsView() {
  const [state, setState] = useState<SettingsState | null>(null);
  const token = storedToken();
  const [form, setForm] = useState({ apiKey: '', provider: 'weather_union', city: '', intervalMinutes: '', mode: '' });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'info' | 'error' | 'warn'; text: string } | null>(null);
  const [test, setTest] = useState<FeedTestResult | null>(null);

  const seed = (s: SettingsState) => ({ apiKey: '', provider: s.weather_union.provider, city: s.weather_union.city, mode: s.weather_union.accumulation_mode,
                                        intervalMinutes: String(s.weather_union.poll_interval_seconds / 60) });
  const load = useCallback(() => getSettings().then((s) => { setState(s); setForm(seed(s)); }).catch((e) => setMessage({ tone: 'error', text: formatError(e) })), []);
  useEffect(() => { void load(); }, [load]);

  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async (clear: string[] = []) => {
    if (!state) return;
    const update = buildSettingsUpdate(form, state, clear);
    if (!update) { setMessage({ tone: 'info', text: 'Nothing changed.' }); return; }
    setBusy(true); setMessage(null); setTest(null);
    try {
      const next = await saveSettings(update, token);
      setState(next); setForm(seed(next));
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
  const chosen = state.providers.find((p) => p.id === form.provider) ?? state.providers[0];
  const canEdit = state.editing_enabled && token.length > 0;
  const can = canEdit && !busy;
  const changed = form.provider !== wu.provider || form.city !== wu.city;          // the test and the feed use the SAVED settings

  return (
    <div className="space-y-3 max-w-3xl">
      {!state.editing_enabled && <Notice tone="warn">Editing is off: set <span className="font-mono">ADMIN_PASSWORD</span> in the server's <span className="font-mono">.env</span> and restart.</Notice>}
      {message && <Notice tone={message.tone}>{message.text}</Notice>}

      <Panel className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><CloudSun className="w-4 h-4" />Weather data</h2>
          <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-bold ${state.feed_running ? 'border-emerald-300 bg-emerald-50 text-emerald-700' : 'border-slate-300 bg-slate-100 text-slate-600'}`}>
            {state.feed_running ? 'RUNNING' : wu.enabled ? 'CONFIGURED, NOT RUNNING' : 'OFF'}</span>
        </div>
        {state.feed && <p className="text-[11px] font-mono text-slate-600">{state.feed.stations} stations · poll every {Math.round(state.feed.poll_interval_seconds / 60)} min · {state.feed.calls_used_today} calls used, {state.feed.calls_remaining_today} left today · last poll {state.feed.last_poll_at ?? 'none yet'}{state.feed.last_error ? ` · ${state.feed.last_error}` : ''}</p>}
        <div className="grid md:grid-cols-2 gap-3">
          <div><Label hint={chosen.note}>Provider</Label>
            <select value={form.provider} onChange={set('provider')} disabled={!canEdit} className={field} aria-label="weather provider">
              {state.providers.map((p) => <option key={p.id} value={p.id}>{p.label}{p.kind === 'model' ? ' (model estimate)' : ''}</option>)}</select></div>
          <div><Label hint={wu.api_key_set ? `A key is set (from ${wu.api_key_source}). Type to replace it; it is never shown.` : chosen.key_required ? 'Required.' : 'Optional: free without a key; a commercial key uses its customer endpoint.'}>API key{chosen.key_required ? '' : ' (optional)'}</Label>
            <input type="password" value={form.apiKey} onChange={set('apiKey')} disabled={!canEdit} placeholder={wu.api_key_set ? '•••••••• (set)' : 'not set'} autoComplete="off" className={field} aria-label="weather API key" /></div>
          <div><Label hint="The 9 stations closest to the city centre are read.">City</Label>
            <select value={form.city} onChange={set('city')} disabled={!canEdit} className={field} aria-label="city">
              <option value="">not set</option>{state.cities.map((c) => <option key={c} value={c}>{c}</option>)}</select></div>
          <div><Label hint={`Between ${state.interval_limits_seconds[0] / 60} and ${state.interval_limits_seconds[1] / 60} minutes; raised automatically to stay inside the provider's daily call budget${chosen.id === 'open_meteo' ? ' and to at least 30' : ''}.`}>Poll interval (minutes)</Label>
            <input value={form.intervalMinutes} onChange={set('intervalMinutes')} inputMode="decimal" disabled={!canEdit} className={field} aria-label="poll interval in minutes" /></div>
          {chosen.mode_setting && (
            <div><Label hint="The provider does not document it, so it stays UNCONFIRMED until the raw log is checked when it rains.">Accumulation mode</Label>
              <select value={form.mode} onChange={set('mode')} disabled={!canEdit} className={field} aria-label="accumulation mode">
                {state.accumulation_modes.map((m) => <option key={m} value={m}>{m}</option>)}</select></div>)}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button disabled={!can} onClick={() => void save()} className="px-3 py-1.5 rounded bg-sky-600 text-white text-xs font-bold disabled:opacity-40">{busy ? 'Working…' : 'Save and apply'}</button>
          <button disabled={!can || !wu.enabled || changed} onClick={() => void runTest()} title={changed ? 'Save first: the test uses the saved settings' : 'makes one call to the provider'}
                  className="px-3 py-1.5 rounded border border-sky-300 text-sky-800 text-xs font-bold disabled:opacity-40">Test connection</button>
          {wu.api_key_source === 'runtime' && <button disabled={!can} onClick={() => void save(['weather_union_api_key'])} className="px-2 py-1 text-[11px] text-red-700 underline disabled:opacity-40">Remove the saved key</button>}
        </div>
        {test && <Notice tone={test.ok ? 'info' : 'error'}>{test.message}{test.place ? ` · ${test.place}` : ''}</Notice>}
      </Panel>

      <McpAccess canEdit={canEdit} />
    </div>
  );
}
