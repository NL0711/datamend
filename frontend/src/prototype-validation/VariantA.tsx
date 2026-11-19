// PROTOTYPE (throwaway, ticket t06). Variant A: REPORT-FIRST. A document-style run report; flagged rows expand inline into evidence.
import { useState } from 'react';
import { Download, FileText, Radio } from 'lucide-react';
import { FLAGGED, ROWS, RUN, STATIONS, headline, pct, stationName } from './sample';
import { EvidenceCard, Panel, SeverityPill, VerdictBadge } from './Shared';

export const NAME = 'Report first';

export function VariantA() {
  const [tab, setTab] = useState<'report' | 'live'>('report');
  const [open, setOpen] = useState<string | null>(FLAGGED[0]?.id ?? null);
  const h = headline();
  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div className="flex items-center gap-2 border-b border-[#D3DCE7]">
        {([['report', 'Run report', FileText], ['live', 'Live gauge feed', Radio]] as const).map(([k, label, Icon]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`flex items-center gap-1.5 px-3 py-2 text-xs font-bold border-b-2 -mb-px ${tab === k ? 'border-sky-600 text-sky-700' : 'border-transparent text-slate-500'}`}>
            <Icon className="w-3.5 h-3.5" />{label}
          </button>))}
        <div className="ml-auto text-[10px] font-mono text-slate-500 pb-1">Runs: <b>{RUN.id}</b> (current) · run-sample-0000 · run-sample--01 · {RUN.storage}</div>
      </div>

      {tab === 'report' ? (
        <>
          <Panel className="p-4">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div>
                <h2 className="text-base font-bold text-slate-900">Validation report · {RUN.id}</h2>
                <p className="text-[11px] font-mono text-slate-500 mt-1">
                  profile {RUN.profile} · source {RUN.source} · interval {RUN.interval} min · accumulation {RUN.mode} · {STATIONS.length} stations · {h.total} readings · {RUN.inputHash}
                </p>
              </div>
              <div className="flex gap-2">
                {['JSON', 'CSV'].map((f) => (
                  <button key={f} className="flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-bold border border-[#D3DCE7] rounded hover:bg-[#EDF1F7]"><Download className="w-3 h-3" />{f}</button>))}
                <button disabled className="px-2.5 py-1.5 text-[11px] border border-dashed border-slate-300 rounded text-slate-400" title="PDF is NOT IMPLEMENTED">PDF (not implemented)</button>
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
              {[['Completeness', pct(h.completeness), 'readings present / expected'], ['SUSPECT', pct(h.suspect), `${h.nSuspect} readings`],
                ['UNCERTAIN', pct(h.uncertain), `${h.nUncertain} readings`], ['NO_DATA', `${h.nNoData}`, 'missing slots']].map(([k, v, s]) => (
                <div key={k} className="rounded border border-[#D3DCE7] bg-[#F4F6FA] p-3">
                  <div className="text-[10px] uppercase font-mono text-slate-500">{k}</div>
                  <div className="text-2xl font-bold text-slate-900">{v}</div>
                  <div className="text-[10px] text-slate-500">{s}</div>
                </div>))}
            </div>
            <p className="text-[10px] text-slate-500 mt-2">No composite quality grade: measured numbers only. SAMPLE data, synthetic.</p>
          </Panel>

          <div className="grid md:grid-cols-3 gap-4">
            <Panel className="p-4 md:col-span-2">
              <h3 className="text-xs font-bold uppercase text-slate-600 mb-2">Checks that fired</h3>
              <table className="w-full text-xs">
                <thead className="text-[10px] uppercase text-slate-500 text-left"><tr><th>Check</th><th>Layer</th><th>Severity</th><th className="text-right">Readings</th></tr></thead>
                <tbody>{Object.entries(h.perCheck).map(([c, v]) => (
                  <tr key={c} className="border-t border-[#E2E8F2]"><td className="py-1.5 font-mono font-bold">{c}</td><td className="font-mono text-slate-500">{v.layer}</td>
                    <td><SeverityPill s={v.severity} /></td><td className="text-right font-mono">{v.rows}</td></tr>))}</tbody>
              </table>
            </Panel>
            <Panel className="p-4">
              <h3 className="text-xs font-bold uppercase text-slate-600 mb-2">Checks not run</h3>
              <ul className="space-y-2 text-xs">{RUN.notRun.map((n) => (
                <li key={n.check}><div className="font-bold text-slate-800">{n.check}</div><div className="text-slate-500">{n.why}</div></li>))}</ul>
            </Panel>
          </div>

          <Panel className="p-4">
            <h3 className="text-xs font-bold uppercase text-slate-600 mb-2">Flagged readings ({FLAGGED.length}) · click a row for evidence</h3>
            <table className="w-full text-xs">
              <thead className="text-[10px] uppercase text-slate-500 text-left"><tr><th>Station</th><th>Time</th><th>Verdict</th><th>Check</th><th className="text-right">Rule score</th></tr></thead>
              <tbody>{FLAGGED.map((r) => (
                <>
                  <tr key={r.id} onClick={() => setOpen(open === r.id ? null : r.id)} className="border-t border-[#E2E8F2] cursor-pointer hover:bg-[#F4F6FA]">
                    <td className="py-1.5">{stationName(r.station)}</td><td className="font-mono">{r.time}</td><td><VerdictBadge v={r.verdict} /></td>
                    <td className="font-mono">{r.hits.map((x) => x.check).join(', ')}</td><td className="text-right font-mono">{r.ruleScore.toFixed(2)}</td>
                  </tr>
                  {open === r.id && r.hits.map((hit) => (
                    <tr key={`${r.id}-${hit.check}`}><td colSpan={5} className="bg-[#F4F6FA] p-3 border-t border-[#E2E8F2]"><EvidenceCard row={r} hit={hit} /></td></tr>))}
                </>))}</tbody>
            </table>
          </Panel>
        </>
      ) : (
        <Panel className="p-4">
          <h2 className="text-base font-bold text-slate-900">Live gauge feed · Weather Union (SAMPLE view)</h2>
          <p className="text-[11px] font-mono text-slate-500 mt-1">9 of 900 calls used today · poll every 15 min · time basis: received · accumulation units unconfirmed</p>
          <table className="w-full text-xs mt-3">
            <thead className="text-[10px] uppercase text-slate-500 text-left"><tr><th>Station</th><th>Cell / region</th><th className="text-right">Intensity</th><th className="text-right">Accum.</th><th>Verdict</th></tr></thead>
            <tbody>{STATIONS.map((s) => {
              const last = ROWS.filter((r) => r.station === s.id).slice(-1)[0];
              return <tr key={s.id} className="border-t border-[#E2E8F2]"><td className="py-1.5">{s.name}</td><td className="font-mono text-slate-500">{s.cell} · {s.region}</td>
                <td className="text-right font-mono">{last.intensity}</td><td className="text-right font-mono">{last.accumulation}</td><td><VerdictBadge v={last.verdict} /></td></tr>;
            })}</tbody>
          </table>
          <p className="text-[11px] text-slate-500 mt-3">Open run today: live-2026-11-19 (closes at 03 UTC). Honest state when it is not raining: every gauge reads 0, verdict OK.</p>
        </Panel>
      )}
    </div>
  );
}
