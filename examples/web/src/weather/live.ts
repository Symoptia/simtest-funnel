// Live Open-Meteo access for the weather part: place search and forecast
// loading through in-memory caches. Imported only when live weather data is
// enabled at build time (VITE_WEATHER_LIVE), so a sample-only build carries
// no Open-Meteo URL.

import { createCache } from './cache';
import {
  type Place,
  placeLabel,
  type VariableId,
  type WeatherData,
} from './model';
import {
  type FetchLike,
  fetchJson,
  forecastUrl,
  forecastWindow,
  geocodingUrl,
  parseForecast,
  parsePlaces,
} from './openmeteo';

/** Search and load operations used by the weather UI. */
export interface LiveClient {
  /** Places matching a normalised query (cached per query). */
  searchPlaces(query: string, signal: AbortSignal): Promise<Place[]>;
  /** All forecast ages of one variable for a place (cached per URL). */
  loadForecast(place: Place, variable: VariableId): Promise<WeatherData>;
}

/** Options of {@link createLiveClient}. */
export interface LiveClientOptions {
  fetch: FetchLike;
  /** Clock for the date window; defaults to the current time. */
  now?: () => Date;
}

/** Create a {@link LiveClient} with its own caches. */
export function createLiveClient(options: LiveClientOptions): LiveClient {
  const places = createCache<Place[]>();
  const forecasts = createCache<WeatherData>();
  const now = options.now ?? (() => new Date());
  return {
    searchPlaces(query, signal) {
      const url = geocodingUrl(query);
      return places.get(url, async () =>
        parsePlaces(await fetchJson(url, { fetch: options.fetch, signal })),
      );
    },
    loadForecast(place, variable) {
      const url = forecastUrl(
        place.latitude,
        place.longitude,
        variable,
        forecastWindow(now()),
      );
      return forecasts.get(url, async () =>
        parseForecast(
          await fetchJson(url, { fetch: options.fetch }),
          variable,
          placeLabel(place),
        ),
      );
    },
  };
}

/** The browser's `fetch`, bound so it can be called detached. */
export function browserFetch(): FetchLike {
  return (input, init) => globalThis.fetch(input, init);
}
