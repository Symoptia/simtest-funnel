import { describe, expect, it, vi } from 'vitest';
import {
  type CompareResult,
  type PlotlyLike,
  compare,
  createFunnelPlot,
} from '../src/index.js';

function makeEl(): HTMLElement {
  // Minimal object — createFunnelPlot does not touch the element
  // itself, it just forwards to Plotly.
  return {} as unknown as HTMLElement;
}

describe('createFunnelPlot', () => {
  it('creates five named traces and forwards them to Plotly.newPlot', async () => {
    const rx = new Float64Array([0, 1, 2, 3]);
    const ry = new Float64Array([0, 1, 2, 3]);
    const tx = new Float64Array([0, 1, 2, 3]);
    const ty = new Float64Array([0.1, 1.05, 2.0, 3.05]);
    const r: CompareResult = compare(rx, ry, tx, ty, {
      tolerances: { atoly: 0.2, atolx: 0.0, rtolx: 0.0, rtoly: 0.0 },
    });
    const calls: { el: HTMLElement; data: unknown[]; layout?: unknown }[] = [];
    const plotly: PlotlyLike = {
      newPlot: vi.fn(async (el, data, layout) => {
        calls.push({ el, data: data as unknown[], layout });
        return undefined;
      }),
    };
    const el = makeEl();
    await createFunnelPlot(plotly, el, {
      reference: { x: rx, y: ry },
      test: { x: tx, y: ty },
      result: r,
    });
    expect(calls).toHaveLength(1);
    const traces = calls[0].data as Array<{ name: string }>;
    expect(traces).toHaveLength(5);
    const names = traces.map((t) => t.name).sort();
    expect(names).toEqual(
      ['error', 'lower bound', 'reference', 'test', 'upper bound'].sort(),
    );
  });
});
