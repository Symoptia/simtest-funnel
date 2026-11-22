import { describe, expect, it, vi } from 'vitest';
import {
  type CompareResult,
  compare,
  createFunnelPlot,
  funnelPlotLayout,
  type PlotlyLike,
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

describe('funnelPlotLayout', () => {
  it('uses title objects, a bottom legend and a right error axis by default', () => {
    const layout = funnelPlotLayout();
    expect(layout.title).toMatchObject({ text: 'Funnel comparison' });
    expect(layout.yaxis).toMatchObject({ title: { text: 'value' } });
    expect(layout.yaxis2).toMatchObject({
      title: { text: '|error|' },
      overlaying: 'y',
      side: 'right',
      automargin: true,
    });
    expect(layout.legend).toMatchObject({
      orientation: 'h',
      yref: 'container',
      y: 0,
      yanchor: 'bottom',
    });
  });

  it('turns string titles into { text } objects (Plotly 3 ignores strings)', () => {
    const layout = funnelPlotLayout({
      title: 'Signal x',
      xaxis: { title: 'time' },
      yaxis: { title: 'm' },
      yaxis2: { title: '|error|, m' },
    });
    expect(layout.title).toMatchObject({ text: 'Signal x', x: 0 });
    expect(layout.xaxis).toEqual({ title: { text: 'time' }, automargin: true });
    expect(layout.yaxis).toMatchObject({ title: { text: 'm' } });
    expect(layout.yaxis2).toMatchObject({
      title: { text: '|error|, m' },
      overlaying: 'y',
      side: 'right',
    });
  });

  it('merges axis, legend and margin objects one level deep', () => {
    const layout = funnelPlotLayout({
      title: { text: '' },
      yaxis2: { range: [0, 1] },
      margin: { t: 40 },
      legend: { y: 1, yanchor: 'top' },
      height: 300,
    });
    expect(layout.title).toMatchObject({ text: '', yref: 'container' });
    expect(layout.yaxis2).toMatchObject({
      range: [0, 1],
      overlaying: 'y',
      title: { text: '|error|' },
    });
    expect(layout.margin).toEqual({ t: 40, r: 8, b: 8, l: 8 });
    expect(layout.legend).toMatchObject({
      orientation: 'h',
      y: 1,
      yanchor: 'top',
    });
    expect(layout.height).toBe(300);
  });

  it('is the layout createFunnelPlot passes to Plotly', async () => {
    const x = new Float64Array([0, 1, 2]);
    const r = compare(x, x, x, x);
    let seen: unknown;
    const plotly: PlotlyLike = {
      newPlot: async (_el, _data, layout) => {
        seen = layout;
        return undefined;
      },
    };
    const given = { title: 'T', xaxis: { title: 'time' } };
    await createFunnelPlot(
      plotly,
      makeEl(),
      { reference: { x, y: x }, test: { x, y: x }, result: r },
      given,
    );
    expect(seen).toEqual(funnelPlotLayout(given));
    expect(given).toEqual({ title: 'T', xaxis: { title: 'time' } });
  });
});
