import { useEffect, useState } from 'react';
import { getFeed, listRuns } from './api';
import type { RunSummary } from './types';
import { Notice, Panel, SeverityPill, VerdictBadge, formatError } from './ui';

type Feed = Awaited<ReturnType<typeof getFeed>>;

/** `stationId`: the shell's selected station; the table then shows that station only (a link shows every station of the feed again).
 *  `onSelectStation`: clicking a row makes that station the selected one. */
export function LiveFeedView({ onOpenRun, stationId, onSelectStation }: { onOpenRun: (id: number) => void; stationId?: string | null; onSelectStation?: (id: string) => void }) {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [everyStation, setEveryStation] = useState(false);
  const [live, setLive] = useState<RunSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => {
      getFeed().then(setFeed).catch((e) => setError(formatError(e)));
      listRuns().then((r) => setLive(r.runs.find((x) => x.source === 'live' && x.status === 'open') ?? null)).catch(() => undefined);
    };
    load();
    const t = window.setInterval(load, 60_000);
    return () => window.clearInterval(t);
  }, []);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!feed) return <p className="text-xs text-slate-500">Loading…</p>;
  if (!feed.enabled) return <Notice tone="warn">The live gauge feed is not enabled. Add a Weather Union key and a city in Settings. Nothing is simulated in its place.</Notice>;

  const { status } = feed;
  const filtering = !!stationId && !everyStation;
  const stations = filtering ? feed.stations.filter((s) => s.station_id === stationId) : feed.stations;
  return (
    <div className="space-y-3">
      <Panel className="p-3 space-y-1">
        <div className="flex items-center gap-4 flex-wrap text-[11px] font-mono">
          <span className="font-bold text-emerald-700">LIVE · {status.source}</span>
          <span>{status.stations} stations</span>
          <span>poll every {Math.round(status.poll_interval_seconds / 60)} min</span>
          <span>{status.calls_used_today} calls used · {status.calls_remaining_today} left today</span>
          <span>last poll {status.last_poll_at ?? 'none yet'}</span>
          <span>accumulation mode: {status.accumulation_mode}{status.kind === 'model' ? ' (stated by the provider)' : ' (UNCONFIRMED)'}</span>
          {live && <button onClick={() => onOpenRun(live.id)} className="ml-auto text-sky-700 font-bold hover:underline">Open today's live run #{live.id}</button>}
        </div>
        {status.last_error && <Notice tone="error">{status.last_error}</Notice>}
        <ul className="text-[11px] text-slate-600 list-disc pl-5">{status.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
      </Panel>
      <Panel className="p-3 overflow-x-auto">
        {stationId && (
          <p className="text-[11px] text-slate-600 mb-2">
            {filtering
              ? <>Showing station <b className="font-mono">{stationId}</b> only. <button className="font-bold text-sky-700" onClick={() => setEveryStation(true)}>Show all {feed.stations.length} stations of the feed</button>.</>
              : <>Showing every station of the feed. <button className="font-bold text-sky-700" onClick={() => setEveryStation(false)}>Show only {stationId}</button>.</>}
          </p>)}
        {filtering && stations.length === 0 && (
          <Notice tone="info">Station {stationId} is not in the live feed (the feed polls {feed.stations.length} stations of the city set in Settings). Nothing is shown in its place.</Notice>)}
        <table className="w-full text-[11px]">
          <thead><tr className="text-left text-[10px] uppercase font-mono text-slate-500">
            <th className="p-1">Station</th><th>Last reading (time, UTC)</th><th>Intensity</th><th>Counter</th><th>Today (mm, rain day ending {stations[0]?.today.rain_day})</th><th>Verdict</th><th>Why</th></tr></thead>
          <tbody>{stations.map((s) => (
            <tr key={s.station_id} onClick={() => onSelectStation?.(s.station_id)} className={`border-t border-[#E2E8F2] align-top ${onSelectStation ? 'cursor-pointer' : ''} ${s.station_id === stationId ? 'bg-[#ECFEFF]' : ''}`}>
              <td className="p-1 font-bold">{s.place}<div className="font-mono text-[10px] text-slate-400">{s.station_id}</div></td>
              <td className="font-mono">{s.last_reading?.received_at.slice(11, 19) ?? 'none yet'} {s.last_reading && s.last_reading.status !== 'OK' ? `(${s.last_reading.status})` : ''}</td>
              <td className="font-mono">{s.last_reading?.rain_intensity ?? 'null'}</td>
              <td className="font-mono">{s.last_reading?.rain_accumulation ?? 'null'}</td>
              <td className="font-mono">{s.today.total_mm ?? 'n/a'}{s.today.complete ? '' : ' (incomplete)'} · units unconfirmed</td>
              <td>{s.quality ? <span className="flex items-center gap-1"><VerdictBadge v={s.quality.assessment} /><SeverityPill s={s.quality.severity} /></span> : 'n/a'}</td>
              <td className="font-mono text-slate-600">{s.quality?.reasons.map((r) => r.check).join(', ') || '—'}</td>
            </tr>))}</tbody>
        </table>
      </Panel>
    </div>
  );
}
