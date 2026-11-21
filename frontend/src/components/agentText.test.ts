import { describe, expect, it } from 'vitest';
import { describeEvent, describeProposal, statusWords } from './agentText';

describe('agentText', () => {
  it('says "agent not connected" in plain words and never calls an abstention a success', () => {
    expect(statusWords('agent_not_connected')).toMatch(/not connected/i);
    expect(statusWords('abstained')).not.toMatch(/done/i);
    expect(statusWords('something_new')).toBe('something_new');
  });
  it('describes a proposal with its label and where it points', () => {
    expect(describeProposal({ action: 'propose_reviewer_label', run_id: 3, row_ref: '9', args: { label: 'false_alarm' } })).toBe('propose reviewer label: false_alarm (run 3, row 9)');
    expect(describeProposal({ action: 'ask_user', run_id: null, row_ref: null, args: { question: 'Which file?' } })).toBe('ask user: Which file?');
  });
  it('describes an event from its tools, note and real outcome', () => {
    const line = describeEvent({ node: 'act', note: '', tool_calls: [{ tool: 'get_run_summary', ok: false }], outcome: { status: 'refused', detail: 'bad label' } });
    expect(line).toContain('get_run_summary (failed)');
    expect(line).toContain('outcome: refused (bad label)');
    expect(describeEvent({ node: 'x', note: '', tool_calls: [], outcome: null })).toBe('-');
  });
});
