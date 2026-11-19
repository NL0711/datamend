// Anomaly Lab (the old injector, rebuilt for rainfall): generate a SYNTHETIC upload with faults injected at known places, validate it through
// the real pipeline, and see whether each injected fault was caught. A demonstration that each check fires, not an accuracy measurement.
import { useEffect, useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { generateLab, getLabOptions } from './api';
import type { LabOptions, LabResult, Profile } from './types';
import { Notice, Panel, SyntheticBadge, formatError } from './ui';

export function LabView({ onOpenRun }: { onOpenRun: (id: number) => void }) {
  const [opts, setOpts] = useState<LabOptions | null>(null);
  const [profile, setProfile] = useState<Profile>('reading');
  const [stations, setStations] = useState(6);
  const [length, setLength] = useState(144);
  const [faults, setFaults] = useState<string[]>([]);
  const [seed, setSeed] = useState(1);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<LabResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { getLabOptions().then((o) => { setOpts(o); setFaults(o.faults.reading); }).catch((e) => setError(formatError(e))); }, []);
  const choose = (p: Profile) => {
    setProfile(p);
    if (opts) { setFaults(opts.faults[p]); setLength(p === 'reading' ? 144 : 60); }
  };
  const toggle = (f: string) => setFaults((cur) => (cur.includes(f) ? cur.filter((x) => x !== f) : [...cur, f]));

  const run = async () => {
    setBusy(true); setError(null); setResult(null);
    try { setResult(await generateLab({ profile, n_stations: stations, length, faults, seed })); } catch (e) { setError(formatError(e)); } finally { setBusy(false); }
  };

  if (!opts) return error ? <Notice tone="error">{error}</Notice> : <p className="text-xs text-slate-500">Loading…</p>;
  const [lo, hi] = opts.length[profile];
  const field = 'text-xs border border-[#D3DCE7] rounded px-2 py-1.5 w-full';
  return (
    <div className="space-y-3 max-w-4xl">
      <Panel className="p-4 space-y-3">
        <div className="flex items-center gap-2"><FlaskConical className="w-4 h-4 text-teal-700" /><h2 className="text-sm font-bold text-slate-900">Anomaly Lab</h2><SyntheticBadge /></div>
        <p className="text-[11px] text-slate-600">Builds an invented rainfall file (stations about 1 km apart, a shared shower) and injects the faults you choose, one per station. The file is validated by the same code as any upload and stored as a run labelled SYNTHETIC. The same seed always gives the same file.</p>
        <div className="grid md:grid-cols-4 gap-3">
          <label className="text-[11px] font-bold text-slate-700">Profile<select value={profile} onChange={(e) => choose(e.target.value as Profile)} className={field} aria-label="profile"><option value="reading">reading (15-minute)</option><option value="daily">daily</option></select></label>
          <label className="text-[11px] font-bold text-slate-700">Stations ({opts.stations[0]} to {opts.stations[1]})<input type="number" min={opts.stations[0]} max={opts.stations[1]} value={stations} onChange={(e) => setStations(Number(e.target.value))} className={field} aria-label="stations" /></label>
          <label className="text-[11px] font-bold text-slate-700">{profile === 'reading' ? 'Readings' : 'Days'} per station ({lo} to {hi})<input type="number" min={lo} max={hi} value={length} onChange={(e) => setLength(Number(e.target.value))} className={field} aria-label="length" /></label>
          <label className="text-[11px] font-bold text-slate-700">Seed<span className="flex gap-1"><input type="number" min={0} value={seed} onChange={(e) => setSeed(Number(e.target.value))} className={field} aria-label="seed" />
            <button type="button" onClick={() => setSeed(Math.floor(Math.random() * 1_000_000))} className="px-2 border border-[#D3DCE7] rounded text-[11px]">New</button></span></label>
        </div>
        <fieldset className="space-y-1"><legend className="text-[11px] font-bold text-slate-700">Faults to inject</legend>
          <div className="flex gap-3 flex-wrap">{opts.faults[profile].map((f) => (
            <label key={f} className="text-[11px] flex items-center gap-1"><input type="checkbox" checked={faults.includes(f)} onChange={() => toggle(f)} />
              <span className="font-mono">{f}</span><span className="text-slate-500">→ {opts.expected_check[f]}</span></label>))}</div></fieldset>
        {error && <Notice tone="error">{error}</Notice>}
        <button disabled={busy || faults.length === 0} onClick={() => void run()} className="px-3 py-1.5 rounded bg-teal-700 text-white text-xs font-bold disabled:opacity-40">{busy ? 'Generating…' : 'Generate and validate'}</button>
      </Panel>

      {result && (
        <Panel className="p-4 space-y-2">
          <div className="flex items-center gap-3 flex-wrap">
            <h3 className="text-sm font-bold text-slate-900">Result</h3><SyntheticBadge />
            <span className="text-xs font-mono">{result.summary.caught} of {result.summary.injected} injected faults flagged by the expected check · {result.summary.other_flagged_rows} other flagged rows · {result.summary.rows} rows</span>
            <button onClick={() => onOpenRun(result.run.id)} className="ml-auto text-xs font-bold text-sky-700 hover:underline">Open run #{result.run.id}</button>
          </div>
          <table className="w-full text-[11px] font-mono border border-[#D3DCE7]">
            <thead className="bg-[#EDF1F7] text-left"><tr><th className="px-2">fault</th><th className="px-2">station</th><th className="px-2">time</th><th className="px-2">expected check</th><th className="px-2">flagged</th></tr></thead>
            <tbody>{result.injected.map((i) => (
              <tr key={`${i.fault}-${i.row_ref}`} className="border-t border-[#E2E8F2]"><td className="px-2">{i.fault}</td><td className="px-2">{i.station_id}</td>
                <td className="px-2">{i.time.slice(0, 16).replace('T', ' ')}</td><td className="px-2">{i.expected_check}</td>
                <td className={`px-2 font-bold ${i.caught ? 'text-emerald-700' : 'text-red-700'}`}>{i.caught ? 'yes' : 'NO'}</td></tr>))}</tbody>
          </table>
          <p className="text-[10px] text-slate-500">{result.note}</p>
        </Panel>)}
    </div>
  );
}
