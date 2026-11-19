import { describe, expect, it } from 'vitest';
import { LINEAGE_BOX, layoutLineage, tone } from './LineageGraph';
import type { Lineage, LineageNode } from './types';

const node = (id: string, kind: LineageNode['kind'], status = 'done'): LineageNode => ({ id, kind, label: id, status, facts: {} });
const { W, H, GX, GY, PAD } = LINEAGE_BOX;

const data: Lineage = {
  columns: ['job', 'run', 'snapshot'],
  nodes: [node('j1', 'job'), node('j2', 'job'), node('r1', 'run'), node('s1', 'snapshot')],
  edges: [{ from: 'j1', to: 'r1' }, { from: 'j2', to: 'r1' }, { from: 'r1', to: 's1' }, { from: 'r1', to: 'ghost' }, { from: 'nope', to: 's1' }],
  note: '',
};

describe('layoutLineage', () => {
  const l = layoutLineage(data);
  it('puts each kind in its own column and stacks rows', () => {
    expect(l.pos.get('j1')).toEqual({ x: PAD, y: PAD + 22 });
    expect(l.pos.get('j2')).toEqual({ x: PAD, y: PAD + 22 + H + GY });
    expect(l.pos.get('r1')).toEqual({ x: PAD + W + GX, y: PAD + 22 });
    expect(l.pos.get('s1')!.x).toBe(PAD + 2 * (W + GX));
  });
  it('keeps only edges between known nodes', () => {
    expect(l.edges).toEqual([{ from: 'j1', to: 'r1' }, { from: 'j2', to: 'r1' }, { from: 'r1', to: 's1' }]);
  });
  it('sizes the canvas to the widest column', () => {
    expect(l.width).toBe(PAD * 2 + 3 * W + 2 * GX);
    expect(l.height).toBe(PAD * 2 + 22 + 2 * H + GY);
  });
  it('does not place nodes whose kind is not a column', () => {
    const x = layoutLineage({ ...data, nodes: [...data.nodes, node('m1', 'model')] });
    expect(x.pos.has('m1')).toBe(false);
  });
  it('handles an empty graph', () => {
    const e = layoutLineage({ columns: [], nodes: [], edges: [], note: '' });
    expect(e.pos.size).toBe(0); expect(e.edges).toEqual([]);
    expect(e.height).toBe(PAD * 2 + 22 + H);
  });
});

describe('tone', () => {
  const c = (s: string) => tone(node('n', 'job', s));
  it('maps status to colour', () => {
    for (const s of ['champion', 'done', 'complete', 'completed']) expect(c(s)).toBe('#059669');
    for (const s of ['failed', 'rejected']) expect(c(s)).toBe('#DC2626');
    for (const s of ['running', 'queued', 'challenger']) expect(c(s)).toBe('#0284C7');
    expect(c('pending')).toBe('#64748B');
  });
});
