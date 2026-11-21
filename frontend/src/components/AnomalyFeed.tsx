// The detections of the stream (GET /api/anomalies): readings on which a check really fired, as a compact card list. With `evidence` each
// card opens to the evidence of every check that fired (the check, its reason, the numbers it used) and the checks that could not run.
// The score is the uncalibrated rule score. Nothing is shown that the API did not return; an empty list says so.
import { useEffect, useState } from 'react';
import { fetchAnomalies, isNotBuilt, errorText } from '../services/api';
import { evidenceFacts, fmtScore, notRunLines } from '../services/stream';
import { AnomalyEvent } from '../types';
import { StatusBadge } from '../design-system/components/StatusBadge';
import { EmptyState } from '../design-system/components/EmptyState';
import { severityVariant, verdictVariant } from './severity';

export function AnomalyFeed({ stationId, limit = 4, onOpen, evidence = false }: { stationId?: string | null; limit?: number; onOpen?: () => void; evidence?: boolean }) {
  const [items, setItems] = useState<AnomalyEvent[] | null>(null);
  const [total, setTotal] = useState<number>(0);
  const [notBuilt, setNotBuilt] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setItems(null); setError(null); setNotBuilt(false);
    fetchAnomalies({ station_id: stationId || undefined, limit })
      .then((r) => { if (current) { setItems(r.items); setTotal(r.total); } })
      .catch((e) => { if (!current) return; if (isNotBuilt(e)) setNotBuilt(true); else setError(errorText(e)); });
    return () => { current = false; };
  }, [stationId, limit]);

  if (notBuilt) {
    return (
      <EmptyState className="!p-6" title="Detections not available" description="GET /api/anomalies did not answer (404, 501, 502 or 503)." />
    );
  }
  if (error) return <div className="p-3 text-xs text-rose-700 font-mono border border-rose-300 bg-rose-50 rounded-lg">{error}</div>;
  if (items === null) return <p className="text-xs text-slate-500 font-mono">Loading…</p>;
  if (items.length === 0) {
    return (
      <div className="p-6 text-center text-xs text-slate-500 font-sans border border-dashed border-[#D3DCE7] rounded-lg">
        No detections recorded{stationId ? ` for ${stationId}` : ''}. A reading appears here only when a check fired on it.
      </div>
    );
  }
  return (
    <div className="space-y-2.5">
      {items.slice(0, limit).map((ev) => {
        const hits = ev.evidence ?? [];
        const notRun = notRunLines(ev.not_run as { check: string; reason: string }[] | undefined);
        return (
          <div
            key={ev.id}
            onClick={onOpen}
            className={`p-3 bg-[#F4F6FA] border border-[#D3DCE7]/70 rounded-lg transition-all space-y-1.5 font-mono text-xs ${onOpen ? 'hover:bg-[#EDF1F7] cursor-pointer' : ''}`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {ev.verdict ? <StatusBadge label={ev.verdict} variant={verdictVariant(ev.verdict)} size="sm" /> : <StatusBadge label={ev.severity} variant={severityVariant(ev.severity)} size="sm" />}
                <span className="font-bold text-slate-900">{ev.station_id}</span>
                {ev.variable && <span className="text-[10px] text-slate-500">{ev.variable}</span>}
              </div>
              <span className="text-[10px] text-slate-500">
                {new Date(ev.timestamp).toISOString().slice(0, 19).replace('T', ' ')} UTC
              </span>
            </div>
            <div className="text-slate-700 font-sans font-semibold text-[11px] truncate">{ev.classification.replace(/_/g, ' ')}</div>
            <div className="flex items-center justify-between text-[10px] text-slate-500">
              <span>Rule score (uncalibrated): {fmtScore(ev.anomaly_score)} · severity {ev.severity}</span>
              {ev.is_fault && <span className="text-rose-600 font-bold">fault-kind check fired</span>}
            </div>
            {ev.reason && <div className="text-[11px] text-slate-600 font-sans">{ev.reason}</div>}
            {evidence && typeof ev.provider === 'object' && ev.provider?.variables && (
              <div className="text-[10px] text-slate-600 border-t border-[#D3DCE7] pt-1.5" onClick={(e) => e.stopPropagation()}>
                <div className="font-bold uppercase tracking-wider">Model score (reconstruction error, not validated)</div>
                {Object.entries(ev.provider.variables).map(([name, v]) => (
                  <div key={name}>
                    {name}: {v.status === 'scored'
                      ? `error ${v.error != null ? v.error.toFixed(3) : 'n/a'}${v.threshold != null ? `, threshold ${v.threshold.toFixed(3)}${v.flagged ? ' (flagged)' : ''}` : ', no threshold yet'}`
                      : `${v.status}${v.reason ? `: ${v.reason}` : ''}`}
                  </div>
                ))}
              </div>
            )}
            {evidence && (hits.length > 0 || notRun.length > 0) && (
              <details className="text-[11px]" onClick={(e) => e.stopPropagation()}>
                <summary className="cursor-pointer font-bold text-slate-700">Evidence ({hits.length} check{hits.length === 1 ? '' : 's'} fired{notRun.length ? `, ${notRun.length} not run` : ''})</summary>
                <ul className="mt-1.5 space-y-1.5">
                  {hits.map((h, i) => (
                    <li key={`${h.check}-${i}`} className="p-2 bg-white border border-[#D3DCE7] rounded">
                      <div className="font-bold text-slate-800">{h.check}{h.variable ? ` · ${h.variable}` : ''}{h.kind ? ` · ${h.kind}` : ''}</div>
                      <div className="text-slate-600 font-sans">{h.reason}</div>
                      <div className="text-[10px] text-slate-500 break-words">{evidenceFacts(h.evidence).join(' · ')}</div>
                    </li>
                  ))}
                </ul>
                {notRun.length > 0 && (
                  <div className="mt-1.5 text-[10px] text-slate-500">
                    <div className="font-bold uppercase tracking-wider">Not run</div>
                    {notRun.map((l) => <div key={l}>{l}</div>)}
                  </div>
                )}
              </details>
            )}
          </div>
        );
      })}
      {total > items.length && <p className="text-[10px] text-slate-500 font-mono">Showing {items.length} of {total} detections.</p>}
    </div>
  );
}
