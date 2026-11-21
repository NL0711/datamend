// Start and stop the simulator through POST /api/simulation/start and /stop, and show GET /api/simulation/status as the server answers it.
// Starting makes the simulator the one running source (the server stops any other). The interval is optional: empty means the server's own.
import { useCallback, useEffect, useState } from 'react';
import { errorText, getSimulationStatus, isAuthError, startSimulation, stopSimulation } from '../services/api';
import type { SimulationStatus } from '../types';
import { AuthNotice } from './AuthNotice';

export function SimulatorControls({ onChanged }: { onChanged?: () => void }) {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [interval, setIntervalText] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsAuth, setNeedsAuth] = useState(false);

  const load = useCallback(() => { getSimulationStatus().then(setStatus).catch((e) => setError(errorText(e))); }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  const act = async (start: boolean) => {
    setBusy(true); setError(null); setNeedsAuth(false);
    try {
      if (start) {
        const secs = interval.trim() === '' ? undefined : Number(interval);
        if (secs !== undefined && !Number.isFinite(secs)) { setError('The interval must be a number of seconds.'); setBusy(false); return; }
        setStatus(await startSimulation(secs === undefined ? {} : { interval_seconds: secs }));
      } else {
        setStatus(await stopSimulation());
      }
      onChanged?.();
    } catch (e) {
      if (isAuthError(e)) setNeedsAuth(true); else setError(errorText(e));
    } finally { setBusy(false); }
  };

  const running = status?.running === true;
  return (
    <div className="space-y-2 text-xs font-mono">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-1.5 text-slate-600">
          Interval (s)
          <input value={interval} onChange={(e) => setIntervalText(e.target.value)} disabled={running || busy} inputMode="decimal" placeholder={status ? String(status.interval_seconds) : 'server default'}
                 aria-label="simulator interval in seconds" className="w-20 bg-[#FFFFFF] border border-[#D3DCE7] rounded px-2 py-1 disabled:bg-slate-100" />
        </label>
        {running ? (
          <button onClick={() => act(false)} disabled={busy} className="px-3.5 py-1.5 bg-rose-500/15 hover:bg-rose-500/25 border border-rose-500/40 text-rose-800 rounded-lg font-bold disabled:opacity-50">Stop simulator</button>
        ) : (
          <button onClick={() => act(true)} disabled={busy} className="px-3.5 py-1.5 bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/40 text-emerald-800 rounded-lg font-bold disabled:opacity-50">Start simulator</button>
        )}
        {status && (
          <span className="text-slate-600">
            {running ? 'running' : 'stopped'} · every {status.interval_seconds} s · step {status.step_count} · {status.pending_injections_count} fault(s) queued · {status.active_stations.length} stations
          </span>
        )}
      </div>
      {needsAuth && <AuthNotice text="Starting or stopping the simulator needs an admin sign-in." />}
      {error && <p className="text-[11px] text-rose-700">{error}</p>}
    </div>
  );
}
