// The x-range window: the tube is built from the reference extended beyond
// the window, so in-window test points are judged as in a full-range
// comparison (same cases as the Rust, Python and MCP tests).
import { describe, expect, it } from 'vitest';
import {
  type CompareResult,
  compare,
  Status,
  summarize,
} from '../src/index.js';

const HOUR = 3600;
const DAY = 86400;
const tolerances = { atolx: 3 * HOUR, atoly: 0.05 };

// Hourly daily temperature cycle over 6 days; the test is 2 h late.
const t = Array.from({ length: 145 }, (_, h) => h * HOUR);
const temp = (s: number) =>
  10 + 5 * Math.cos((2 * Math.PI * (s - 14 * HOUR)) / DAY);
const yRef = t.map(temp);
const yTest = t.map((s) => temp(s - 2 * HOUR));
const last = t[t.length - 1];

function run(
  lo: number | null,
  hi: number | null,
  tol: typeof tolerances = tolerances,
): CompareResult {
  return compare(t, yRef, t, yTest, { tolerances: tol, xRange: { lo, hi } });
}

function inWindow(r: CompareResult, lo: number, hi: number): number[] {
  return t.flatMap((x, j) => (x >= lo && x <= hi ? [r.errorsY[j]] : []));
}

describe('x-range window', () => {
  const full = run(null, null);

  it('passes a shift within atolx at the window edges', () => {
    // Only the first hours of the data fail: no earlier reference there.
    expect(full.status).toBe(Status.Fail);
    full.errorsY.forEach((e, j) => {
      if (e !== 0) expect(t[j]).toBeLessThan(3 * HOUR);
    });
    const options = { tolerances, xRange: { lo: 2 * DAY, hi: 4 * DAY } };
    const win = compare(t, yRef, t, yTest, options);
    expect(win.status).toBe(Status.Pass);
    const s = summarize(win, t, options);
    expect([s.pointsCompared, s.pointsOutside]).toEqual([49, 0]);
    expect(win.lowerX[0]).toBeLessThan(2 * DAY - 3 * HOUR);
    expect(win.upperX[win.upperX.length - 1]).toBeGreaterThan(
      4 * DAY + 3 * HOUR,
    );
    t.forEach((x, j) => {
      expect(win.errorsX[j]).toBe(x);
      if (x < 2 * DAY || x > 4 * DAY) expect(win.errorsY[j]).toBe(0);
    });
  });

  it('handles a window narrower than the x tolerance', () => {
    const [lo, hi] = [2.5 * DAY, 2.5 * DAY + HOUR];
    const win = run(lo, hi);
    expect(win.status).toBe(Status.Pass);
    expect(inWindow(win, lo, hi)).toEqual(inWindow(full, lo, hi));
    expect(run(lo, hi, { atolx: 0.5 * HOUR, atoly: 0.05 }).status).toBe(
      Status.Fail,
    );
  });

  it('leaves the data start and end unchanged', () => {
    const cases: [number, number, number][] = [
      [0, DAY, Status.Fail],
      [-1e6, DAY, Status.Fail],
      [5 * DAY, last, Status.Pass],
      [5 * DAY, 1e9, Status.Pass],
    ];
    for (const [lo, hi, status] of cases) {
      const win = run(lo, hi);
      expect(win.status).toBe(status);
      expect(inWindow(win, lo, hi)).toEqual(inWindow(full, lo, hi));
    }
    expect(run(0, DAY).lowerX[0]).toBe(full.lowerX[0]);
    const end = run(5 * DAY, 1e9).upperX;
    expect(end[end.length - 1]).toBe(full.upperX[full.upperX.length - 1]);
  });

  it('compares a window partly outside the data on the overlap', () => {
    expect(run(3 * HOUR, DAY).status).toBe(Status.Pass);
    expect(run(last - DAY, last + DAY).status).toBe(Status.Pass);
    expect(run(last + 1, last + DAY).status).toBe(Status.EmptyRange);
    expect(run(last + 1, last + HOUR).status).toBe(Status.EmptyRange);
  });

  it('keeps rtoly relative to the window', () => {
    const x = Array.from({ length: 101 }, (_, i) => i);
    const yt = x.map((v) => v + 0.5);
    const tol = { rtoly: 0.01 };
    expect(compare(x, x, x, yt, { tolerances: tol }).status).toBe(Status.Pass);
    expect(
      compare(x, x, x, yt, { tolerances: tol, xRange: { lo: 0, hi: 10 } })
        .status,
    ).toBe(Status.Fail);
  });

  it('judges in-window points as the full-range comparison does', () => {
    // Deterministic pseudo-random signals (xorshift32).
    let s = 2463534242;
    const rnd = () => {
      s ^= s << 13;
      s ^= s >>> 17;
      s ^= s << 5;
      return (s >>> 0) / 4294967296;
    };
    let windows = 0;
    for (let c = 0; c < 200; c++) {
      const n = 20 + Math.floor(rnd() * 150);
      const x: number[] = [];
      const y: number[] = [];
      let xv = 100 * rnd();
      let yv = 0;
      for (let i = 0; i < n; i++) {
        x.push(xv);
        y.push(yv);
        xv += 0.2 + rnd();
        yv += rnd() - 0.5;
      }
      const shift = rnd() * 2 - 1;
      const xt = x.map((v) => v + shift * 0.5);
      const yt = y.map((v) => v + (rnd() - 0.5) * 0.2);
      const tol = {
        atolx: 5 * rnd(),
        atoly: 0.5 * rnd(),
        ltoly: rnd() < 0.3 ? 0.2 * rnd() : 0,
      };
      const span = x[n - 1] - x[0];
      const lo = x[0] + (rnd() * 1.2 - 0.1) * span;
      const hi = lo + rnd() * 0.5 * span;
      const fullR = compare(x, y, xt, yt, { tolerances: tol });
      const win = compare(x, y, xt, yt, {
        tolerances: tol,
        xRange: { lo, hi },
      });
      if (win.status !== Status.Pass && win.status !== Status.Fail) continue;
      windows++;
      const [effLo, effHi] = [Math.max(lo, x[0]), Math.min(hi, x[n - 1])];
      let fail = false;
      xt.forEach((v, j) => {
        if (v < effLo || v > effHi) return;
        expect(win.errorsY[j]).toBe(fullR.errorsY[j]);
        if (fullR.errorsY[j] !== 0) fail = true;
      });
      expect(win.status === Status.Fail).toBe(fail);
    }
    expect(windows).toBeGreaterThan(50);
  });
});
