// Comparison pipeline: for every forecast age, align with the latest run,
// drop missing and future hours, and run the WASM funnel comparison.

import {
  type CompareResult,
  compare,
  Status,
  type StatusCode,
  summarize,
  type Tolerances,
} from '@simtest-js/funnel';
import type { WeatherData, WeatherTolerances } from './model';

/** One row of the all-ages table. */
export interface AgeRow {
  age: number;
  /** Library status; null when the age has no data. */
  status: StatusCode | null;
  /** Verdict; null when the age has no data. */
  pass: boolean | null;
  /** Hours in the window (after leaving out future hours). */
  total: number;
  /** Hours left out because either series has no value. */
  missing: number;
  pointsCompared: number;
  pointsOutside: number;
  fractionOfPointsOutside: number | null;
}

/** Aligned series and the comparison of one age. */
export interface AgeComparison {
  row: AgeRow;
  /** Present when the age was compared. */
  series?: { time: Float64Array; latest: Float64Array; forecast: Float64Array };
  result?: CompareResult;
}

/** The tolerances passed to `compare()`: both axes always explicit. */
export function toTolerances(tol: WeatherTolerances): Tolerances {
  return { atoly: tol.valueTol, atolx: tol.timeTolHours * 3600 };
}

/**
 * Compare one forecast age against the latest run. `nowSec` (epoch
 * seconds) leaves out hours later than now for live data, a safeguard
 * against a wrong visitor clock (a window reaching into the future compares
 * a forecast with itself).
 */
export function compareAge(
  data: WeatherData,
  age: number,
  tol: WeatherTolerances,
  nowSec: number,
): AgeComparison {
  const forecastAll = data.ages.get(age);
  const keepFuture = data.source === 'sample';
  const t: number[] = [];
  const ref: number[] = [];
  const fc: number[] = [];
  let total = 0;
  for (let i = 0; i < data.time.length; i++) {
    if (!keepFuture && data.time[i] > nowSec) {
      continue;
    }
    total++;
    const r = data.latest[i];
    const f = forecastAll ? forecastAll[i] : Number.NaN;
    if (Number.isNaN(r) || Number.isNaN(f)) {
      continue;
    }
    t.push(data.time[i]);
    ref.push(r);
    fc.push(f);
  }
  const row: AgeRow = {
    age,
    status: null,
    pass: null,
    total,
    missing: total - t.length,
    pointsCompared: 0,
    pointsOutside: 0,
    fractionOfPointsOutside: null,
  };
  if (t.length < 2) {
    return { row };
  }
  const time = Float64Array.from(t);
  const latest = Float64Array.from(ref);
  const forecast = Float64Array.from(fc);
  const options = { tolerances: toTolerances(tol) };
  const result = compare(time, latest, time, forecast, options);
  const summary = summarize(result, time, options);
  row.status = result.status;
  row.pass = result.status === Status.Pass;
  row.pointsCompared = summary.pointsCompared;
  row.pointsOutside = summary.pointsOutside;
  row.fractionOfPointsOutside = summary.fractionOfPointsOutside;
  return { row, series: { time, latest, forecast }, result };
}

/** Compare every forecast age present in `data`, in ascending order. */
export function compareAllAges(
  data: WeatherData,
  tol: WeatherTolerances,
  nowSec: number,
): AgeComparison[] {
  return [...data.ages.keys()]
    .sort((a, b) => a - b)
    .map((age) => compareAge(data, age, tol, nowSec));
}
