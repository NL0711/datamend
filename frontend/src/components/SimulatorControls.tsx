// The simulator's running state from GET /api/simulation/status, as the server answers it. There is no start or stop control here: the backend
// starts the simulator itself, and the source is chosen in Settings.
import { useCallback, useEffect, useState } from 'react';
import { errorText, getSimulationStatus } from '../services/api';
import type { SimulationStatus } from '../types';

/** "running · every 5 s · step 12 · 0 fault(s) queued · 580 stations". */
export function simulatorLine(s: SimulationStatus): string {
  return `${s.running ? 'running' : 'stopped'} · every ${s.interval_seconds} s · step ${s.step_count} · ${s.pending_injections_count} fault(s) queued · ${s.active_stations.length} stations`;
}

export function SimulatorControls() {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => { getSimulationStatus().then((s) => { setStatus(s); setError(null); }).catch((e) => setError(errorText(e))); }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="space-y-1 text-xs font-mono" data-testid="simulator-status">
      {status && <span className="text-slate-600">Simulator: {simulatorLine(status)}</span>}
      {error && <p className="text-[11px] text-rose-700">{error}</p>}
    </div>
  );
}
