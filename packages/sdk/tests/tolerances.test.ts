import { describe, expect, it } from 'vitest';
import {
  compare,
  defaultOptions,
  type Options,
  type ResolvedTolerances,
  Status,
  summarize,
} from '../src/index.js';

// Step-edge case shared with tests/python/test_tolerances.py, the Rust
// core and CLI tests: the test signal is the reference step delayed by
// 0.001 in x, so it passes only when the x axis keeps a non-zero tolerance.
const t = Float64Array.from({ length: 101 }, (_, i) => i / 100);
const clip = (v: number): number => Math.min(Math.max(v, 0), 1);
const yRef = t.map((x) => clip((x - 0.49) / 0.01));
const yTest = t.map((x) => clip((x - 0.491) / 0.01));

const ZERO: ResolvedTolerances = {
  atolx: 0,
  atoly: 0,
  ltolx: 0,
  ltoly: 0,
  rtolx: 0,
  rtoly: 0,
};
const DEFAULT: ResolvedTolerances = { ...ZERO, rtolx: 2e-3, rtoly: 2e-3 };

function resolved(options?: Options): {
  status: number;
  tolerances: ResolvedTolerances;
} {
  const r = compare(t, yRef, t, yTest, options);
  return {
    status: r.status,
    tolerances: summarize(r, t, options).tolerances,
  };
}

describe('tolerance resolution', () => {
  it('uses the default when options are omitted', () => {
    expect(resolved()).toEqual({ status: Status.Pass, tolerances: DEFAULT });
  });

  it('treats empty options / tolerances like omitted options', () => {
    const none = resolved();
    expect(resolved({})).toEqual(none);
    expect(resolved({ tolerances: {} })).toEqual(none);
    expect(resolved({ xRange: { lo: -Infinity, hi: Infinity } })).toEqual(none);
  });

  it('keeps the x default when only atoly is given', () => {
    expect(resolved({ tolerances: { atoly: 0.05 } })).toEqual({
      status: Status.Pass,
      tolerances: { ...ZERO, atoly: 0.05, rtolx: 2e-3 },
    });
  });

  it('counts an explicit zero as given', () => {
    expect(resolved({ tolerances: { atolx: 0, atoly: 0.05 } })).toEqual({
      status: Status.Fail,
      tolerances: { ...ZERO, atoly: 0.05 },
    });
  });

  it('treats null and undefined fields as not given', () => {
    const onlyY = resolved({ tolerances: { atoly: 0.05 } });
    expect(resolved({ tolerances: { atolx: null, atoly: 0.05 } })).toEqual(
      onlyY,
    );
    expect(resolved({ tolerances: { atolx: undefined, atoly: 0.05 } })).toEqual(
      onlyY,
    );
  });

  it('keeps the y default when only ltolx is given', () => {
    expect(resolved({ tolerances: { ltolx: 0.01 } }).tolerances).toEqual({
      ...ZERO,
      ltolx: 0.01,
      rtoly: 2e-3,
    });
  });

  it('zeroes the rest of an axis with one coefficient given', () => {
    expect(
      resolved({ tolerances: { atolx: 0.1, atoly: 0.1 } }).tolerances,
    ).toEqual({ ...ZERO, atolx: 0.1, atoly: 0.1 });
  });

  it('uses fully explicit tolerances verbatim', () => {
    const explicit: ResolvedTolerances = {
      atolx: 0.1,
      atoly: 0.2,
      ltolx: 0.3,
      ltoly: 0.4,
      rtolx: 0.5,
      rtoly: 0.6,
    };
    expect(resolved({ tolerances: explicit }).tolerances).toEqual(explicit);
  });

  it('defaultOptions() agrees with omitted options', () => {
    const d = defaultOptions();
    expect(d.tolerances).toEqual(DEFAULT);
    expect(d.xRange).toEqual({ lo: -Infinity, hi: Infinity });
    expect(compare(t, yRef, t, yTest, d)).toEqual(compare(t, yRef, t, yTest));
  });
});
