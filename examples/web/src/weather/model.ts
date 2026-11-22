// Shared types and the variable table of the weather part.

/** Open-Meteo variable names offered by the demo. */
export type VariableId = 'temperature_2m' | 'precipitation' | 'wind_speed_10m';

/** One weather variable with its unit and tolerance presets. */
export interface Variable {
  id: VariableId;
  label: string;
  /** Open-Meteo's default unit for the variable. */
  unit: string;
  /** Preset value tolerance (± in `unit`). */
  valueTol: number;
  /** Preset time tolerance (± hours). */
  timeTolHours: number;
  /** Step of the value-tolerance input. */
  step: number;
}

/** The variables offered, in display order (design §3). */
export const VARIABLES: readonly Variable[] = [
  {
    id: 'temperature_2m',
    label: 'Temperature (2 m)',
    unit: '°C',
    valueTol: 2,
    timeTolHours: 3,
    step: 0.5,
  },
  {
    id: 'precipitation',
    label: 'Precipitation',
    unit: 'mm',
    valueTol: 1,
    timeTolHours: 3,
    step: 0.1,
  },
  {
    id: 'wind_speed_10m',
    label: 'Wind speed (10 m)',
    unit: 'km/h',
    valueTol: 10,
    timeTolHours: 3,
    step: 1,
  },
];

/** Forecast ages the Previous Runs API provides (days ahead). */
export const ALL_AGES: readonly number[] = [1, 2, 3, 4, 5, 6, 7];

/** The weather model all data comes from. */
export const MODEL = 'ecmwf_ifs';

/** Look up a variable by its Open-Meteo name. */
export function variableById(id: string): Variable | undefined {
  return VARIABLES.find((v) => v.id === id);
}

/** A place found by the geocoding search. */
export interface Place {
  id: number;
  name: string;
  admin1?: string;
  country?: string;
  latitude: number;
  longitude: number;
}

/** "Stockholm, Stockholm County, Sweden" (missing parts left out). */
export function placeLabel(place: Place): string {
  return [place.name, place.admin1, place.country]
    .filter((p): p is string => Boolean(p))
    .join(', ');
}

/** Tolerances chosen in the UI. */
export interface WeatherTolerances {
  /** ± value in the variable's unit. */
  valueTol: number;
  /** ± hours. */
  timeTolHours: number;
}

/**
 * Hourly data of one variable for one place: the latest run and the
 * forecasts made N days ahead, on one shared time axis. Missing values are
 * NaN.
 */
export interface WeatherData {
  /** Display name of the place. */
  place: string;
  variable: VariableId;
  unit: string;
  /** Epoch seconds (UTC), strictly increasing. */
  time: Float64Array;
  /** Latest run (the reference). */
  latest: Float64Array;
  /** Forecast age in days -> forecast series (the test). */
  ages: Map<number, Float64Array>;
  source: 'sample' | 'live';
  /** Retrieval date of a bundled sample (YYYY-MM-DD). */
  retrieved?: string;
}
