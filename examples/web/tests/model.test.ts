import { describe, expect, it } from 'vitest';
import {
  ALL_AGES,
  MODEL,
  placeLabel,
  VARIABLES,
  variableById,
} from '../src/weather/model';

describe('variable table', () => {
  it('offers temperature, precipitation and wind speed with their presets', () => {
    expect(
      VARIABLES.map((v) => [v.id, v.unit, v.valueTol, v.timeTolHours]),
    ).toEqual([
      ['temperature_2m', '°C', 2, 3],
      ['precipitation', 'mm', 1, 3],
      ['wind_speed_10m', 'km/h', 10, 3],
    ]);
    for (const v of VARIABLES) {
      expect(v.step).toBeGreaterThan(0);
    }
  });

  it('looks variables up by name', () => {
    expect(variableById('precipitation')?.label).toBe('Precipitation');
    expect(variableById('pressure_msl')).toBeUndefined();
  });

  it('pins the model and the seven ages', () => {
    expect(MODEL).toBe('ecmwf_ifs');
    expect(ALL_AGES).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });
});

describe('placeLabel', () => {
  it('joins name, region and country and leaves out missing parts', () => {
    const base = { id: 1, name: 'Stockholm', latitude: 0, longitude: 0 };
    expect(
      placeLabel({ ...base, admin1: 'Stockholm County', country: 'Sweden' }),
    ).toBe('Stockholm, Stockholm County, Sweden');
    expect(placeLabel({ ...base, country: 'Sweden' })).toBe(
      'Stockholm, Sweden',
    );
    expect(placeLabel(base)).toBe('Stockholm');
  });
});
