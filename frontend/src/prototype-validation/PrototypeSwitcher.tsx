// PROTOTYPE (throwaway, ticket t06): floating variant switcher. Hidden in production builds.
import { useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface Props { variants: { key: string; name: string }[]; current: string; onChange: (key: string) => void }

export function PrototypeSwitcher({ variants, current, onChange }: Props) {
  const idx = Math.max(0, variants.findIndex((v) => v.key === current));
  const go = (d: number) => onChange(variants[(idx + d + variants.length) % variants.length].key);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      if (e.key === 'ArrowLeft') go(-1);
      if (e.key === 'ArrowRight') go(1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  if ((import.meta as any).env?.PROD) return null;
  return (
    <div className="fixed bottom-12 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-full bg-slate-900 text-white px-4 py-2 shadow-2xl border border-slate-700 select-none">
      <button onClick={() => go(-1)} className="hover:text-sky-300" aria-label="Previous variant"><ChevronLeft className="w-5 h-5" /></button>
      <span className="text-xs font-mono font-bold tracking-wide">
        {variants[idx].key} <span className="font-normal text-slate-300">({variants[idx].name})</span>
      </span>
      <button onClick={() => go(1)} className="hover:text-sky-300" aria-label="Next variant"><ChevronRight className="w-5 h-5" /></button>
    </div>
  );
}
