// Open-Meteo client: URL building, fetching with error mapping, and JSON
// parsing. `fetch` is always injected so tests never touch the network.
// Only imported when live weather data is enabled at build time.

import { WeatherError } from './errors';
import {
  ALL_AGES,
  MODEL,
  type Place,
  type VariableId,
  type WeatherData,
} from './model';

export { WeatherError, type WeatherErrorKind } from './errors';

/** Geocoding API origin. */
export const GEOCODING_ORIGIN = 'https://geocoding-api.open-meteo.com';
/** Previous Runs API origin. */
export const PREVIOUS_RUNS_ORIGIN = 'https://previous-runs-api.open-meteo.com';

/** Maximum number of places a search lists. */
export const SEARCH_COUNT = 8;
/** Days in the comparison window. */
export const WINDOW_DAYS = 14;
/** Time after which a request is given up. */
export const TIMEOUT_MS = 15_000;

/** The `fetch` signature the client needs. */
export type FetchLike = (
  input: string,
  init?: RequestInit,
) => Promise<Response>;

const OFFLINE_MESSAGE =
  'Could not reach Open-Meteo. Check your connection; the sample still works.';

/** Geocoding search URL for a (normalised) place name. */
export function geocodingUrl(name: string): string {
  const params = new URLSearchParams({
    name,
    count: String(SEARCH_COUNT),
    language: 'en',
    format: 'json',
  });
  return `${GEOCODING_ORIGIN}/v1/search?${params}`;
}

/** A date window in UTC, both ends inclusive (YYYY-MM-DD). */
export interface DateWindow {
  start: string;
  end: string;
}

function isoDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/**
 * The last {@link WINDOW_DAYS} full days in UTC: ends yesterday, so every
 * valid time is in the past and every forecast age has had its run.
 */
export function forecastWindow(now: Date): DateWindow {
  const today = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
  );
  const day = 86_400_000;
  return {
    start: isoDate(today - WINDOW_DAYS * day),
    end: isoDate(today - day),
  };
}

function round4(v: number): string {
  // Drops trailing zeros; avoids "-0".
  const r = Math.round(v * 1e4) / 1e4;
  return String(r === 0 ? 0 : r);
}

/** Hourly column names requested for a variable: latest run, then ages. */
export function forecastColumns(variable: VariableId): string[] {
  return [variable, ...ALL_AGES.map((a) => `${variable}_previous_day${a}`)];
}

/** Previous Runs URL for one place, variable and window (all ages). */
export function forecastUrl(
  latitude: number,
  longitude: number,
  variable: VariableId,
  window: DateWindow,
): string {
  // Commas in `hourly` are kept literal, as in Open-Meteo's documentation.
  const query = [
    `latitude=${round4(latitude)}`,
    `longitude=${round4(longitude)}`,
    `hourly=${forecastColumns(variable).join(',')}`,
    `models=${MODEL}`,
    `start_date=${window.start}`,
    `end_date=${window.end}`,
    'timeformat=unixtime',
  ].join('&');
  return `${PREVIOUS_RUNS_ORIGIN}/v1/forecast?${query}`;
}

