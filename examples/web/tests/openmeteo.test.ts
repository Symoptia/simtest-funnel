import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  fetchJson,
  forecastUrl,
  forecastWindow,
  geocodingUrl,
  parseForecast,
  parsePlaces,
  REQUEST_INIT,
  WeatherError,
} from '../src/weather/openmeteo';
import { allAges, fakeFetch, forecastBody, hours, json } from './helpers';

describe('URLs', () => {
  it('builds the geocoding search URL', () => {
    expect(geocodingUrl('stockholm')).toBe(
      'https://geocoding-api.open-meteo.com/v1/search?name=stockholm&count=8&language=en&format=json',
    );
    expect(geocodingUrl('new york')).toBe(
      'https://geocoding-api.open-meteo.com/v1/search?name=new+york&count=8&language=en&format=json',
    );
  });

  it('uses the last 14 full days in UTC, ending yesterday', () => {
    expect(forecastWindow(new Date('2026-11-22T10:00:00Z'))).toEqual({
      start: '2026-11-08',
      end: '2026-11-21',
    });
    // Just after midnight UTC, whatever the local zone says.
    expect(forecastWindow(new Date('2026-11-22T00:00:01Z'))).toEqual({
      start: '2026-11-08',
      end: '2026-11-21',
    });
    expect(forecastWindow(new Date('2026-11-21T23:59:59Z'))).toEqual({
      start: '2026-11-07',
      end: '2026-11-20',
    });
  });

  it('crosses month and year boundaries', () => {
    expect(forecastWindow(new Date('2026-03-05T12:00:00Z'))).toEqual({
      start: '2026-02-19',
      end: '2026-03-04',
    });
    expect(forecastWindow(new Date('2027-01-01T08:00:00Z'))).toEqual({
      start: '2026-12-18',
      end: '2026-12-31',
    });
  });

  it('builds one Previous Runs URL for all seven ages', () => {
    const window = forecastWindow(new Date('2026-11-22T10:00:00Z'));
    expect(forecastUrl(59.32938, 18.06871, 'temperature_2m', window)).toBe(
      'https://previous-runs-api.open-meteo.com/v1/forecast?latitude=59.3294&longitude=18.0687' +
        '&hourly=temperature_2m,temperature_2m_previous_day1,temperature_2m_previous_day2,' +
        'temperature_2m_previous_day3,temperature_2m_previous_day4,temperature_2m_previous_day5,' +
        'temperature_2m_previous_day6,temperature_2m_previous_day7' +
        '&models=ecmwf_ifs&start_date=2026-11-08&end_date=2026-11-21&timeformat=unixtime',
    );
  });

  it('rounds coordinates to 4 decimals without noise', () => {
    const w = { start: '2026-11-08', end: '2026-11-21' };
    const url = forecastUrl(-33.86787, 151.20732, 'precipitation', w);
    expect(url).toContain('latitude=-33.8679&longitude=151.2073&');
    expect(url).toContain('hourly=precipitation,precipitation_previous_day1,');
    expect(forecastUrl(0.00001, -0.00001, 'precipitation', w)).toContain(
      'latitude=0&longitude=0&',
    );
  });
});

describe('parsePlaces', () => {
  it('reads results with optional region and country', () => {
    const places = parsePlaces({
      results: [
        {
          id: 2673730,
          name: 'Stockholm',
          latitude: 59.32938,
          longitude: 18.06871,
          country_code: 'SE',
          country: 'Sweden',
          admin1: 'Stockholm County',
        },
        { id: 7, name: 'Stockholm', latitude: 47.0, longitude: -68.1 },
      ],
      generationtime_ms: 0.09,
    });
    expect(places).toEqual([
      {
        id: 2673730,
        name: 'Stockholm',
        admin1: 'Stockholm County',
        country: 'Sweden',
        latitude: 59.32938,
        longitude: 18.06871,
      },
      {
        id: 7,
        name: 'Stockholm',
        admin1: undefined,
        country: undefined,
        latitude: 47.0,
        longitude: -68.1,
      },
    ]);
  });

  it('treats a missing results key as no place', () => {
    expect(parsePlaces({ generationtime_ms: 0.1 })).toEqual([]);
  });

  it('rejects malformed answers', () => {
    expect(() => parsePlaces([])).toThrow('Unexpected answer from Open-Meteo');
    expect(() => parsePlaces({ results: [{ name: 'x' }] })).toThrow(
      WeatherError,
    );
  });
});

