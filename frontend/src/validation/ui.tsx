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
  <div className={`rain-panel ${className}`}>{children}</div>
);

/** Anything that is not a measurement (synthetic data, AI-written text) is drawn dashed, so it is never mistaken for one. */
export const NOT_MEASURED = 'border border-dashed border-slate-400 bg-slate-50 text-slate-700';

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
  <span className={`px-1.5 py-0.5 rounded ${NOT_MEASURED} text-[10px] font-mono font-bold`}>SYNTHETIC</span>
);

/** Text written by the rule-based baseline or the AI narrator: dashed and always called GENERATED. */
export const GeneratedBadge = ({ text = 'GENERATED' }: { text?: string }) => (
  <span className={`px-1.5 py-0.5 rounded ${NOT_MEASURED} text-[10px] font-mono font-bold`}>{text}</span>
);

/** A value the cleaning proposed (interpolated): never a measurement. */
export const ImputedBadge = () => (
  <span className={`px-1.5 py-0.5 rounded ${NOT_MEASURED} text-[10px] font-mono font-bold`} title="Proposed by interpolation; not a measurement. basis: derived">IMPUTED</span>
);

export const btn = 'px-3 py-1.5 rounded bg-teal-700 text-white text-xs font-bold disabled:opacity-40';
export const btnQuiet = 'px-3 py-1.5 rounded border border-[#D3DCE7] bg-white text-xs font-bold disabled:opacity-40';
export const field = 'text-xs border border-[#D3DCE7] rounded px-2 py-1.5 bg-white';
export const num = (n: number) => n.toLocaleString('en-IN');

/** The end of every step: one clear button to the next. */
export function NextButton({ label, onClick, disabled }: { label: string; onClick: () => void; disabled?: boolean }) {
  return (
    <div className="flex justify-end pt-2">
      <button onClick={onClick} disabled={disabled} className="px-5 py-2.5 rounded bg-teal-700 text-white text-sm font-bold disabled:opacity-40 inline-flex items-center gap-2">
        Next: {label}<span aria-hidden="true">→</span></button>
    </div>);
}

export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <Panel className="p-4 space-y-3">
      <div><h2 className="text-sm font-bold text-slate-900">{title}</h2>{hint && <p className="text-xs text-slate-600 mt-0.5">{hint}</p>}</div>
      {children}
    </Panel>);
}

export function formatError(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
