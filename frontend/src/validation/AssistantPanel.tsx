// The assistant: questions about the imported data. Its replies are generated (rule-based baseline now, the AI narrator when connected),
// always badged GENERATED and drawn dashed; a reply may carry a table spec that runs only when the user clicks. It never changes data.
import { useRef, useState } from 'react';
import { Send } from 'lucide-react';
import { askAssistant } from './api';
import { asPlainText } from './lib';
import type { AssistantReply, ChatTurn, QuerySpec } from './types';
import { GeneratedBadge, NOT_MEASURED, Notice, Panel, btn, btnQuiet, field, formatError } from './ui';

export const NARRATOR_OFF = 'AI narrator not connected, rule-based assistant';

/** One generated reply: the text, the why lines, the generator note and (optionally) the table it proposes. */
export function ReplyCard({ reply, onShowTable, children }: { reply: AssistantReply; onShowTable?: (s: QuerySpec) => void; children?: React.ReactNode }) {
  return (
    <div className={`rounded px-2 py-1.5 text-xs space-y-1 ${NOT_MEASURED}`}>
      <div className="flex items-center gap-2 flex-wrap"><GeneratedBadge /><span className="text-[10px] font-mono text-slate-500">{reply.generator}{reply.label ? ` · ${reply.label}` : ''}</span></div>
      {reply.generator === 'baseline-rules' && <p className="text-[10px] text-amber-800">{NARRATOR_OFF}</p>}
      <p className="whitespace-pre-wrap text-slate-800">{asPlainText(reply.reply)}</p>
      {reply.why.length > 0 && (
        <div><div className="text-[10px] uppercase font-mono text-slate-500">Why</div>
          <ul className="list-disc ml-4 text-slate-700">{reply.why.map((w, i) => <li key={i}>{asPlainText(w)}</li>)}</ul></div>)}
      {reply.table_spec && onShowTable && <button className={btnQuiet} onClick={() => onShowTable(reply.table_spec as QuerySpec)}>Show this table</button>}
      {children}
    </div>);
}

export function AssistantPanel({ onShowTable, runId }: { onShowTable: (s: QuerySpec) => void; runId?: number | null }) {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const end = useRef<HTMLDivElement>(null);

  const submit = async () => {
    const q = text.trim();
    if (!q || busy) return;
    setBusy(true); setError('');
    const history = turns;
    setTurns((t) => [...t, { role: 'user', text: q }]); setText('');
    try {
      const r = await askAssistant(q, history, runId);
      setTurns((t) => [...t, { role: 'assistant', text: r.reply, reply: r }]);
    } catch (e) { setError(formatError(e)); } finally { setBusy(false); end.current?.scrollIntoView?.({ block: 'nearest' }); }
  };

  return (
    <Panel className="p-3 space-y-2 flex flex-col">
      <h3 className="text-sm font-bold text-slate-900">Assistant</h3>
      <p className="text-[11px] text-slate-600">Ask about your tables, for example "which station has the most rows?". It answers from the stored data and only advises: it never changes it.</p>
      {error && <Notice tone="error">{error}</Notice>}
      <div className="max-h-96 overflow-y-auto space-y-2" aria-live="polite">
        {turns.map((t, i) => t.role === 'user'
          ? <div key={i} className="ml-6 rounded bg-slate-100 px-2 py-1 text-xs"><span className="text-[10px] font-mono text-slate-500">you: </span>{asPlainText(t.text)}</div>
          : t.reply && <ReplyCard key={i} reply={t.reply} onShowTable={onShowTable} />)}
        <div ref={end} />
      </div>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
        <input value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} disabled={busy} className={`${field} flex-1`} aria-label="question for the assistant" placeholder="Ask about your data" />
        <button type="submit" disabled={busy || !text.trim()} className={`${btn} flex items-center gap-1`}><Send className="w-3 h-3" />{busy ? 'Asking…' : 'Ask'}</button>
      </form>
    </Panel>);
}
