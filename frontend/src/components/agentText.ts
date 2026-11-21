// Words for the Agent page (PROTOTYPE of a sandboxed, bounded decision-support agent). Pure helpers, tested in agentText.test.ts.
import { errorText, isNotBuilt } from '../services/api';

/** The Agent page's error line: an absent /api/agent (404, 405, 501, 502, 503) means the agent packages are not installed on this server. */
export function agentErrorText(err: unknown): string {
  return isNotBuilt(err) ? 'Agent service not available on this server (the agent packages are not installed).' : errorText(err);
}

/** What a task status means, in words. Only "completed" means a proposal was recorded. */
export function statusWords(status: string): string {
  switch (status) {
    case 'completed':
      return 'Done. The answer is generated text from the evidence the agent read.';
    case 'agent_not_connected':
      return 'Agent not connected. The rule-based explanation below is shown instead.';
    case 'abstained':
      return 'The agent abstained: the evidence or the proposals were not good enough to act on.';
    case 'needs_clarification':
      return 'The agent needs clarification before it can act.';
    case 'explanation_refused':
      return 'The generated explanation was refused: it named something the tools did not return.';
    case 'gate_refused':
      return 'The execution gate refused the action.';
    case 'act_refused':
      return 'The executor refused the action.';
    case 'act_error':
      return 'The action failed with an error. Nothing is assumed to have happened.';
    default:
      return status;
  }
}

/** One line per proposal, e.g. "propose reviewer label: false_alarm (run 3, row 9)". */
export function describeProposal(p: { action: string; run_id: number | null; row_ref: string | null; args: Record<string, unknown> }): string {
  const name = p.action.replace(/_/g, ' ');
  const detail = p.args.label ?? p.args.note ?? p.args.question ?? p.args.reason;
  const where = p.run_id != null ? ` (run ${p.run_id}${p.row_ref ? `, row ${p.row_ref}` : ''})` : '';
  return `${name}${detail != null ? `: ${String(detail)}` : ''}${where}`;
}

/** The "why" line of one event: what the step decided or why it stopped. */
export function describeEvent(e: { node: string; note: string; tool_calls: { tool: string; ok: boolean }[]; outcome: { status: string; detail: string } | null }): string {
  const parts: string[] = [];
  if (e.tool_calls.length) parts.push(`tools: ${e.tool_calls.map((c) => `${c.tool}${c.ok ? '' : ' (failed)'}`).join(', ')}`);
  if (e.note) parts.push(e.note);
  if (e.outcome) parts.push(`outcome: ${e.outcome.status}${e.outcome.detail ? ` (${e.outcome.detail})` : ''}`);
  return parts.join('; ') || '-';
}
