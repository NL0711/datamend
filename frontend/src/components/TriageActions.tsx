import { useState, type MouseEvent as ReactMouseEvent } from 'react';
import { CheckCircle2, X, ShieldCheck, ClipboardCheck } from 'lucide-react';
import { submitOperatorFeedback } from '../services/api';

export type TriageStatus = 'CONFIRMED_FAULT' | 'FALSE_POSITIVE' | 'IMPUTATION_APPROVED';

interface TriageActionsProps {
  eventId: number | string;
  stationId?: string;
  /** Hide the Approve Imputation button when the event carries no imputed value. */
  hasImputation?: boolean;
  compact?: boolean;
}

const OPERATOR_KEY = 'skyguard.operator_id';

const ACTIONS: Array<{ status: TriageStatus; label: string; title: string }> = [
  { status: 'CONFIRMED_FAULT', label: 'Confirm Fault', title: 'Mark this event as a verified sensor fault' },
  { status: 'FALSE_POSITIVE', label: 'Reject False Alarm', title: 'Mark this event as a false positive' },
  { status: 'IMPUTATION_APPROVED', label: 'Approve Imputation', title: 'Accept the system-estimated replacement value' },
];

/**
 * Shared operator triage controls (OpenSpec task4-parity-closeout, triage-ui).
 * Posts to POST /api/feedback via submitOperatorFeedback and surfaces the
 * outcome inline. Used by AlertCenterView and EventDetailView.
 */
export function TriageActions({ eventId, stationId, hasImputation = true, compact = false }: TriageActionsProps) {
  const [operatorId, setOperatorId] = useState<string>(() => {
    try {
      return window.localStorage.getItem(OPERATOR_KEY) || '';
    } catch {
      return '';
    }
  });
  const [pending, setPending] = useState<TriageStatus | null>(null);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);

  const submit = async (status: TriageStatus, e: ReactMouseEvent) => {
    e.stopPropagation();
    const id = operatorId.trim() || 'OPERATOR-UNSPECIFIED';
    setPending(status);
    setNotice(null);
    try {
      try {
        window.localStorage.setItem(OPERATOR_KEY, id);
      } catch {
        /* storage unavailable — operator id still sent with the request */
      }
      const record = await submitOperatorFeedback({
        event_id: String(eventId),
        operator_id: id,
        verification_status: status,
        imputation_accepted: status === 'IMPUTATION_APPROVED',
      });
      setNotice({
        ok: true,
        text: `Recorded ${record.verification_status} for event #${record.event_id} (record ${record.id}).`,
      });
    } catch (err) {
      setNotice({
        ok: false,
        text: `Triage submit failed: ${err instanceof Error ? err.message : String(err)}`,
      });
    } finally {
      setPending(null);
    }
  };

  const visible = ACTIONS.filter((a) => a.status !== 'IMPUTATION_APPROVED' || hasImputation);

  return (
    <div className="rounded-xl border border-[#263B5E] bg-[#101A2E] p-3 space-y-2" onClick={(e) => e.stopPropagation()}>
      <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-slate-400 font-mono">
        <ClipboardCheck className="w-3.5 h-3.5 text-sky-400" />
        Operator Triage
        {stationId && <span className="text-slate-500 normal-case">· {stationId} · event #{eventId}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={operatorId}
          onChange={(e) => setOperatorId(e.target.value)}
          onClick={(e) => e.stopPropagation()}
          placeholder="Operator ID"
          aria-label="Operator ID"
          className="px-2 py-1.5 text-xs font-mono bg-[#0B1424] border border-[#263B5E] rounded-lg text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-sky-500/60 w-36"
        />
        {visible.map((a) => (
          <button
            key={a.status}
            type="button"
            title={a.title}
            disabled={pending !== null}
            onClick={(e) => submit(a.status, e)}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-mono font-semibold transition-colors disabled:opacity-50 ${
              a.status === 'CONFIRMED_FAULT'
                ? 'bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border-rose-500/40'
                : a.status === 'FALSE_POSITIVE'
                  ? 'bg-slate-500/15 hover:bg-slate-500/25 text-slate-300 border-slate-500/40'
                  : 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border-emerald-500/40'
            } ${compact ? 'text-[11px] px-2 py-1' : ''}`}
          >
            {a.status === 'CONFIRMED_FAULT' ? (
              <CheckCircle2 className="w-3.5 h-3.5" />
            ) : a.status === 'FALSE_POSITIVE' ? (
              <X className="w-3.5 h-3.5" />
            ) : (
              <ShieldCheck className="w-3.5 h-3.5" />
            )}
            {pending === a.status ? 'Sending…' : a.label}
          </button>
        ))}
      </div>
      {notice && (
        <p className={`text-[11px] font-mono ${notice.ok ? 'text-emerald-300' : 'text-rose-300'}`}>{notice.text}</p>
      )}
    </div>
  );
}
