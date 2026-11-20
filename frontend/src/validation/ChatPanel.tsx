// AI chat about a run, grounded in the selected row's evidence. With no narrator configured it says so and sends nothing: it never
// answers from canned text. Replies are stored on the server as generated text and rendered here as plain text with an AI-generated badge.
import { useEffect, useRef, useState } from 'react';
import { Send } from 'lucide-react';
import { getChat, sendChat } from './api';
import { asPlainText } from './lib';
import type { ExplanationItem, NarratorStatus } from './types';
import { Notice, Panel, formatError } from './ui';

export function ChatPanel({ runId, rowId, narrator }: { runId: number; rowId: number | null; narrator: NarratorStatus | null }) {
  const [messages, setMessages] = useState<ExplanationItem[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const connected = !!narrator?.connected;

  useEffect(() => {
    setMessages([]); setError(null);
    getChat(runId).then((r) => setMessages(r.messages)).catch((e) => setError(formatError(e)));
  }, [runId]);
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'nearest' }); }, [messages]);

  const submit = async () => {
    const q = text.trim();
    if (!q || busy || !connected) return;
    setBusy(true); setError(null);
    try {
      const reply = await sendChat(runId, q, rowId ?? undefined);
      setMessages((m) => [...m, reply]);
      setText('');
    } catch (e) { setError(formatError(e)); } finally { setBusy(false); }
  };

  return (
    <Panel className="p-3 space-y-2">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-bold text-slate-900">Ask the AI</h3>
        <span className="text-[10px] font-mono text-slate-500">{rowId === null ? 'about this run' : `about the selected row #${rowId}`}</span>
      </div>
      {!connected && <Notice tone="warn">AI narrator not connected: the server has no narrator URL. The chat sends nothing and invents no answer.</Notice>}
      {error && <Notice tone="error">{error}</Notice>}
      <div className="max-h-64 overflow-y-auto space-y-2">
        {messages.map((m) => (
          <div key={m.id} className="space-y-1 text-xs">
            <div className="ml-6 rounded bg-slate-100 px-2 py-1"><span className="text-[10px] font-mono text-slate-500">you{m.row_ref ? ` · row ${m.row_ref}` : ''}: </span>{asPlainText(m.question)}</div>
            <div className="mr-6 rounded border border-dashed border-slate-400 bg-slate-50 px-2 py-1">
              <div className="text-[10px] uppercase font-mono font-bold text-slate-700">AI-generated · {m.model_id}{m.confidence !== null ? ` · narrator's own confidence ${m.confidence}` : ''}</div>
              <p className="whitespace-pre-wrap text-slate-800">{asPlainText(m.text)}</p>
            </div>
          </div>))}
        <div ref={end} />
      </div>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} disabled={!connected || busy}
               placeholder={connected ? 'Why was this flagged? What should I check?' : 'AI narrator not connected'}
               className="flex-1 text-xs border border-[#D3DCE7] rounded px-2 py-1.5 disabled:bg-slate-100" aria-label="question for the AI" />
        <button type="submit" disabled={!connected || busy || !text.trim()} className="px-3 rounded bg-teal-700 text-white text-xs font-bold disabled:opacity-40 flex items-center gap-1">
          <Send className="w-3 h-3" />{busy ? 'Asking…' : 'Ask'}
        </button>
      </form>
    </Panel>
  );
}
