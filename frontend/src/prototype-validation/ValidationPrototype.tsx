// PROTOTYPE (throwaway, ticket t06): "Three variants of the validation dashboard, switchable via ?variant=A|B|C, mounted as a tab of the existing app."
// Read-only, in-memory, SYNTHETIC sample data. Delete this folder and its App.tsx hooks when a variant has been chosen.
import { useEffect, useState } from 'react';
import { PrototypeSwitcher } from './PrototypeSwitcher';
import { NAME as NAME_A, VariantA } from './VariantA';
import { NAME as NAME_B, VariantB } from './VariantB';
import { NAME as NAME_C, VariantC } from './VariantC';
import { NAME as NAME_D, VariantD } from './VariantD';

const VARIANTS = [{ key: 'A', name: NAME_A }, { key: 'B', name: NAME_B }, { key: 'C', name: NAME_C }, { key: 'D', name: NAME_D }];
const read = () => {
  const v = (new URLSearchParams(window.location.search).get('variant') ?? 'D').toUpperCase();
  return VARIANTS.some((x) => x.key === v) ? v : 'D';
};

export function ValidationPrototype() {
  const [variant, setVariant] = useState(read);
  useEffect(() => { const f = () => setVariant(read()); window.addEventListener('popstate', f); return () => window.removeEventListener('popstate', f); }, []);
  const change = (key: string) => {
    const u = new URL(window.location.href);
    u.searchParams.set('variant', key);
    window.history.replaceState({}, '', u);
    setVariant(key);
  };
  return (
    <div className="space-y-3 pb-16">
      <div className="rounded border border-amber-300 bg-amber-50 text-amber-800 px-3 py-1.5 text-[11px] font-mono">
        PROTOTYPE (ticket t06) · SYNTHETIC sample data · no backend, nothing is saved · flip variants with the bar below or ← →
      </div>
      {variant === 'A' && <VariantA />}
      {variant === 'B' && <VariantB />}
      {variant === 'C' && <VariantC />}
      {variant === 'D' && <VariantD />}
      <PrototypeSwitcher variants={VARIANTS} current={variant} onChange={change} />
    </div>
  );
}
