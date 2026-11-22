import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { compare, downsampleMinMax, Status, summarize } from '../src/index.js';

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

const X = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
const Y = [0, 5, 1, 2, 9, 3, 4, 8, 6, 7];

describe('downsampleMinMax', () => {
  it('keeps the extremes of each bucket', () => {
    const d = downsampleMinMax(X, Y, 2);
    expect(d.indices).toBeInstanceOf(Uint32Array);
    expect(d.x).toBeInstanceOf(Float64Array);
    expect(Array.from(d.indices)).toEqual([0, 4, 5, 7, 9]);
    expect(Array.from(d.x)).toEqual([0, 4, 5, 7, 9]);
    expect(Array.from(d.y)).toEqual([0, 9, 3, 8, 7]);
  });

  it('keeps pinned samples', () => {
    expect(Array.from(downsampleMinMax(X, Y, 2, [2.2]).indices)).toEqual([
      0, 2, 4, 5, 7, 9,
    ]);
    expect(Array.from(downsampleMinMax(X, Y, 2, [2.5]).indices)).toEqual([
      0, 2, 4, 5, 7, 9,
    ]);
    expect(
      Array.from(downsampleMinMax(X, Y, 2, [-5, 100, Number.NaN]).indices),
    ).toEqual([0, 4, 5, 7, 9]);
  });

  it('returns small and empty signals unchanged', () => {
    const x = [0, 1, 2, 3, 4, 5, 6, 7];
    const y = [3, 1, 4, 1, 5, 9, 2, 6];
    expect(Array.from(downsampleMinMax(x, y, 4).y)).toEqual(y);
    expect(Array.from(downsampleMinMax([], [], 1).indices)).toEqual([]);
    expect(
      downsampleMinMax(x, y, Number.POSITIVE_INFINITY).indices,
    ).toHaveLength(8);
  });

  it('rejects invalid input', () => {
    expect(() => downsampleMinMax([0, 1, 2], [0, 1], 1)).toThrow(
      'length mismatch: x has 3 values but y has 2',
    );
    expect(() => downsampleMinMax([0, 2, 1], [0, 0, 0], 1)).toThrow(
      'non-monotonic x: x[2] < x[1]',
    );
    expect(() => downsampleMinMax([0, Number.NaN], [0, 0], 1)).toThrow(
      'non-finite x-value at index 1',
    );
    expect(() => downsampleMinMax([0], [0], 0)).toThrow(
      'buckets must be at least 1',
    );
    expect(() => downsampleMinMax([0], [0], -3)).toThrow(
      'buckets must be at least 1',
    );
    expect(() => downsampleMinMax([0], [0], 1.5)).toThrow(
      'buckets must be an integer',
    );
    expect(() => downsampleMinMax([0], [0], 0)).toThrow(Error);
  });

  it('keeps every violation of fail1 when worst points are pinned', () => {
    const ref = readXY(resolve(CORPUS, 'fail1/trended.csv'));
    const tst = readXY(resolve(CORPUS, 'fail1/simulated.csv'));
    // The corpus case's tolerances (param.json), given explicitly so the
    // check does not depend on the library default.
    const options = { tolerances: { rtolx: 2e-3, rtoly: 2e-3 } };
    const r = compare(ref.x, ref.y, tst.x, tst.y, options);
    const s = summarize(r, ref.x, options);
    expect(r.status).toBe(Status.Fail);
    const pins = s.intervals.map((iv) => iv.worstX);
    const d = downsampleMinMax(tst.x, tst.y, 50, pins);

    for (const iv of s.intervals) {
      const kept = Array.from(d.indices).some(
        (j) =>
          tst.x[j] >= iv.startX && tst.x[j] <= iv.endX && r.errorsY[j] !== 0,
      );
      expect(kept, `[${iv.startX}, ${iv.endX}]`).toBe(true);
    }

    // Pinned values shared with the Rust and Python tests.
    expect([tst.x.length, pins.length]).toEqual([5041, 35]);
    expect(d.indices).toHaveLength(117);
    expect(d.indices.reduce((a, b) => a + b, 0)).toBe(311003);
    expect(Array.from(d.indices.slice(0, 8))).toEqual([
      0, 101, 202, 303, 404, 504, 605, 706,
    ]);
    expect(Array.from(d.indices.slice(-4))).toEqual([4939, 4940, 5029, 5040]);
  });
});
