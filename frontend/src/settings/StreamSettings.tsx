// Input-stream settings: the active source, the station set it applies to, cadence and (for the ESP32) the MQTT broker.
// Reads GET /api/settings (`stream` block) and writes PUT /api/settings with stream_* fields; the server validates and restarts the stream.
// The MQTT password is write-only: only whether one is set is shown.
import { useCallback, useEffect, useState } from 'react';
import { errorText, fetchStreamSettings, isAuthError, saveStreamSettings } from '../services/api';
import type { StreamSettingsAnswer, StreamSettingsView } from '../services/api';
import { AuthNotice } from '../components/AuthNotice';

const SOURCE_WORDS: Record<string, string> = {
  simulated: 'Simulator',
  open_meteo: 'Open-Meteo',
  weather_union: 'Weather Union',
  esp32: 'ESP32 (MQTT)',
};

const field = 'bg-[#FFFFFF] border border-[#D3DCE7] rounded px-2 py-1 text-xs font-mono';

export function StreamSettings() {
  const [answer, setAnswer] = useState<StreamSettingsAnswer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsAuth, setNeedsAuth] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const [source, setSource] = useState('');
  const [mode, setMode] = useState('');
  const [city, setCity] = useState('');
  const [interval, setIntervalText] = useState('');
  const [host, setHost] = useState('');
  const [port, setPort] = useState('');
  const [topic, setTopic] = useState('');
  const [user, setUser] = useState('');
  const [password, setPassword] = useState('');

  const adopt = useCallback((a: StreamSettingsAnswer) => {
    setAnswer(a);
    const s = a.stream;
    setSource(s.active_source);
    setMode(s.station_set.mode);
    setCity(s.station_set.city);
    setIntervalText(String(s.intervals_seconds[s.active_source] ?? ''));
    setHost(s.mqtt.host); setPort(String(s.mqtt.port)); setTopic(s.mqtt.topic_prefix); setUser(s.mqtt.username);
  }, []);

  useEffect(() => { fetchStreamSettings().then(adopt).catch((e) => setError(errorText(e))); }, [adopt]);

  const s: StreamSettingsView | undefined = answer?.stream;
  const editable = answer?.editing_enabled === true;

  const save = async () => {
    if (!s) return;
    setBusy(true); setError(null); setNeedsAuth(false); setNote(null);
    const update: Record<string, unknown> = {
      stream_active_source: source,
      stream_station_mode: mode,
    };
    if (mode === 'city') update.stream_city = city;
    const secs = Number(interval);
    if (interval.trim() !== '' && Number.isFinite(secs)) update[`stream_${source}_interval_seconds`] = secs;
    if (source === 'esp32') {
      update.stream_mqtt_host = host;
      if (port.trim() !== '') update.stream_mqtt_port = Number(port);
      update.stream_mqtt_topic_prefix = topic;
      update.stream_mqtt_username = user;
      if (password !== '') update.stream_mqtt_password = password;
    }
    try {
      const a = await saveStreamSettings(update);
      adopt(a);
      setPassword('');
      setNote(a.stream_error ? `Saved, but the stream did not start: ${a.stream_error}` : 'Saved. The stream was restarted with these settings.');
    } catch (e) {
      if (isAuthError(e)) setNeedsAuth(true); else setError(errorText(e));
    } finally { setBusy(false); }
  };

  if (!s) {
    return <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 text-xs text-slate-600 font-mono">{error ?? 'Loading input-stream settings...'}</div>;
  }
  const state = s.status as { state?: string; active_source?: string; station_count?: number } | undefined;
  return (
    <section className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl p-4 shadow-lg space-y-3" aria-label="Input stream settings">
      <div>
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 font-mono">Input stream: where live readings come from</h3>
        <p className="text-xs text-slate-700">
          The simulator, Open-Meteo, Weather Union or an ESP32 sensor. The Live page, the Overview tiles and the stream detections all use this one.
        </p>
        <p className="text-xs text-slate-600 mt-1">
          Active: {SOURCE_WORDS[s.active_source] ?? s.active_source}
          {state?.state ? ` (${state.state})` : ''}; stations: {s.station_set.mode === 'city' ? s.station_set.city : s.station_set.mode}. Changing a setting restarts the stream.
        </p>
      </div>
      {!editable && <p className="text-xs text-amber-800 font-mono">Editing is off on this server (no ADMIN_TOKEN set).</p>}
      <div className="flex flex-wrap items-end gap-3 text-xs font-mono text-slate-600">
        <label className="flex flex-col gap-1">Source
          <select value={source} onChange={(e) => { setSource(e.target.value); setIntervalText(String(s.intervals_seconds[e.target.value] ?? '')); }} className={field} disabled={!editable || busy}>
            {s.source_ids.map((id) => <option key={id} value={id}>{SOURCE_WORDS[id] ?? id}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">Stations
          <select value={mode} onChange={(e) => setMode(e.target.value)} className={field} disabled={!editable || busy}>
            {s.station_modes.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        {mode === 'city' && (
          <label className="flex flex-col gap-1">City
            <select value={city} onChange={(e) => setCity(e.target.value)} className={field} disabled={!editable || busy}>
              <option value="">choose a city</option>
              {s.cities.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1">Cadence (s)
          <input value={interval} onChange={(e) => setIntervalText(e.target.value)} inputMode="decimal" className={`${field} w-24`} disabled={!editable || busy} aria-label="cadence in seconds" />
          {s.interval_limits_seconds[source] && <span className="text-[10px] text-slate-500">{s.interval_limits_seconds[source][0]} to {s.interval_limits_seconds[source][1]}</span>}
        </label>
      </div>
      {source === 'esp32' && (
        <div className="flex flex-wrap items-end gap-3 text-xs font-mono text-slate-600">
          <label className="flex flex-col gap-1">MQTT host<input value={host} onChange={(e) => setHost(e.target.value)} className={field} disabled={!editable || busy} /></label>
          <label className="flex flex-col gap-1">Port<input value={port} onChange={(e) => setPort(e.target.value)} className={`${field} w-20`} disabled={!editable || busy} /></label>
          <label className="flex flex-col gap-1">Topic prefix<input value={topic} onChange={(e) => setTopic(e.target.value)} className={field} disabled={!editable || busy} /></label>
          <label className="flex flex-col gap-1">User<input value={user} onChange={(e) => setUser(e.target.value)} className={field} disabled={!editable || busy} /></label>
          <label className="flex flex-col gap-1">Password ({s.mqtt.password_set ? 'set' : 'not set'})
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="write-only" autoComplete="new-password" className={field} disabled={!editable || busy} />
          </label>
          <p className="basis-full text-[11px] text-slate-500">The ESP32 source is tested against a fake broker only; it is not verified on a real device.</p>
        </div>
      )}
      <div className="flex items-center gap-3">
        <button onClick={save} disabled={!editable || busy} className="px-3 py-2 bg-sky-500 hover:bg-sky-400 text-slate-950 font-mono font-bold text-xs rounded-lg shadow disabled:opacity-50">
          {busy ? 'Saving...' : 'Save and restart stream'}
        </button>
        {note && <span className="text-xs text-slate-700 font-mono">{note}</span>}
      </div>
      {needsAuth && <AuthNotice text="Saving stream settings needs an admin sign-in." />}
      {error && <p className="text-xs text-rose-700 font-mono">{error}</p>}
    </section>
  );
}
