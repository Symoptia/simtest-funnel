import { describe, expect, it } from 'vitest';
import { createCache } from '../src/weather/cache';

describe('request cache', () => {
  it('loads a key once', async () => {
    const cache = createCache<number>();
    let loads = 0;
    const load = async (): Promise<number> => ++loads;
    expect(await cache.get('a', load)).toBe(1);
    expect(await cache.get('a', load)).toBe(1);
    expect(loads).toBe(1);
    expect(await cache.get('b', load)).toBe(2);
  });

  it('shares an in-flight request', async () => {
    const cache = createCache<string>();
    let loads = 0;
    let resolve: (v: string) => void = () => {};
    const load = (): Promise<string> => {
      loads++;
      return new Promise((r) => {
        resolve = r;
      });
    };
    const a = cache.get('k', load);
    const b = cache.get('k', load);
    resolve('done');
    expect(await Promise.all([a, b])).toEqual(['done', 'done']);
    expect(loads).toBe(1);
  });

  it('does not keep failures', async () => {
    const cache = createCache<string>();
    let loads = 0;
    const load = async (): Promise<string> => {
      loads++;
      if (loads === 1) {
        throw new Error('offline');
      }
      return 'ok';
    };
    await expect(cache.get('k', load)).rejects.toThrow('offline');
    expect(cache.has('k')).toBe(false);
    expect(await cache.get('k', load)).toBe('ok');
    expect(loads).toBe(2);
  });
});