function malformed(): WeatherError {
  return new WeatherError('malformed', 'Unexpected answer from Open-Meteo');
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Places from a geocoding answer; a missing `results` key means none. */
export function parsePlaces(json: unknown): Place[] {
  if (!isRecord(json)) {
    throw malformed();
  }
  const results = json.results;
  if (results === undefined) {
    return [];
  }
  if (!Array.isArray(results)) {
    throw malformed();
  }
  const places: Place[] = [];
  for (const r of results) {
    if (
      !isRecord(r) ||
      typeof r.name !== 'string' ||
      typeof r.latitude !== 'number' ||
      typeof r.longitude !== 'number'
    ) {
      throw malformed();
    }
    places.push({
      id: typeof r.id === 'number' ? r.id : places.length,
      name: r.name,
      admin1: typeof r.admin1 === 'string' ? r.admin1 : undefined,
      country: typeof r.country === 'string' ? r.country : undefined,
      latitude: r.latitude,
      longitude: r.longitude,
    });
  }
  return places;
}

function numberSeries(v: unknown, length: number): Float64Array {
  if (!Array.isArray(v) || v.length !== length) {
    throw malformed();
  }
  const out = new Float64Array(length);
  v.forEach((x, i) => {
    if (x === null) {
      out[i] = Number.NaN;
    } else if (typeof x === 'number') {
      out[i] = x;
    } else {
      throw malformed();
    }
  });
  return out;
}

/** A Previous Runs answer as {@link WeatherData}; checks the expected keys. */
export function parseForecast(
  json: unknown,
  variable: VariableId,
  place: string,
): WeatherData {
  if (!isRecord(json) || !isRecord(json.hourly)) {
    throw malformed();
  }
  const hourly = json.hourly;
  if (!Array.isArray(hourly.time) || hourly.time.length === 0) {
    throw malformed();
  }
  const n = hourly.time.length;
  const time = numberSeries(hourly.time, n);
  if (time.some((t) => Number.isNaN(t))) {
    throw malformed();
  }
  const latest = numberSeries(hourly[variable], n);
  const ages = new Map<number, Float64Array>();
  for (const age of ALL_AGES) {
    ages.set(age, numberSeries(hourly[`${variable}_previous_day${age}`], n));
  }
  const units = isRecord(json.hourly_units) ? json.hourly_units : {};
  const unit = typeof units[variable] === 'string' ? units[variable] : '';
  return { place, variable, unit, time, latest, ages, source: 'live' };
}

/** Options of {@link fetchJson}. */
export interface FetchJsonOptions {
  fetch: FetchLike;
  signal?: AbortSignal;
  timeoutMs?: number;
}

/** The request options every Open-Meteo request uses (no custom headers). */
export const REQUEST_INIT: Readonly<RequestInit> = {
  credentials: 'omit',
  referrerPolicy: 'no-referrer',
  cache: 'default',
};

async function errorFor(res: Response): Promise<WeatherError> {
  if (res.status === 429) {
    const retry = Number.parseInt(res.headers.get('retry-after') ?? '', 10);
    const when =
      Number.isFinite(retry) && retry >= 0 ? `in ${retry} s` : 'in a minute';
    return new WeatherError(
      'rate-limit',
      `Open-Meteo's rate limit was reached; try again ${when}.`,
    );
  }
  if (res.status === 400) {
    let reason = '';
    try {
      const body: unknown = await res.json();
      if (isRecord(body) && typeof body.reason === 'string') {
        reason = body.reason;
      }
    } catch {
      // No readable reason; fall through.
    }
    if (reason) {
      return new WeatherError(
        'bad-request',
        `Open-Meteo refused the request: ${reason}`,
      );
    }
  }
  return new WeatherError('http', `Open-Meteo answered ${res.status}`);
}

/**
 * GET a JSON document with the request hygiene of design §9 and the error
 * mapping of design §10. Rejects with a {@link WeatherError}.
 */
export async function fetchJson(
  url: string,
  options: FetchJsonOptions,
): Promise<unknown> {
  const { signal } = options;
  if (signal?.aborted) {
    throw new WeatherError('aborted', 'Request cancelled');
  }
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, options.timeoutMs ?? TIMEOUT_MS);
  const onAbort = (): void => controller.abort();
  signal?.addEventListener('abort', onAbort);
  try {
    let res: Response;
    try {
      res = await options.fetch(url, {
        ...REQUEST_INIT,
        signal: controller.signal,
      });
    } catch {
      if (timedOut) {
        throw new WeatherError('timeout', OFFLINE_MESSAGE);
      }
      if (signal?.aborted) {
        throw new WeatherError('aborted', 'Request cancelled');
      }
      throw new WeatherError('offline', OFFLINE_MESSAGE);
    }
    if (!res.ok) {
      throw await errorFor(res);
    }
    try {
      return (await res.json()) as unknown;
    } catch {
      if (timedOut) {
        throw new WeatherError('timeout', OFFLINE_MESSAGE);
      }
      if (signal?.aborted) {
        throw new WeatherError('aborted', 'Request cancelled');
      }
      throw malformed();
    }
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onAbort);
  }
}
