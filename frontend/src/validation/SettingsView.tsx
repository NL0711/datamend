// Settings, trimmed to what the platform needs (spec section 7). All of these live in the server's environment (.env): the UI shows their
// real state and does not edit them, so a browser user cannot point the server at an arbitrary narrator address. Editing here is NOT IMPLEMENTED.
import { useEffect, useState } from 'react';
import { getFeed, getNarrator } from './api';
import type { NarratorStatus } from './types';
import { Notice, Panel } from './ui';

type Feed = Awaited<ReturnType<typeof getFeed>>;

export function SettingsView() {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [narrator, setNarrator] = useState<NarratorStatus | null>(null);
  useEffect(() => { getFeed().then(setFeed).catch(() => setFeed(null)); getNarrator().then(setNarrator).catch(() => setNarrator(null)); }, []);

  const row = (k: string, v: string, env: string) => (
    <tr className="border-t border-[#E2E8F2]"><td className="p-2 font-bold">{k}</td><td className="font-mono">{v}</td><td className="font-mono text-slate-500">{env}</td></tr>);
  return (
    <div className="space-y-3 max-w-3xl">
      <Notice tone="info">These settings are read from the server's environment (<span className="font-mono">.env</span>) and shown here as they are. Changing them from this page is NOT IMPLEMENTED; edit <span className="font-mono">.env</span> and restart.</Notice>
      <Panel className="p-3">
        <table className="w-full text-xs">
          <thead><tr className="text-left text-[10px] uppercase font-mono text-slate-500"><th className="p-2">Setting</th><th>Current value</th><th>Environment variable</th></tr></thead>
          <tbody>
            {row('Live feed', feed === null ? 'unknown' : feed.enabled ? 'enabled' : 'not enabled', 'WEATHER_UNION_API_KEY, WEATHER_UNION_CITY')}
            {row('Feed interval', feed?.enabled ? `${Math.round(feed.status.poll_interval_seconds / 60)} min (raised automatically if the call budget would be exceeded)` : 'n/a', 'WEATHER_UNION_POLL_INTERVAL_SECONDS')}
            {row('Accumulation mode', feed?.enabled ? `${feed.status.accumulation_mode} (UNCONFIRMED: the provider does not document it)` : 'n/a', 'WEATHER_UNION_ACCUMULATION_MODE')}
            {row('AI narrator', narrator === null ? 'unknown' : narrator.connected ? `connected (${narrator.host})` : 'AI narrator not connected', 'NARRATOR_URL, NARRATOR_TOKEN')}
          </tbody>
        </table>
        {narrator && !narrator.connected && narrator.note && <p className="text-[11px] text-slate-600 mt-2">{narrator.note}</p>}
      </Panel>
    </div>
  );
}
