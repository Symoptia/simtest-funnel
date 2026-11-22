import { describe, expect, it } from 'vitest';
import type { AgeRow } from '../src/weather/compare';
import type { Place } from '../src/weather/model';
import {
  answerLine,
  attributionLines,
  formatDateRange,
  formatPercent,
  formatTolerances,
  placeDetails,
} from '../src/weather/text';

function text(lines: ReturnType<typeof attributionLines>): string {
  return lines.map((parts) => parts.map((p) => p.text).join('')).join('\n');
}

function hrefs(lines: ReturnType<typeof attributionLines>): string[] {
  return lines.flat().flatMap((p) => (p.href ? [p.href] : []));
}

const ROW: AgeRow = {
  age: 3,
  status: -1,
  pass: false,
  total: 360,
  missing: 0,
  pointsCompared: 360,
  pointsOutside: 14,
  fractionOfPointsOutside: 14 / 360,
};

describe('numbers and dates', () => {
  it('formats shares, tolerances and the UTC window', () => {
    expect(formatPercent(14 / 360)).toBe('3.9 %');
    expect(formatPercent(0)).toBe('0.0 %');
    expect(formatTolerances({ valueTol: 2, timeTolHours: 3 }, '°C')).toBe(
      '±2 °C and ±3 h',
    );
    expect(
      formatTolerances({ valueTol: 0.1 + 0.2, timeTolHours: 0 }, 'mm'),
    ).toBe('±0.3 mm and ±0 h');
    expect(formatDateRange(1793836800, 1793836800 + 359 * 3600)).toBe(
      '5 Nov – 19 Nov 2026',
    );
    expect(
      formatDateRange(
        Date.UTC(2026, 11, 25) / 1000,
        Date.UTC(2027, 0, 7) / 1000,
      ),
    ).toBe('25 Dec 2026 – 7 Jan 2027');
  });
});

describe('answerLine', () => {
  const tol = { valueTol: 2, timeTolHours: 3 };
  it('says how many hours were outside', () => {
    expect(answerLine(ROW, tol, '°C')).toBe(
      'The forecast made 3 days ahead did not stay within ±2 °C and ±3 h: 3.9 % of the hours (14 of 360 hours) were outside the tube.',
    );
  });
  it('says when the forecast stayed inside', () => {
    expect(
      answerLine(
        {
          ...ROW,
          age: 1,
          status: 0,
          pass: true,
          pointsOutside: 0,
          fractionOfPointsOutside: 0,
        },
        tol,
        '°C',
      ),
    ).toBe(
      'The forecast made 1 day ahead stayed within ±2 °C and ±3 h for all 360 hours.',
    );
  });
  it('says when there is no data', () => {
    expect(
      answerLine({ ...ROW, age: 7, status: null, pass: null }, tol, '°C'),
    ).toBe('The forecast made 7 days ahead: no forecast data for this window.');
  });
});

describe('attribution', () => {
  it('credits Open-Meteo, the licence, ECMWF and the sample date', () => {
    const lines = attributionLines({
      live: true,
      sampleRetrieved: '2026-11-22',
    });
    const all = text(lines);
    expect(all).toContain('Weather data by Open-Meteo.com');
    expect(all).toContain('CC BY 4.0');
    expect(all).toContain('ECMWF IFS');
    expect(all).toContain('Location data based on GeoNames');
    expect(all).toContain('retrieved 2026-11-22');
    expect(all).toContain('not station measurements');
    expect(all).toContain(
      "Open-Meteo's free API, which is for non-commercial use",
    );
    expect(hrefs(lines)).toEqual(
      expect.arrayContaining([
        'https://open-meteo.com/',
        'https://creativecommons.org/licenses/by/4.0/',
        'https://www.geonames.org/',
        'https://open-meteo.com/en/terms',
      ]),
    );
  });

  it('leaves out the sample date for live data', () => {
    expect(text(attributionLines({ live: true }))).not.toContain('retrieved');
  });

  it('drops GeoNames and explains a sample-only build', () => {
    const all = text(
      attributionLines({ live: false, sampleRetrieved: '2026-11-22' }),
    );
    expect(all).not.toContain('GeoNames');
    expect(all).toContain('Live search is not available on this site');
    expect(all).toContain('Weather data by Open-Meteo.com');
  });
});

describe('placeDetails', () => {
  const base: Place = {
    id: 1,
    name: 'Uppsala',
    admin1: 'Uppsala County',
    country: 'Sweden',
    latitude: 59.86,
    longitude: 17.64,
  };

  it('tells a town and an airport with the same label apart', () => {
    const city: Place = {
      ...base,
      featureCode: 'PPLA',
      population: 177074,
      admin2: 'Uppsala Municipality',
    };
    const airport: Place = {
      ...base,
      id: 2,
      featureCode: 'AIRP',
      admin2: 'Uppsala Municipality',
    };
    const all = [city, airport];
    expect(placeDetails(city, all)).toEqual(['pop. 177,074']);
    expect(placeDetails(airport, all)).toEqual(['airport']);
  });

  it('adds the second-level region only when look-alikes differ in it', () => {
    const a: Place = { ...base, featureCode: 'PPL', admin2: 'Askersund' };
    const b: Place = { ...base, id: 2, featureCode: 'PPL', admin2: 'Markaryd' };
    const other: Place = { ...base, id: 3, admin1: 'Kronoberg County' };
    expect(placeDetails(a, [a, b, other])).toEqual(['Askersund']);
    expect(placeDetails(a, [a, other])).toEqual([]);
  });

  it('gives nothing for a place without extra fields', () => {
    expect(placeDetails(base, [base])).toEqual([]);
  });
});
