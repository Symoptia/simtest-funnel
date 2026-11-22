// The bundled Open-Meteo sample of examples/open-meteo/, read as the CSV it
// is committed as (no second copy in another format).

import sampleCsv from '../../../open-meteo/stockholm-2026-11-05-to-19.csv?raw';
import { type VariableId, variableById, type WeatherData } from './model';

/** Display name of the sample place. */
export const SAMPLE_PLACE = 'Stockholm (sample)';
/** Date the sample was retrieved (examples/open-meteo/ATTRIBUTION.md). */
export const SAMPLE_RETRIEVED = '2026-11-22';

/** The raw text of the bundled sample. */
export const SAMPLE_CSV: string = sampleCsv;

const PREAMBLE_LINES = 3;
const ISO_HOUR = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;
const COLUMN = /^([a-z0-9_]+?)(?:_previous_day(\d+))? \((.*)\)$/;

/**
 * Read an Open-Meteo CSV answer: a three-line preamble, then
 * `time,<name> (<unit>),...` with ISO times in GMT (read as UTC) and empty
 * cells for missing values. One variable, its latest run and any
 * `_previous_dayN` columns.
 */
export function parseSampleCsv(
  text: string,
  place: string = SAMPLE_PLACE,
): WeatherData {
  const lines = text.split(/\r?\n/).filter((l, i) => i < 3 || l.length > 0);
  const header = (lines[PREAMBLE_LINES] ?? '').split(',');
  if (header[0] !== 'time') {
    throw new Error('sample: expected a time column on line 4');
  }
  let variable: VariableId | undefined;
  let unit = '';
  let latestCol = -1;
  const ageCols = new Map<number, number>();
  header.slice(1).forEach((name, i) => {
    const m = COLUMN.exec(name);
    const v = m ? variableById(m[1]) : undefined;
    if (!m || !v || (variable && v.id !== variable)) {
      throw new Error(`sample: unexpected column "${name}"`);
    }
    variable = v.id;
    unit = m[3];
    if (m[2] === undefined) {
      latestCol = i + 1;
    } else {
      ageCols.set(Number(m[2]), i + 1);
    }
  });
  if (!variable || latestCol < 0) {
    throw new Error('sample: no latest-run column');
  }
  const rows = lines.slice(PREAMBLE_LINES + 1).map((l) => l.split(','));
  const n = rows.length;
  const cell = (row: string[], col: number): number => {
    const s = row[col] ?? '';
    return s === '' ? Number.NaN : Number(s);
  };
  const time = new Float64Array(n);
  const latest = new Float64Array(n);
  const ages = new Map<number, Float64Array>();
  for (const age of [...ageCols.keys()].sort((a, b) => a - b)) {
    ages.set(age, new Float64Array(n));
  }
  rows.forEach((row, r) => {
    if (row.length !== header.length || !ISO_HOUR.test(row[0])) {
      throw new Error(`sample: bad row ${r + PREAMBLE_LINES + 2}`);
    }
    time[r] = Date.parse(`${row[0]}:00Z`) / 1000;
    latest[r] = cell(row, latestCol);
    for (const [age, col] of ageCols) {
      const series = ages.get(age);
      if (series) {
        series[r] = cell(row, col);
      }
    }
  });
  return {
    place,
    variable,
    unit,
    time,
    latest,
    ages,
    source: 'sample',
    retrieved: SAMPLE_RETRIEVED,
  };
}

/** The bundled sample, parsed. */
export function loadSample(): WeatherData {
  return parseSampleCsv(SAMPLE_CSV);
}
