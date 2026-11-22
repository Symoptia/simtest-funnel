// Fake fetch for the Open-Meteo client tests.

import type { FetchLike } from '../src/weather/openmeteo';

/** A recorded request. */
export interface Call {
  url: string;
  init: RequestInit | undefined;
}

/** A fake fetch answering from `answer` and recording every call. */
export function fakeFetch(
  answer: (url: string, init?: RequestInit) => Promise<Response> | Response,
): { fetch: FetchLike; calls: Call[] } {
  const calls: Call[] = [];
  return {
    calls,
    fetch: async (url, init) => {
      calls.push({ url, init });
      return answer(url, init);
    },
  };
}

/** A JSON response. */
export function json(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  });
}

/** Hourly epoch seconds starting at `start`. */
export function hours(start: number, n: number): number[] {
  return Array.from({ length: n }, (_, i) => start + i * 3600);
}

/** A Previous Runs answer for `variable` with the given columns. */
export function forecastBody(
  variable: string,
  time: number[],
  columns: Record<string, (number | null)[]>,
  unit = '°C',
): unknown {
  const hourly: Record<string, (number | null)[]> = { time };
  const hourlyUnits: Record<string, string> = { time: 'unixtime' };
  for (const [k, v] of Object.entries(columns)) {
    hourly[k] = v;
    hourlyUnits[k] = unit;
  }
  return {
    latitude: 59.36731,
    longitude: 18.0,
    generationtime_ms: 0.07,
    utc_offset_seconds: 0,
    timezone: 'GMT',
    timezone_abbreviation: 'GMT',
    elevation: 24.0,
    hourly_units: hourlyUnits,
    hourly,
    variable,
  };
}

/** All seven age columns of `variable`, filled by `fill(age)`. */
export function allAges(
  variable: string,
  fill: (age: number) => (number | null)[],
  latest: (number | null)[],
): Record<string, (number | null)[]> {
  const cols: Record<string, (number | null)[]> = { [variable]: latest };
  for (let a = 1; a <= 7; a++) {
    cols[`${variable}_previous_day${a}`] = fill(a);
  }
  return cols;
}
