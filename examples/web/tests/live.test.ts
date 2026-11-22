import { describe, expect, it } from 'vitest';
import {
  WeatherController,
  type WeatherState,
} from '../src/weather/controller';
import { createLiveClient } from '../src/weather/live';
import type { Place } from '../src/weather/model';
import { loadSample } from '../src/weather/sample';
import { allAges, fakeFetch, forecastBody, hours, json } from './helpers';

const NOW = new Date('2026-11-22T10:00:00Z');
const STOCKHOLM: Place = {
  id: 2673730,
  name: 'Stockholm',
  admin1: 'Stockholm County',
  country: 'Sweden',
  latitude: 59.32938,
  longitude: 18.06871,
};
const OSLO: Place = {
  id: 3143244,
  name: 'Oslo',
  country: 'Norway',
  latitude: 59.91273,
  longitude: 10.74609,
};

function answer(url: string): Response {
  if (url.startsWith('https://geocoding-api.open-meteo.com/')) {
    return json({ results: [{ ...STOCKHOLM }], generationtime_ms: 0.1 });
  }
  const variable = /hourly=([a-z0-9_]+?),/.exec(url)?.[1] ?? 'temperature_2m';
  const t = hours(Date.UTC(2026, 10, 8) / 1000, 336);
  const v = t.map((_, i) => i % 24);
  return json(
    forecastBody(
      variable,
      t,
      allAges(variable, () => v, v),
    ),
  );
}

describe('live client', () => {
  it('sends one forecast request per place and variable', async () => {
    const { fetch, calls } = fakeFetch(answer);
    const client = createLiveClient({ fetch, now: () => NOW });
    const a = await client.loadForecast(STOCKHOLM, 'temperature_2m');
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain('hourly=temperature_2m,');
    expect(calls[0].url).toContain('start_date=2026-11-08&end_date=2026-11-21');
    expect(a.place).toBe('Stockholm, Stockholm County, Sweden');
    expect([...a.ages.keys()]).toEqual([1, 2, 3, 4, 5, 6, 7]);
    // Re-pick: cache hit.
    await client.loadForecast(OSLO, 'temperature_2m');
    expect(await client.loadForecast(STOCKHOLM, 'temperature_2m')).toBe(a);
    expect(calls).toHaveLength(2);
    // Another variable is another request.
    await client.loadForecast(STOCKHOLM, 'precipitation');
    expect(calls).toHaveLength(3);
    for (const c of calls) {
      expect(
        c.url.startsWith('https://previous-runs-api.open-meteo.com/'),
      ).toBe(true);
    }
  });

  it('shares concurrent identical requests', async () => {
    const { fetch, calls } = fakeFetch(answer);
    const client = createLiveClient({ fetch, now: () => NOW });
    const [a, b] = await Promise.all([
      client.loadForecast(STOCKHOLM, 'temperature_2m'),
      client.loadForecast(STOCKHOLM, 'temperature_2m'),
    ]);
    expect(a).toBe(b);
    expect(calls).toHaveLength(1);
  });

  it('caches searches by query and retries failures', async () => {
    let fail = true;
    const { fetch, calls } = fakeFetch((url) => {
      if (fail) {
        fail = false;
        return Promise.reject(new TypeError('offline'));
      }
      return answer(url);
    });
    const client = createLiveClient({ fetch, now: () => NOW });
    const signal = new AbortController().signal;
    await expect(client.searchPlaces('stockholm', signal)).rejects.toThrow(
      /Could not reach Open-Meteo/,
    );
    const places = await client.searchPlaces('stockholm', signal);
    expect(places[0].name).toBe('Stockholm');
    await client.searchPlaces('stockholm', signal);
    expect(calls).toHaveLength(2);
    expect(calls[1].url).toBe(
      'https://geocoding-api.open-meteo.com/v1/search?name=stockholm&count=8&language=en&format=json',
    );
  });
});

describe('weather controller', () => {
  function setUp(fetchAnswer: (url: string) => Promise<Response> | Response) {
    const { fetch, calls } = fakeFetch(fetchAnswer);
    const client = createLiveClient({ fetch, now: () => NOW });
    const states: WeatherState[] = [];
    const sample = loadSample();
    const controller = new WeatherController(
      sample,
      (p, v) => client.loadForecast(p, v),
      (s) => states.push(s),
    );
    return { controller, calls, states, sample };
  }

  it('starts on the sample and shows a picked place', async () => {
    const { controller, calls, states, sample } = setUp(answer);
    expect(controller.state.data).toBe(sample);
    expect(calls).toHaveLength(0);
    const done = controller.pick(STOCKHOLM, 'temperature_2m');
    expect(controller.state.loading?.place).toBe(STOCKHOLM);
    await done;
    expect(controller.state.place).toBe(STOCKHOLM);
    expect(controller.state.data.source).toBe('live');
    expect(controller.state.loading).toBeNull();
    expect(states.length).toBe(2);
    controller.showSample();
    expect(controller.state.data).toBe(sample);
    expect(controller.state.place).toBeUndefined();
    // Picking Stockholm again uses the cache.
    await controller.pick(STOCKHOLM, 'temperature_2m');
    expect(calls).toHaveLength(1);
  });

  it('keeps earlier results, marked stale, when a load fails', async () => {
    let status = 200;
    const { controller } = setUp((url) =>
      status === 200 ? answer(url) : json({}, status, { 'retry-after': '30' }),
    );
    await controller.pick(STOCKHOLM, 'temperature_2m');
    const shown = controller.state.data;
    status = 429;
    await controller.pick(OSLO, 'temperature_2m');
    expect(controller.state.data).toBe(shown);
    expect(controller.state.place).toBe(STOCKHOLM);
    expect(controller.state.stale).toBe(true);
    expect(controller.state.error).toBe(
      "Open-Meteo's rate limit was reached; try again in 30 s.",
    );
    // Not cached: trying again requests again and clears the error.
    status = 200;
    await controller.pick(OSLO, 'temperature_2m');
    expect(controller.state.place).toBe(OSLO);
    expect(controller.state.stale).toBe(false);
    expect(controller.state.error).toBeNull();
  });

  it('ignores the answer of a superseded pick', async () => {
    const { controller } = setUp(answer);
    const first = controller.pick(STOCKHOLM, 'temperature_2m');
    const second = controller.pick(OSLO, 'temperature_2m');
    await Promise.all([first, second]);
    expect(controller.state.place).toBe(OSLO);
  });

  it('does nothing without live data', async () => {
    const sample = loadSample();
    const controller = new WeatherController(sample, null, () => {});
    await controller.pick(STOCKHOLM, 'temperature_2m');
    expect(controller.state.data).toBe(sample);
  });
});
