// In-memory cache for the page's lifetime: keyed by request URL, holding the
// parsed answer or the in-flight promise (so two quick identical requests
// share one fetch). Failures are evicted so a retry requests again. Nothing
// is written to browser storage.

/** A promise cache keyed by string. */
export interface RequestCache<T> {
  /** The cached value for `key`, or the result of `load()` (then cached). */
  get(key: string, load: () => Promise<T>): Promise<T>;
  /** Whether `key` holds a value or an in-flight request. */
  has(key: string): boolean;
}

/** Create an empty {@link RequestCache}. */
export function createCache<T>(): RequestCache<T> {
  const entries = new Map<string, Promise<T>>();
  return {
    get(key, load) {
      const hit = entries.get(key);
      if (hit) {
        return hit;
      }
      const pending = load();
      entries.set(key, pending);
      pending.catch(() => {
        if (entries.get(key) === pending) {
          entries.delete(key);
        }
      });
      return pending;
    },
    has(key) {
      return entries.has(key);
    },
  };
}
