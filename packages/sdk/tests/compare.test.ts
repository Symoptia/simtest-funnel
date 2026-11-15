import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  compare,
  defaultOptions,
  Status,
  summarize,
  version,
} from '../src/index.js';

function readXY(path: string): { x: Float64Array; y: Float64Array } {
  const lines = readFileSync(path, 'utf8').trim().split(/\r?\n/);
  const xs: number[] = [];
  const ys: number[] = [];
  for (let i = 0; i < lines.length; i++) {
    const parts = lines[i].split(',');
    const x = Number.parseFloat(parts[0]);
    const y = Number.parseFloat(parts[1]);
    if (Number.isNaN(x) || Number.isNaN(y)) continue;
    xs.push(x);
    ys.push(y);
  }
  return { x: Float64Array.from(xs), y: Float64Array.from(ys) };
}

const CORPUS = resolve(
  __dirname,
  '../../../crates/simtest-funnel-core/tests/corpus',
);

describe('version', () => {
  it('returns a non-empty string', () => {
    const v = version();
    expect(typeof v).toBe('string');
    expect(v.length).toBeGreaterThan(0);
  });
});

describe('defaultOptions', () => {
  it('returns rtolx=rtoly=2e-3', () => {
    const o = defaultOptions();
    expect(o.tolerances?.rtolx).toBeCloseTo(2e-3);
    expect(o.tolerances?.rtoly).toBeCloseTo(2e-3);
  });
});

describe('compare', () => {
  it('flags the fail1 corpus case as Fail', () => {
    const ref = readXY(resolve(CORPUS, 'fail1/trended.csv'));
    const tst = readXY(resolve(CORPUS, 'fail1/simulated.csv'));
    const r = compare(ref.x, ref.y, tst.x, tst.y, {
      tolerances: { atolx: 0, atoly: 0, rtolx: 0.002, rtoly: 0.002 },
    });
    expect(r.status).toBe(Status.Fail);
    expect(r.lowerX.length).toBeGreaterThan(0);
    expect(r.upperX.length).toBeGreaterThan(0);
    expect(r.errorsY.some((v: number) => v !== 0)).toBe(true);
  });

  it('reports Pass for success1', () => {
    const ref = readXY(resolve(CORPUS, 'success1/trended.csv'));
    const tst = readXY(resolve(CORPUS, 'success1/simulated.csv'));
    const r = compare(ref.x, ref.y, tst.x, tst.y, {
      tolerances: { atolx: 0, atoly: 0, rtolx: 0.002, rtoly: 0.002 },
    });
    expect(r.status).toBe(Status.Pass);
    expect(r.errorsY.every((v: number) => v === 0)).toBe(true);
  });
});

describe('xRange with one bound', () => {
  const t = [0, 0.25, 0.5, 0.75, 1];
  const y = [0, 0, 0, 0, 0];
  // Only the first test point is outside the tube.
  const yt = [5, 0, 0, 0, 0];
  const tolerances = { atolx: 0, atoly: 0.1 };

  it('treats an omitted hi as unbounded', () => {
    const options = { tolerances, xRange: { lo: 0.5 } };
    const r = compare(t, y, t, yt, options);
    expect(r.status).toBe(Status.Pass);
    const s = summarize(r, t, options);
    expect(s.xRange).toEqual({ lo: 0.5, hi: Infinity });
    expect(s.comparedRange).toEqual({ lo: 0.5, hi: 1 });
    expect(s.pointsCompared).toBe(3);
  });

  it('treats an omitted or null lo as unbounded', () => {
    expect(
      compare(t, y, t, yt, { tolerances, xRange: { hi: 0.5 } }).status,
    ).toBe(Status.Fail);
    const s = summarize(
      compare(t, y, t, yt, { tolerances, xRange: { lo: null, hi: 0.5 } }),
      t,
      { tolerances, xRange: { lo: null, hi: 0.5 } },
    );
    expect(s.xRange).toEqual({ lo: -Infinity, hi: 0.5 });
  });

  it('judges coverage within the x-range', () => {
    const tt = [0, 0.25, 0.5, 0.75, 1, 1.1];
    const ytt = [0, 0, 0, 0, 0, 0];
    expect(compare(t, y, tt, ytt, { tolerances }).status).toBe(
      Status.MissingReference,
    );
    expect(
      compare(t, y, tt, ytt, { tolerances, xRange: { hi: 1 } }).status,
    ).toBe(Status.Pass);
  });
});
