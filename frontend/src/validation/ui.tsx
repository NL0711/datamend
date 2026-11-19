import type { ReactNode } from 'react';
import type { Basis, Severity, Verdict } from './types';

const VERDICT_STYLE: Record<Verdict, string> = {
  OK: 'bg-emerald-50 text-emerald-700 border-emerald-300',
  SUSPECT: 'bg-red-50 text-red-700 border-red-300',
  UNCERTAIN: 'bg-amber-50 text-amber-700 border-amber-300',
  NO_DATA: 'bg-slate-100 text-slate-600 border-slate-300',
};
const SEVERITY_STYLE = { high: 'bg-red-600 text-white', medium: 'bg-amber-500 text-white', low: 'bg-slate-400 text-white' } as const;
const BASIS_STYLE: Record<Basis, string> = { measured: 'text-emerald-700', assumed: 'text-amber-700', derived: 'text-sky-700' };

export const Panel = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <div className={`bg-white border border-[#D3DCE7] rounded-lg ${className}`}>{children}</div>
);

export const VerdictBadge = ({ v }: { v: Verdict }) => (
  <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-bold ${VERDICT_STYLE[v]}`}>{v}</span>
);

export const SeverityPill = ({ s }: { s: Severity }) =>
  s ? <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${SEVERITY_STYLE[s]}`}>{s}</span> : null;

/** A number's basis, always shown next to it: measured, assumed or derived. */
export const BasisTag = ({ basis }: { basis: Basis }) => (
  <span className={`text-[10px] font-mono ${BASIS_STYLE[basis]}`}>basis: {basis}</span>
);

export const Notice = ({ tone, children }: { tone: 'info' | 'warn' | 'error'; children: ReactNode }) => {
  const style = { info: 'border-sky-200 bg-sky-50 text-sky-900', warn: 'border-amber-300 bg-amber-50 text-amber-900', error: 'border-red-300 bg-red-50 text-red-800' }[tone];
  return <div className={`rounded border px-3 py-2 text-xs ${style}`}>{children}</div>;
};

export const SyntheticBadge = () => (
  <span className="px-1.5 py-0.5 rounded border border-violet-300 bg-violet-50 text-violet-700 text-[10px] font-mono font-bold">SYNTHETIC</span>
);

export function formatError(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
