// Overview (the command centre): what the platform holds right now. Counts of rows in the stored runs, nothing more: no grade, no accuracy.
import { useEffect, useState } from 'react';
import { getFeed, getNarrator, getOverview, getReviewSummary } from './api';
import { VERDICT_COLOR, headlineLine, pct } from './lib';
import type { NarratorStatus, Overview, ReviewSummary, Verdict } from './types';
import { Notice, Panel, SyntheticBadge, formatError } from './ui';

type Feed = Awaited<ReturnType<typeof getFeed>>;
export type Tab = 'overview' | 'stations' | 'live' | 'runs' | 'run' | 'review' | 'insights' | 'settings';

const Tile = ({ label, value, sub }: { label: string; value: string | number; sub?: string }) => (
  <div className="rounded border border-[#D3DCE7] bg-[#F4F6FA] px-3 py-2"><div className="text-[10px] uppercase font-mono text-slate-500">{label}</div>
    <div className="text-lg font-bold font-mono">{value}</div>{sub && <div className="text-[10px] text-slate-500">{sub}</div>}</div>
);

export function OverviewView({ onOpenRun, go }: { onOpenRun: (id: number) => void; go: (t: Tab) => void }) {
  const [ov, setOv] = useState<Overview | null>(null);
  const [rs, setRs] = useState<ReviewSummary | null>(null);
  const [feed, setFeed] = useState<Feed | null>(null);
  const [nar, setNar] = useState<NarratorStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getOverview().then(setOv).catch((e) => setError(formatError(e)));
    getReviewSummary().then(setRs).catch(() => undefined);
    getFeed().then(setFeed).catch(() => undefined);
    getNarrator().then(setNar).catch(() => undefined);
  }, []);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!ov) return <p className="text-xs text-slate-500">Loading…</p>;
  const total = Object.values(ov.verdicts).reduce((a, b) => a + b, 0);
  const maxCheck = Math.max(1, ...Object.values(ov.checks_fired));

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Runs" value={ov.runs.total} sub={`${ov.runs.completed} completed · ${ov.runs.rejected_uploads} rejected · ${ov.runs.open_live} live`} />
        <Tile label="Rows validated" value={ov.rows.total} sub={`${ov.rows.uploaded_or_live} uploaded or live · ${ov.rows.synthetic} synthetic`} />
        <Tile label="Awaiting review" value={rs?.unreviewed_rows ?? '…'} sub={rs ? `${rs.reviewed_rows} reviewed of ${rs.flagged_rows} flagged` : undefined} />
        <Tile label="Storage" value={ov.storage} />
      </div>

      <div className="grid lg:grid-cols-2 gap-3">
        <Panel className="p-3 space-y-2">
          <h2 className="text-sm font-bold text-slate-900">Verdicts across all runs</h2>
          {total === 0 ? <p className="text-xs text-slate-500">No rows yet. <button className="text-sky-700 font-bold" onClick={() => go('runs')}>Add a run</button>.</p> : (
            <>
              <div className="flex h-4 rounded overflow-hidden border border-[#D3DCE7]" role="img" aria-label="verdict shares">
                {(['OK', 'UNCERTAIN', 'SUSPECT', 'NO_DATA'] as Verdict[]).map((v) => ov.verdicts[v] > 0 && (
                  <div key={v} style={{ width: `${(ov.verdicts[v] / total) * 100}%`, background: VERDICT_COLOR[v] }} title={`${v}: ${ov.verdicts[v]}`} />))}
              </div>
              <ul className="text-[11px] font-mono grid grid-cols-2 gap-x-4">
                {(['OK', 'SUSPECT', 'UNCERTAIN', 'NO_DATA'] as Verdict[]).map((v) => <li key={v}><span style={{ color: VERDICT_COLOR[v] }}>■</span> {v} {ov.verdicts[v]} ({pct(ov.verdicts[v] / total)})</li>)}
              </ul>
            </>)}
        </Panel>

        <Panel className="p-3 space-y-2">
          <h2 className="text-sm font-bold text-slate-900">Checks that fired</h2>
          {Object.keys(ov.checks_fired).length === 0 ? <p className="text-xs text-slate-500">No check has fired yet.</p> : (
            <ul className="space-y-1">{Object.entries(ov.checks_fired).map(([c, n]) => (
              <li key={c} className="flex items-center gap-2 text-[11px] font-mono"><span className="w-56 truncate">{c}</span>
                <span className="h-2 bg-sky-400 rounded" style={{ width: `${(n / maxCheck) * 100}%`, minWidth: 4 }} /><span>{n}</span></li>))}</ul>)}
        </Panel>
      </div>

      <div className="grid lg:grid-cols-3 gap-3">
        <Panel className="p-3 space-y-1">
          <h2 className="text-sm font-bold text-slate-900">Latest run</h2>
          {ov.latest_run ? (
            <>
              <button onClick={() => onOpenRun(ov.latest_run!.id)} className="text-xs font-bold text-sky-700 hover:underline">#{ov.latest_run.id} {ov.latest_run.label}</button>
              {ov.latest_run.synthetic && <> <SyntheticBadge /></>}
              <p className="text-[11px] text-slate-600">{headlineLine(ov.latest_run.headline)}</p>
            </>) : <p className="text-xs text-slate-500">None yet.</p>}
        </Panel>
        <Panel className="p-3 space-y-1">
          <h2 className="text-sm font-bold text-slate-900">Live gauge feed</h2>
          {feed?.enabled ? (
            <>
              <p className="text-[11px] font-mono text-emerald-700">RUNNING · {feed.stations.length} stations · {feed.status.calls_remaining_today} calls left today</p>
              {ov.live_run ? <button onClick={() => onOpenRun(ov.live_run!.id)} className="text-xs font-bold text-sky-700 hover:underline">Open today's live run #{ov.live_run.id}</button> : <p className="text-[11px] text-slate-500">Waiting for the first poll.</p>}
            </>) : <p className="text-[11px] text-slate-600">Off. <button className="text-sky-700 font-bold" onClick={() => go('settings')}>Connect it in Settings</button>.</p>}
        </Panel>
        <Panel className="p-3 space-y-1">
          <h2 className="text-sm font-bold text-slate-900">AI narrator</h2>
          <p className="text-[11px] text-slate-600">{nar?.connected ? `Connected (${nar.host}).` : 'Not connected (NARRATOR_URL).'}</p>
        </Panel>
      </div>

      {rs && rs.flagged_rows > 0 && (
        <Panel className="p-3 space-y-1">
          <div className="flex items-center gap-3"><h2 className="text-sm font-bold text-slate-900">Review loop</h2>
            <button onClick={() => go('review')} className="text-xs font-bold text-sky-700 hover:underline">Open the review queue</button></div>
          <p className="text-[11px] font-mono text-slate-600">confirmed {rs.by_decision.confirmed_fault} · false alarm {rs.by_decision.false_alarm} · genuine extreme {rs.by_decision.genuine_extreme} · follow-up {rs.by_decision.needs_followup}</p>
        </Panel>)}
    </div>
  );
}
