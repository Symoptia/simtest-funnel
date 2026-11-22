// Text shown in the weather part: numbers, the window line, the one-line
// answer and the attribution. Plain functions so tests can check the words.

import { Status, type StatusCode } from '@simtest-js/funnel';
import type { AgeRow } from './compare';
import { type Place, placeLabel, type WeatherTolerances } from './model';

const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/** A number without float noise: 2, 0.5, 10 (at most 3 decimals). */
export function formatNumber(v: number): string {
  return String(Math.round(v * 1000) / 1000);
}

/** A share as a percentage with one decimal: "3.9 %". */
export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)} %`;
}

/** "±2 °C and ±3 h". */
export function formatTolerances(tol: WeatherTolerances, unit: string): string {
  const value = `±${formatNumber(tol.valueTol)}${unit ? ` ${unit}` : ''}`;
  return `${value} and ±${formatNumber(tol.timeTolHours)} h`;
}

function day(sec: number): { d: number; m: string; y: number } {
  const date = new Date(sec * 1000);
  return {
    d: date.getUTCDate(),
    m: MONTHS[date.getUTCMonth()],
    y: date.getUTCFullYear(),
  };
}

/** "5 Nov – 18 Nov 2026" for two epoch seconds (UTC dates). */
export function formatDateRange(startSec: number, endSec: number): string {
  const a = day(startSec);
  const b = day(endSec);
  const left = a.y === b.y ? `${a.d} ${a.m}` : `${a.d} ${a.m} ${a.y}`;
  return `${left} – ${b.d} ${b.m} ${b.y}`;
}

/** Name of a library status for the verdict badge. */
export function statusName(status: StatusCode): string {
  const entry = Object.entries(Status).find(([, code]) => code === status);
  return entry ? entry[0] : String(status);
}

/** "made 1 day ahead" / "made 3 days ahead". */
export function ageWords(age: number): string {
  return `made ${age} ${age === 1 ? 'day' : 'days'} ahead`;
}

/** "14 of 360 hours". */
export function hoursOutside(row: AgeRow): string {
  return `${row.pointsOutside} of ${row.pointsCompared} hours`;
}

/** The one-line answer above the table for the selected age. */
export function answerLine(
  row: AgeRow,
  tol: WeatherTolerances,
  unit: string,
): string {
  const who = `The forecast ${ageWords(row.age)}`;
  const within = formatTolerances(tol, unit);
  if (row.status === null) {
    return `${who}: no forecast data for this window.`;
  }
  if (row.pass) {
    return `${who} stayed within ${within} for all ${row.pointsCompared} hours.`;
  }
  if (row.status !== Status.Fail) {
    return `${who} could not be compared (${statusName(row.status)}).`;
  }
  const share =
    row.fractionOfPointsOutside === null
      ? ''
      : `${formatPercent(row.fractionOfPointsOutside)} of the hours (${hoursOutside(row)}) were outside the tube`;
  return `${who} did not stay within ${within}: ${share}.`;
}

/** One link or plain text piece of the attribution block. */
export interface AttributionPart {
  text: string;
  href?: string;
}

/** Options of {@link attributionLines}. */
export interface AttributionOptions {
  /** Live place search is offered on this page. */
  live: boolean;
  /** Retrieval date when the bundled sample is shown. */
  sampleRetrieved?: string;
}

/**
 * The attribution and caveats shown with any weather data (spec "Weather
 * data attribution"), one array of parts per line.
 */
export function attributionLines(
  opts: AttributionOptions,
): AttributionPart[][] {
  const lines: AttributionPart[][] = [
    [
      {
        text: 'Weather data by Open-Meteo.com',
        href: 'https://open-meteo.com/',
      },
      { text: ', licensed under ' },
      {
        text: 'CC BY 4.0',
        href: 'https://creativecommons.org/licenses/by/4.0/',
      },
      { text: '. Forecasts: ECMWF IFS HRES 9 km (' },
      { text: 'ECMWF', href: 'https://www.ecmwf.int/' },
      { text: ').' },
    ],
  ];
  if (opts.live) {
    lines.push([
      { text: 'Location data based on ' },
      { text: 'GeoNames', href: 'https://www.geonames.org/' },
      { text: '.' },
    ]);
  }
  if (opts.sampleRetrieved) {
    lines.push([
      {
        text: `Bundled sample retrieved ${opts.sampleRetrieved}; no changes.`,
      },
    ]);
  }
  lines.push([
    {
      text: 'The "latest run" is the weather model\'s newest analysis of each hour, not station measurements: a pass means the earlier forecast agreed with a later model run.',
    },
  ]);
  lines.push(
    opts.live
      ? [
          {
            text: "Live data comes from Open-Meteo's free API, which is for non-commercial use (",
          },
          { text: 'terms', href: 'https://open-meteo.com/en/terms' },
          {
            text: '). Requests go from your browser directly to Open-Meteo, without an API key; nothing is stored.',
          },
        ]
      : [
          {
            text: "Live search is not available on this site; the sample shows how it works. Open-Meteo's free API is for non-commercial use (",
          },
          { text: 'terms', href: 'https://open-meteo.com/en/terms' },
          { text: ').' },
        ],
  );
  return lines;
}

/** Words for GeoNames feature codes that are not plain towns or villages. */
const FEATURE_KINDS: Record<string, string> = {
  PPLC: 'capital',
  PPLX: 'part of a town',
  AIRP: 'airport',
  ADM1: 'administrative area',
  ADM2: 'administrative area',
  ADM3: 'administrative area',
  ADM4: 'administrative area',
  ADM5: 'administrative area',
  ADMD: 'administrative area',
  PCLI: 'country',
  ISL: 'island',
  MT: 'mountain',
  LK: 'lake',
  RSTN: 'railway station',
  PRT: 'port',
};

/**
 * Extra words that tell a search result apart from others with the same
 * name, region and country, all from the one geocoding answer: the kind of
 * place (e.g. "airport"; nothing for an ordinary town), the second-level
 * region when it differs between such look-alikes, and the population.
 */
export function placeDetails(
  place: Place,
  results: readonly Place[],
): string[] {
  const parts: string[] = [];
  const kind = place.featureCode ? FEATURE_KINDS[place.featureCode] : undefined;
  if (kind) {
    parts.push(kind);
  }
  const label = placeLabel(place);
  const lookAlikes = results.filter(
    (p) => p !== place && placeLabel(p) === label,
  );
  if (place.admin2 && lookAlikes.some((p) => p.admin2 !== place.admin2)) {
    parts.push(place.admin2);
  }
  if (place.population !== undefined) {
    parts.push(`pop. ${place.population.toLocaleString('en-US')}`);
  }
  return parts;
}