describe('parseForecast', () => {
  const time = hours(1794960000, 4);

  it('reads time, latest run, seven ages and the unit', () => {
    const body = forecastBody(
      'temperature_2m',
      time,
      allAges('temperature_2m', (a) => [a, a, a, a], [1, 2, 3, 4]),
    );
    const d = parseForecast(body, 'temperature_2m', 'Stockholm, Sweden');
    expect(d.source).toBe('live');
    expect(d.unit).toBe('°C');
    expect(d.place).toBe('Stockholm, Sweden');
    expect([...d.time]).toEqual(time);
    expect([...d.latest]).toEqual([1, 2, 3, 4]);
    expect([...d.ages.keys()]).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect([...(d.ages.get(5) ?? [])]).toEqual([5, 5, 5, 5]);
  });

  it('turns null into NaN, including an all-null age', () => {
    const body = forecastBody(
      'temperature_2m',
      time,
      allAges(
        'temperature_2m',
        (a) => (a === 7 ? [null, null, null, null] : [1, null, 3, 4]),
        [1, 2, null, 4],
      ),
    );
    const d = parseForecast(body, 'temperature_2m', 'x');
    expect(Number.isNaN(d.latest[2])).toBe(true);
    expect(Number.isNaN(d.ages.get(3)?.[1] ?? 0)).toBe(true);
    expect([...(d.ages.get(7) ?? [])].every(Number.isNaN)).toBe(true);
  });

  it('says "unexpected answer" when keys are missing or wrong', () => {
    const cols = allAges('temperature_2m', () => [1, 1, 1, 1], [1, 1, 1, 1]);
    const { temperature_2m_previous_day4: _, ...without4 } = cols;
    const cases: unknown[] = [
      null,
      { hourly: null },
      forecastBody('temperature_2m', [], {}),
      forecastBody('temperature_2m', time, without4),
      forecastBody('temperature_2m', time, { ...cols, temperature_2m: [1] }),
      forecastBody('temperature_2m', time, {
        ...cols,
        temperature_2m: ['a', 1, 1, 1] as unknown as number[],
      }),
    ];
    for (const body of cases) {
      expect(() => parseForecast(body, 'temperature_2m', 'x')).toThrow(
        'Unexpected answer from Open-Meteo',
      );
    }
  });
});

describe('fetchJson', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  const url = 'https://previous-runs-api.open-meteo.com/v1/forecast?x=1';

  async function failure(
    answer: Parameters<typeof fakeFetch>[0],
  ): Promise<WeatherError> {
    const { fetch } = fakeFetch(answer);
    try {
      await fetchJson(url, { fetch });
    } catch (err) {
      expect(err).toBeInstanceOf(WeatherError);
      return err as WeatherError;
    }
    throw new Error('expected a failure');
  }

  it('sends no credentials, no referrer and no custom headers', async () => {
    const { fetch, calls } = fakeFetch(() => json({ ok: 1 }));
    expect(await fetchJson(url, { fetch })).toEqual({ ok: 1 });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe(url);
    const { signal, ...rest } = calls[0].init ?? {};
    expect(rest).toEqual({
      credentials: 'omit',
      referrerPolicy: 'no-referrer',
      cache: 'default',
    });
    expect(REQUEST_INIT).toEqual(rest);
    expect(signal).toBeInstanceOf(AbortSignal);
  });

  it('maps a rejected fetch to "offline"', async () => {
    const err = await failure(() => Promise.reject(new TypeError('x')));
    expect(err.kind).toBe('offline');
    expect(err.message).toBe(
      'Could not reach Open-Meteo. Check your connection; the sample still works.',
    );
  });

  it('maps 429 with and without retry-after', async () => {
    const a = await failure(() => json({}, 429, { 'retry-after': '30' }));
    expect(a.kind).toBe('rate-limit');
    expect(a.message).toBe(
      "Open-Meteo's rate limit was reached; try again in 30 s.",
    );
    const b = await failure(() => json({}, 429));
    expect(b.message).toBe(
      "Open-Meteo's rate limit was reached; try again in a minute.",
    );
  });

  it('quotes the reason of a 400', async () => {
    const err = await failure(() =>
      json(
        {
          reason: 'End-date must be larger or equals than start-date',
          error: true,
        },
        400,
      ),
    );
    expect(err.kind).toBe('bad-request');
    expect(err.message).toBe(
      'Open-Meteo refused the request: End-date must be larger or equals than start-date',
    );
  });

  it('reports other statuses and a 400 without reason by number', async () => {
    expect((await failure(() => json({}, 500))).message).toBe(
      'Open-Meteo answered 500',
    );
    const err = await failure(() => new Response('nope', { status: 400 }));
    expect(err.kind).toBe('http');
    expect(err.message).toBe('Open-Meteo answered 400');
  });

  it('reports a body that is not JSON as unexpected', async () => {
    const err = await failure(() => new Response('<html>', { status: 200 }));
    expect(err.kind).toBe('malformed');
    expect(err.message).toBe('Unexpected answer from Open-Meteo');
  });

  it('gives up after the timeout', async () => {
    vi.useFakeTimers();
    const { fetch } = fakeFetch(
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          );
        }),
    );
    const pending = fetchJson(url, { fetch, timeoutMs: 15_000 }).catch(
      (e: unknown) => e,
    );
    await vi.advanceTimersByTimeAsync(14_999);
    await vi.advanceTimersByTimeAsync(1);
    const err = (await pending) as WeatherError;
    expect(err.kind).toBe('timeout');
    expect(err.message).toMatch(/Could not reach Open-Meteo/);
  });

  it('reports a cancelled request as aborted', async () => {
    const controller = new AbortController();
    const { fetch } = fakeFetch(
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          );
        }),
    );
    const pending = fetchJson(url, { fetch, signal: controller.signal }).catch(
      (e: unknown) => e,
    );
    controller.abort();
    expect(((await pending) as WeatherError).kind).toBe('aborted');
    const already = await fetchJson(url, {
      fetch,
      signal: controller.signal,
    }).catch((e: unknown) => e);
    expect((already as WeatherError).kind).toBe('aborted');
  });
});
