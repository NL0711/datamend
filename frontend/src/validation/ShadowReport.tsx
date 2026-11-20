// The shadow comparison of a challenger beside the champion on one pipeline run. Measured only on the rows a reviewer labelled in that run:
// one person's judgements, not ground truth. It changes nothing by itself; the promotion gate may read it.
import type { ShadowRun, ShadowSide } from './types';

const pct = (v: number | null) => (v === null ? 'no reviewed faults' : `${(v * 100).toFixed(0)}%`);

function Side({ name, s }: { name: string; s: ShadowSide | null }) {
  if (!s) return <tr><td className="pr-3 font-bold">{name}</td><td colSpan={4} className="text-slate-500">none: there is no champion to compare with</td></tr>;
  return (
    <tr>
      <td className="pr-3 font-bold">{name} (model {s.model_id})</td>
      <td className="pr-3">{s.flagged}</td>
      <td className="pr-3">{s.faults_flagged} of {s.faults} ({pct(s.recall_on_reviewed)})</td>
      <td className="pr-3">{s.false_alarms_flagged} of {s.false_alarms_labelled}</td>
      <td>{s.genuine_extremes_flagged} of {s.genuine_extremes}</td>
    </tr>
  );
}

export function ShadowReport({ s }: { s: ShadowRun }) {
  const r = s.report;
  return (
    <div className="rounded border border-dashed border-slate-400 bg-slate-50 px-2 py-1.5 text-[11px] space-y-1" data-testid="shadow-report">
      <div className="font-mono font-bold uppercase text-[10px] text-slate-700">Shadow run on run {s.run_id} · {r.rows} rows · {r.reviewed_rows_used} reviewed rows used</div>
      <table className="font-mono text-[11px]">
        <thead><tr className="text-left text-slate-500"><th className="pr-3 font-normal">model</th><th className="pr-3 font-normal">rows flagged</th>
          <th className="pr-3 font-normal">reviewed faults caught</th><th className="pr-3 font-normal">reviewed false alarms flagged</th><th className="font-normal">genuine extremes flagged</th></tr></thead>
        <tbody><Side name="challenger" s={r.challenger} /><Side name="champion" s={r.champion} /></tbody>
      </table>
      <div>{r.disagreements} row(s) flagged by one model only{r.only_challenger_flags.length ? `; challenger only: ${r.only_challenger_flags.join(', ')}` : ''}{r.only_champion_flags.length ? `; champion only: ${r.only_champion_flags.join(', ')}` : ''}.</div>
      <div className="text-slate-500">{r.note}</div>
    </div>
  );
}
