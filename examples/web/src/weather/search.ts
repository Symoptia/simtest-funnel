// Debounced place search: runs a search 300 ms after the last keystroke
// (or at once on Enter) for inputs of at least two characters, aborts a
// search still in flight when a newer one starts, and reports only the
// newest answer. DOM-free so it can be tested with fake timers.

import { normaliseQuery, WeatherError } from './errors';
import type { Place } from './model';

/** Minimum trimmed input length that reaches the API. */
export const MIN_QUERY_LENGTH = 2;
/** Pause after the last keystroke before searching. */
export const SEARCH_DELAY_MS = 300;

/** What the result list shows. */
export type SearchState =
  | { kind: 'idle' }
  | { kind: 'loading'; query: string }
  | { kind: 'results'; query: string; places: Place[] }
  | { kind: 'error'; query: string; message: string };

/** Options of {@link createPlaceSearch}. */
export interface PlaceSearchOptions {
  /** Run one search; must honour `signal`. */
  search: (query: string, signal: AbortSignal) => Promise<Place[]>;
  onState: (state: SearchState) => void;
  delayMs?: number;
}

/** A debounced place search bound to one input. */
export interface PlaceSearch {
  /** The input text changed (debounced). */
  input(text: string): void;
  /** Enter pressed: search at once. */
  submit(text: string): void;
  /** Stop pending and in-flight searches. */
  cancel(): void;
}

/** Create a {@link PlaceSearch}. */
export function createPlaceSearch(options: PlaceSearchOptions): PlaceSearch {
  const delay = options.delayMs ?? SEARCH_DELAY_MS;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inflight: AbortController | undefined;
  let lastQuery: string | undefined;

  const clearTimer = (): void => {
    if (timer !== undefined) {
      clearTimeout(timer);
      timer = undefined;
    }
  };

  const abortInflight = (): void => {
    inflight?.abort();
    inflight = undefined;
  };

  const run = (text: string): void => {
    clearTimer();
    const shown = text.trim();
    const query = normaliseQuery(text);
    if (query.length < MIN_QUERY_LENGTH) {
      abortInflight();
      lastQuery = undefined;
      options.onState({ kind: 'idle' });
      return;
    }
    if (query === lastQuery && inflight) {
      return;
    }
    abortInflight();
    lastQuery = query;
    const controller = new AbortController();
    inflight = controller;
    options.onState({ kind: 'loading', query: shown });
    options.search(query, controller.signal).then(
      (places) => {
        if (inflight !== controller) {
          return;
        }
        inflight = undefined;
        options.onState({ kind: 'results', query: shown, places });
      },
      (err: unknown) => {
        if (inflight !== controller) {
          return;
        }
        inflight = undefined;
        lastQuery = undefined;
        if (err instanceof WeatherError && err.kind === 'aborted') {
          return;
        }
        const message =
          err instanceof WeatherError
            ? err.message
            : 'Unexpected answer from Open-Meteo';
        options.onState({ kind: 'error', query: shown, message });
      },
    );
  };

  return {
    input(text) {
      clearTimer();
      if (normaliseQuery(text).length < MIN_QUERY_LENGTH) {
        run(text);
        return;
      }
      timer = setTimeout(() => run(text), delay);
    },
    submit(text) {
      run(text);
    },
    cancel() {
      clearTimer();
      abortInflight();
      lastQuery = undefined;
    },
  };
}
