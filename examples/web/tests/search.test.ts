import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Place } from '../src/weather/model';
import { WeatherError } from '../src/weather/openmeteo';
import { createPlaceSearch, type SearchState } from '../src/weather/search';

const PLACE: Place = { id: 1, name: 'Stockholm', latitude: 59, longitude: 18 };

interface Pending {
  query: string;
  signal: AbortSignal;
  resolve: (p: Place[]) => void;
  reject: (e: unknown) => void;
}

function setUp(): {
  pending: Pending[];
  states: SearchState[];
  search: ReturnType<typeof createPlaceSearch>;
} {
  const pending: Pending[] = [];
  const states: SearchState[] = [];
  const search = createPlaceSearch({
    search: (query, signal) =>
      new Promise<Place[]>((resolve, reject) => {
        pending.push({ query, signal, resolve, reject });
        signal.addEventListener('abort', () =>
          reject(new WeatherError('aborted', 'Request cancelled')),
        );
      }),
    onState: (s) => states.push(s),
  });
  return { pending, states, search };
}

describe('place search', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('searches once, 300 ms after the last keystroke', async () => {
    const { pending, search } = setUp();
    for (const text of ['S', 'St', 'Sto', 'Stoc', 'Stock', 'Stockh']) {
      search.input(text);
      await vi.advanceTimersByTimeAsync(100);
    }
    expect(pending).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(199);
    expect(pending).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);
    expect(pending.map((p) => p.query)).toEqual(['stockh']);
  });

  it('searches at once on Enter', () => {
    const { pending, search } = setUp();
    search.input('Stockh');
    search.submit('Stockh');
    expect(pending.map((p) => p.query)).toEqual(['stockh']);
    vi.advanceTimersByTime(1000);
    expect(pending).toHaveLength(1);
  });

  it('never searches for fewer than 2 characters', async () => {
    const { pending, states, search } = setUp();
    search.input(' S ');
    search.submit('S');
    search.submit('   ');
    await vi.advanceTimersByTimeAsync(1000);
    expect(pending).toHaveLength(0);
    expect(states.every((s) => s.kind === 'idle')).toBe(true);
  });

  it('abandons an earlier search and shows only the newest answer', async () => {
    const { pending, states, search } = setUp();
    search.submit('Stock');
    search.submit('Stockholm');
    expect(pending).toHaveLength(2);
    expect(pending[0].signal.aborted).toBe(true);
    // A late answer for the first search is ignored.
    pending[0].resolve([{ ...PLACE, name: 'Old' }]);
    pending[1].resolve([PLACE]);
    await vi.advanceTimersByTimeAsync(0);
    const results = states.filter((s) => s.kind === 'results');
    expect(results).toEqual([
      { kind: 'results', query: 'Stockholm', places: [PLACE] },
    ]);
  });

  it('reports no results and errors', async () => {
    const { pending, states, search } = setUp();
    search.submit('Xqzzqx');
    pending[0].resolve([]);
    await vi.advanceTimersByTimeAsync(0);
    expect(states[states.length - 1]).toEqual({
      kind: 'results',
      query: 'Xqzzqx',
      places: [],
    });
    search.submit('Paris');
    pending[1].reject(new WeatherError('rate-limit', 'slow down'));
    await vi.advanceTimersByTimeAsync(0);
    expect(states[states.length - 1]).toEqual({
      kind: 'error',
      query: 'Paris',
      message: 'slow down',
    });
  });

  it('clears the list when the input becomes too short', async () => {
    const { pending, states, search } = setUp();
    search.submit('Paris');
    search.input('P');
    expect(pending[0].signal.aborted).toBe(true);
    expect(states[states.length - 1]).toEqual({ kind: 'idle' });
  });
});
