import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { compare, Status, summarize } from '../src/index.js';

function readXY(path: string): { x: Float64Array; y: Float64Array } {
  const lines = readFileSync(path, 'utf8').trim().split(/\r?\n/);
  const xs: number[] = [];
  const ys: number[] = [];
  for (const line of lines) {
    const parts = line.split(',');
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

describe('summarize', () => {
  it('describes a single excursion above the tube', () => {
    const t = [0, 1, 2, 3, 4];
    const y = [1, 1, 1, 1, 1];
    const yt = [1, 1, 1.5, 1, 1];
    const options = { tolerances: { atoly: 0.2 } };
    const r = compare(t, y, t, yt, options);
    const s = summarize(r, t, options);
    expect(s.status).toBe(Status.Fail);
    expect(s.tolerances.atoly).toBe(0.2);
    expect(s.tolerances.rtoly).toBe(0);
    expect(s.xRange).toEqual({ lo: -Infinity, hi: Infinity });
    expect(s.comparedRange).toEqual({ lo: 0, hi: 4 });
    expect(s.intervals).toHaveLength(1);
    const iv = s.intervals[0];
    expect([iv.startX, iv.endX, iv.direction, iv.pointCount]).toEqual([
      2,
      2,
      'above',
      1,
    ]);
    expect(s.worst).not.toBeNull();
    expect(s.worst?.x).toBe(2);
    expect(s.worst?.deviation).toBeCloseTo(0.3, 12);
    expect(s.worst?.tubeHalfWidthY).toBeCloseTo(0.2, 12);
    expect([s.pointsCompared, s.pointsOutside]).toEqual([5, 1]);
    expect(s.fractionOfPointsOutside).toBe(0.2);
    expect(s.fractionOfSpanOutside).toBe(0.25);
  });

  it('reports no violations for a pass', () => {
    const t = [0, 1, 2, 3];
    const options = { tolerances: { atoly: 0.5 } };
    const s = summarize(compare(t, t, t, t, options), t, options);
    expect(s.status).toBe(Status.Pass);
    expect(s.intervals).toEqual([]);
    expect(s.worst).toBeNull();
    expect(s.fractionOfPointsOutside).toBe(0);
    expect(s.fractionOfSpanOutside).toBe(0);
  });

  it('returns an empty summary for validation statuses', () => {
    const t = [0, 2, 1];
    const y = [0, 1, 2];
    const options = {
      tolerances: { atoly: 0.5 },
      xRange: { lo: 0, hi: 1.5 },
    };
    const r = compare(t, y, [0, 1, 2], y, options);
    const s = summarize(r, t, options);
    expect(s.status).toBe(Status.NonMonotonic);
    expect(s.tolerances.atoly).toBe(0.5);
    expect(s.xRange).toEqual({ lo: 0, hi: 1.5 });
    expect(s.intervals).toEqual([]);
    expect(s.worst).toBeNull();
    expect(s.comparedRange).toBeNull();
    expect([s.pointsCompared, s.pointsOutside]).toEqual([0, 0]);
    expect(s.fractionOfPointsOutside).toBeNull();
    expect(s.fractionOfSpanOutside).toBeNull();
  });

  it('matches the Rust/Python pinned values on fail1', () => {
    // Same pinned values as crates/simtest-funnel-core/tests/summary_corpus.rs
    // and tests/python/test_summary.py.
    const ref = readXY(resolve(CORPUS, 'fail1/trended.csv'));
    const tst = readXY(resolve(CORPUS, 'fail1/simulated.csv'));
    const options = { tolerances: { rtolx: 2e-3, rtoly: 2e-3 } };
    const r = compare(ref.x, ref.y, tst.x, tst.y, options);
    const s = summarize(r, ref.x, options);
    expect(s.status).toBe(Status.Fail);
    expect(s.comparedRange).toEqual({ lo: 54000, hi: 79200 });
    expect(s.intervals).toHaveLength(35);
    expect(s.intervals[0]).toEqual({
      startX: 62435,
      endX: 62530,
      direction: 'above',
      pointCount: 20,
      worstDeviation: 0.0023400000000000087,
      worstX: 62490,
    });
    expect(s.worst).toEqual({
      x: 66925,
      deviation: 0.019127999999996537,
      tubeHalfWidthY: 0.003080000000001748,
    });
    expect([s.pointsCompared, s.pointsOutside]).toEqual([5041, 498]);
    expect(s.fractionOfPointsOutside).toBe(0.09878992263439794);
    expect(s.fractionOfSpanOutside).toBe(0.0988095238095238);
  });
});
