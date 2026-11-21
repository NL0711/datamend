// A "?" in the header that opens a popover explaining the verdict words, the scores, "not run" and the review decisions.
import { useEffect, useRef, useState } from 'react';
import { HelpCircle } from 'lucide-react';
import { LEGEND, restoreGuide } from '../validation/guide';

export function Legend({ onShowGuide }: { onShowGuide: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', away);
    document.addEventListener('keydown', esc);
    return () => { document.removeEventListener('mousedown', away); document.removeEventListener('keydown', esc); };
  }, [open]);
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="dialog" aria-expanded={open} aria-label="What the words mean" title="What the words mean"
              className="w-8 h-8 flex items-center justify-center rounded-lg border border-sky-500/40 bg-[#EDF1F7] hover:bg-[#E2E8F2] text-sky-700 shadow-sm">
        <HelpCircle className="w-4 h-4" />
      </button>
      {open && (
        <div role="dialog" aria-label="What the words mean" className="absolute right-0 top-full mt-1 w-[26rem] max-w-[92vw] max-h-[75vh] overflow-y-auto rounded-lg border border-[#D3DCE7] bg-white shadow-lg z-50 p-3 space-y-3 font-sans text-left">
          {LEGEND.map((s) => (
            <div key={s.heading}>
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-slate-900 font-mono">{s.heading}</h4>
              <dl className="mt-1 space-y-1.5">
                {s.entries.map((e) => (
                  <div key={e.term}>
                    <dt className="text-xs font-bold text-slate-900">{e.term}</dt>
                    <dd className="text-[11px] text-slate-600">{e.meaning}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
          <button onClick={() => { restoreGuide(window.localStorage); onShowGuide(); setOpen(false); }} className="text-xs font-bold text-sky-700 underline">
            Show the Start here guide again
          </button>
        </div>
      )}
    </div>
  );
}
