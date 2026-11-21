// The temperature, pressure and humidity anomaly list of the ORIGINAL contract (GET /api/anomalies), as a compact card list.
// The endpoint is NOT BUILT yet (slice S4): while it answers 404 or 503 the list says so; it never shows invented events.
import { useEffect, useState } from 'react';
import { fetchAnomalies, isNotBuilt } from '../services/api';
import { AnomalyEvent } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { EmptyState } from '../design-system/components/EmptyState';
import { severityVariant } from './severity';

export function AnomalyFeed({ stationId, limit = 4, onOpen }: { stationId?: string | null; limit?: number; onOpen?: () => void }) {
  const [items, setItems] = useState<AnomalyEvent[] | null>(null);
  const [notBuilt, setNotBuilt] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setItems(null); setError(null); setNotBuilt(false);
    fetchAnomalies({ station_id: stationId || undefined, limit })
      .then((r) => { if (current) setItems(r.items); })
      .catch((e) => { if (!current) return; if (isNotBuilt(e)) setNotBuilt(true); else setError(e instanceof Error ? e.message : String(e)); });
    return () => { current = false; };
  }, [stationId, limit]);

  if (notBuilt) {
    return (
      <EmptyState
        className="!p-6"
        title="No anomaly stream connected"
        description="Temperature, pressure and humidity anomalies are not built yet. Planned in slice S4 (the T/P/RH checks)."
      />
    );
  }
  if (error) return <div className="p-3 text-xs text-rose-700 font-mono border border-rose-300 bg-rose-50 rounded-lg">{error}</div>;
  if (items === null) return <p className="text-xs text-slate-500 font-mono">Loading…</p>;
  if (items.length === 0) {
    return (
      <div className="p-6 text-center text-xs text-slate-500 font-sans border border-dashed border-[#D3DCE7] rounded-lg">
        No anomalies recorded{stationId ? ` for ${stationId}` : ''}.
      </div>
    );
  }
  return (
    <div className="space-y-2.5">
      {items.slice(0, limit).map((ev) => (
        <div
          key={ev.id}
          onClick={onOpen}
          className="p-3 bg-[#F4F6FA] hover:bg-[#EDF1F7] border border-[#D3DCE7]/70 rounded-lg cursor-pointer transition-all space-y-1.5 font-mono text-xs"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <StatusBadge label={ev.severity} variant={severityVariant(ev.severity)} size="sm" />
              <span className="font-bold text-slate-900">{ev.station_id}</span>
            </div>
            <span className="text-[10px] text-slate-500">
              {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
          <div className="text-slate-700 font-sans font-semibold text-[11px] truncate">{ev.classification.replace(/_/g, ' ')}</div>
          <div className="flex items-center justify-between text-[10px] text-slate-500">
            <span>Rule score: {(ev.anomaly_score * 100).toFixed(0)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}
