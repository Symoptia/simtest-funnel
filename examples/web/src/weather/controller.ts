// State of the weather part, DOM-free: which data is shown (the sample or a
// searched place), what is loading, and the last error. A failed load keeps
// the earlier data visible, marked as not current.

import type { Place, VariableId, WeatherData } from './model';

/** Loads all forecast ages of one variable for a place. */
export type ForecastLoader = (
  place: Place,
  variable: VariableId,
) => Promise<WeatherData>;

/** What the weather part shows. */
export interface WeatherState {
  /** Data on screen. */
  data: WeatherData;
  /** The searched place of `data`; undefined for the sample. */
  place?: Place;
  /** What is being loaded, for a status line. */
  loading: { place: Place; variable: VariableId } | null;
  /** Message of the last failed load, until the next success. */
  error: string | null;
  /** True when `data` is not what the visitor last asked for. */
  stale: boolean;
}

/** Holds {@link WeatherState} and tells the UI about every change. */
export class WeatherController {
  private current: WeatherState;
  private token = 0;
  private readonly sample: WeatherData;
  private readonly load: ForecastLoader | null;
  private readonly onChange: (state: WeatherState) => void;

  constructor(
    sample: WeatherData,
    load: ForecastLoader | null,
    onChange: (state: WeatherState) => void,
  ) {
    this.sample = sample;
    this.load = load;
    this.onChange = onChange;
    this.current = { data: sample, loading: null, error: null, stale: false };
  }

  /** The current state. */
  get state(): WeatherState {
    return this.current;
  }

  private set(next: WeatherState): void {
    this.current = next;
    this.onChange(next);
  }

  /** Show the bundled sample again. */
  showSample(): void {
    this.token++;
    this.set({ data: this.sample, loading: null, error: null, stale: false });
  }

  /** Load and show `variable` for `place`; resolves when done. */
  async pick(place: Place, variable: VariableId): Promise<void> {
    if (!this.load) {
      return;
    }
    const token = ++this.token;
    this.set({ ...this.current, loading: { place, variable } });
    try {
      const data = await this.load(place, variable);
      if (token !== this.token) {
        return;
      }
      this.set({ data, place, loading: null, error: null, stale: false });
    } catch (err) {
      if (token !== this.token) {
        return;
      }
      this.set({
        ...this.current,
        loading: null,
        error:
          err instanceof Error
            ? err.message
            : 'Unexpected answer from Open-Meteo',
        stale: true,
      });
    }
  }
}
