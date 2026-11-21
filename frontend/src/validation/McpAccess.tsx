// MCP access: let other people's agents (Claude and so on) read the platform's results. A token per person, shown once when made and kept as a
// hash; the agent connects to the endpoint below and gets read-only tools (runs, flagged rows, evidence). Making and revoking need the admin sign-in.
import { useCallback, useEffect, useState } from 'react';
import { Copy, KeyRound, Plug } from 'lucide-react';
import { createMcpToken, getMcp, revokeMcpToken } from './api';
import { mcpEndpoint, mcpSnippets, shortTime } from './mcp';
import type { McpState, NewMcpToken } from './types';
import { Notice, Panel, formatError } from './ui';

const field = 'text-xs border border-[#D3DCE7] rounded px-2 py-1.5 w-full';

function CopyBlock({ title, text }: { title: string; text: string }) {
  const [done, setDone] = useState(false);
  const copy = () => { void navigator.clipboard?.writeText(text).then(() => { setDone(true); window.setTimeout(() => setDone(false), 1500); }); };
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2"><span className="text-[11px] font-bold text-slate-700">{title}</span>
        <button onClick={copy} className="ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded border border-[#D3DCE7] text-[10px] font-bold text-slate-600 hover:bg-[#F4F6FA]"><Copy className="w-3 h-3" />{done ? 'Copied' : 'Copy'}</button></div>
      <pre className="text-[10px] font-mono bg-slate-900 text-slate-100 rounded p-2 overflow-x-auto whitespace-pre-wrap break-all">{text}</pre>
    </div>);
}

export function McpAccess({ canEdit }: { canEdit: boolean }) {
  const [state, setState] = useState<McpState | null>(null);
  const [label, setLabel] = useState('');
  const [fresh, setFresh] = useState<NewMcpToken | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const url = mcpEndpoint(window.location.origin);

  const load = useCallback(() => getMcp().then(setState).catch((e) => setError(formatError(e))), []);
  useEffect(() => { void load(); }, [load]);

  const create = async () => {
    if (!label.trim()) return;
    setBusy(true); setError(null);
    try { setFresh(await createMcpToken(label.trim())); setLabel(''); await load(); } catch (e) { setError(formatError(e)); } finally { setBusy(false); }
  };
  const revoke = async (id: number) => {
    setBusy(true); setError(null);
    try { await revokeMcpToken(id); if (fresh?.id === id) setFresh(null); await load(); } catch (e) { setError(formatError(e)); } finally { setBusy(false); }
  };

  const snippets = mcpSnippets(url, fresh?.token ?? '');
  return (
    <Panel className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Plug className="w-4 h-4" />Agent access (MCP)</h2>
        {state && <span className={`px-2 py-0.5 rounded border text-[10px] font-mono font-bold ${state.active > 0 ? 'border-violet-300 bg-violet-50 text-violet-700' : 'border-slate-300 bg-slate-100 text-slate-600'}`}>
          {state.active > 0 ? `${state.active} TOKEN${state.active > 1 ? 'S' : ''} ACTIVE` : 'NO TOKEN'}</span>}
      </div>
      <p className="text-[11px] text-slate-600">Give someone's agent (Claude, an IDE, any MCP client) a token and it can analyse this platform's runs, flagged rows and evidence. Read-only: it cannot change anything.</p>
      {error && <Notice tone="error">{error}</Notice>}
      {state && !state.available && <Notice tone="warn">The MCP service files are not installed on this server.</Notice>}

      <label className="block text-[11px] font-bold text-slate-700 space-y-1"><span>Endpoint</span>
        <input readOnly value={url} onFocus={(e) => e.currentTarget.select()} className={`${field} font-mono bg-slate-50`} aria-label="MCP endpoint" /></label>

      {state && state.available && (
        <>
          <form className="flex gap-2 items-end" onSubmit={(e) => { e.preventDefault(); void create(); }}>
            <label className="flex-1 text-[11px] font-bold text-slate-700 space-y-1"><span>New token for</span>
              <input value={label} onChange={(e) => setLabel(e.target.value)} maxLength={80} disabled={!canEdit} placeholder="a name, e.g. Alice's Claude" className={field} aria-label="token name" /></label>
            <button type="submit" disabled={!canEdit || busy || !label.trim()} className="px-3 py-1.5 rounded bg-violet-600 text-white text-xs font-bold disabled:opacity-40 inline-flex items-center gap-1"><KeyRound className="w-3.5 h-3.5" />Create token</button>
          </form>

          {fresh && (
            <div className="rounded border border-violet-300 bg-violet-50 p-3 space-y-2">
              <p className="text-[11px] font-bold text-violet-900">Token for {fresh.label}: copy it now, it is not shown again.</p>
              <CopyBlock title="Token" text={fresh.token} />
              <CopyBlock title="Claude Code" text={snippets.claudeCode} />
              <CopyBlock title="Remote MCP client (JSON)" text={snippets.json} />
              <CopyBlock title="Claude Desktop (through mcp-remote)" text={snippets.desktop} />
            </div>)}

          {state.tokens.length > 0 && (
            <table className="w-full text-[11px]">
              <thead className="text-left text-[10px] uppercase font-mono text-slate-500"><tr><th className="p-1">Name</th><th>Token</th><th>Created</th><th>Last used</th><th /></tr></thead>
              <tbody>{state.tokens.map((t) => (
                <tr key={t.id} className="border-t border-[#E2E8F2]">
                  <td className="p-1 font-bold">{t.label}</td><td className="font-mono">{t.prefix}…</td><td className="font-mono">{shortTime(t.created_at)}</td>
                  <td className="font-mono">{shortTime(t.last_used_at)}</td>
                  <td className="text-right">{t.revoked_at ? <span className="text-slate-500">revoked</span> : (
                    <button disabled={!canEdit || busy} onClick={() => void revoke(t.id)} className="text-red-700 underline disabled:opacity-40">Revoke</button>)}</td>
                </tr>))}</tbody>
            </table>)}

          <details className="text-[11px] text-slate-600">
            <summary className="cursor-pointer select-none font-bold text-slate-500">{state.tools.length} read-only tools · up to {state.rate_per_minute} calls a minute</summary>
            <ul className="mt-1 space-y-0.5">{state.tools.map((t) => <li key={t.name}><span className="font-mono font-bold">{t.name}</span> {t.description}</li>)}</ul>
          </details>
        </>)}
    </Panel>
  );
}
