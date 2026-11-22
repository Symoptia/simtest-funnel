import { Status } from '@simtest-js/funnel';
import { describe, expect, it } from 'vitest';
import {
  compareAge,
  compareAllAges,
  toTolerances,
} from '../src/weather/compare';
import type { WeatherData } from '../src/weather/model';
import { loadSample } from '../src/weather/sample';

const T0 = 1_800_000_000;

function synthetic(
  latest: number[],
  ages: Record<number, number[]>,
  source: 'sample' | 'live' = 'live',
): WeatherData {
  return {
    place: 'Test',
    variable: 'temperature_2m',
    unit: '°C',
    time: Float64Array.from(latest.map((_, i) => T0 + i * 3600)),
    latest: Float64Array.from(latest),
    ages: new Map(
      Object.entries(ages).map(([a, v]) => [Number(a), Float64Array.from(v)]),
    ),
    source,
  };
}

/** A smooth daily cycle, optionally shifted by `shift` hours. */
function cycle(n: number, shift = 0): number[] {
  return Array.from(
    { length: n },
    (_, i) => 5 + 4 * Math.sin((2 * Math.PI * (i - shift)) / 24),
  );
}

/** A warm spell around hour 48 (flat at both ends), shifted by `shift` h. */
function pulse(n: number, shift = 0): number[] {
  return Array.from(
    { length: n },
    (_, i) => 5 + 4 * Math.exp(-(((i - 48 - shift) / 4) ** 2)),
  );
}

const FAR_FUTURE = Number.POSITIVE_INFINITY;

describe('compareAge', () => {
  it('always passes both tolerance axes', () => {
    expect(toTolerances({ valueTol: 2, timeTolHours: 3 })).toEqual({
      atoly: 2,
      atolx: 10800,
    });
    expect(toTolerances({ valueTol: 0.5, timeTolHours: 0 })).toEqual({
      atoly: 0.5,
      atolx: 0,
    });
  });

  it('fails a 2 h shifted forecast at 0 h and passes it at ±3 h', () => {
    const data = synthetic(pulse(96), { 3: pulse(96, 2) });
    const strict = compareAge(
      data,
      3,
      { valueTol: 0.5, timeTolHours: 0 },
      FAR_FUTURE,
    );
    expect(strict.row.pass).toBe(false);
    expect(strict.row.status).toBe(Status.Fail);
    expect(strict.row.pointsOutside).toBeGreaterThan(0);
    const loose = compareAge(
      data,
      3,
      { valueTol: 0.5, timeTolHours: 3 },
      FAR_FUTURE,
    );
    expect(loose.row.pass).toBe(true);
    expect(loose.row.pointsOutside).toBe(0);
    expect(loose.row.fractionOfPointsOutside).toBe(0);
    expect(loose.row.pointsCompared).toBe(96);
    expect(loose.series?.time.length).toBe(96);
  });

  it('drops hours with a gap in either series and reports them', () => {
    const fc = cycle(336);
    for (let i = 100; i < 124; i++) {
      fc[i] = Number.NaN;
    }
    const latest = cycle(336);
    const data = synthetic(latest, { 3: fc });
    const c = compareAge(data, 3, { valueTol: 2, timeTolHours: 3 }, FAR_FUTURE);
    expect(c.row.total).toBe(336);
    expect(c.row.missing).toBe(24);
    expect(c.row.pointsCompared).toBe(312);
    expect(c.series?.time.length).toBe(312);
  });

  it('gives no verdict for an age without data', () => {
    const data = synthetic(cycle(48), {
      7: Array.from({ length: 48 }, () => Number.NaN),
    });
    const c = compareAge(data, 7, { valueTol: 2, timeTolHours: 3 }, FAR_FUTURE);
    expect(c.row.status).toBeNull();
    expect(c.row.pass).toBeNull();
    expect(c.row.missing).toBe(48);
    expect(c.result).toBeUndefined();
    // One remaining hour is not enough either.
    const one = Array.from({ length: 48 }, () => Number.NaN);
    one[5] = 1;
    const d = compareAge(
      synthetic(cycle(48), { 7: one }),
      7,
      { valueTol: 2, timeTolHours: 3 },
      FAR_FUTURE,
    );
    expect(d.row.status).toBeNull();
  });

  it('leaves out live hours later than now, but not sample hours', () => {
    const now = T0 + 23 * 3600; // hours 0..23 are not in the future
    const live = synthetic(cycle(48), { 1: cycle(48) });
    const c = compareAge(live, 1, { valueTol: 2, timeTolHours: 3 }, now);
    expect(c.row.total).toBe(24);
    expect(c.row.pointsCompared).toBe(24);
    expect(c.row.missing).toBe(0);
    const sample = synthetic(cycle(48), { 1: cycle(48) }, 'sample');
    expect(
      compareAge(sample, 1, { valueTol: 2, timeTolHours: 3 }, now).row.total,
    ).toBe(48);
  });

  it('compares every age in ascending order', () => {
    const data = synthetic(cycle(24), { 5: cycle(24), 1: cycle(24) });
    const rows = compareAllAges(
      data,
      { valueTol: 1, timeTolHours: 0 },
      FAR_FUTURE,
    );
    expect(rows.map((r) => r.row.age)).toEqual([1, 5]);
  });
});

describe('pipeline on the bundled sample', () => {
  // Pinned by the MCP walkthrough (python/simtest-funnel-mcp/README.md and
  // tests/test_mcp_examples.py): points outside of 360 for day 1/3/5.
  const MCP_WALKTHROUGH = {
    '2C': { 1: 0, 3: 38, 5: 84 },
    '2C_3h': { 1: 0, 3: 14, 5: 47 },
  } as const;

  const sample = loadSample();

  it.each([
    ['2C', { valueTol: 2, timeTolHours: 0 }],
    ['2C_3h', { valueTol: 2, timeTolHours: 3 }],
  ] as const)('matches the MCP walkthrough at %s', (label, tol) => {
    const rows = compareAllAges(sample, tol, Date.now() / 1000).map(
      (c) => c.row,
    );
    expect(rows.map((r) => r.age)).toEqual([1, 3, 5]);
    for (const row of rows) {
      const expected =
        MCP_WALKTHROUGH[label][row.age as keyof (typeof MCP_WALKTHROUGH)['2C']];
      expect(row.pointsCompared).toBe(360);
      expect(row.missing).toBe(0);
      expect(row.pointsOutside).toBe(expected);
      expect(row.pass).toBe(expected === 0);
      expect(row.fractionOfPointsOutside).toBeCloseTo(expected / 360, 12);
    }
  });

  it('shows the walkthrough percentages', () => {
    const rows = compareAllAges(
      sample,
      { valueTol: 2, timeTolHours: 3 },
      Date.now() / 1000,
    ).map((c) => ((c.row.fractionOfPointsOutside ?? 0) * 100).toFixed(1));
    expect(rows).toEqual(['0.0', '3.9', '13.1']);
  });
});
