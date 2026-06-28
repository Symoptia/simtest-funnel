import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { Status, compare, defaultOptions, version } from '../src/index.js';

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
