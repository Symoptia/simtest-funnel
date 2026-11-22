import { describe, expect, it } from 'vitest';
import attribution from '../../open-meteo/ATTRIBUTION.md?raw';
import {
  loadSample,
  parseSampleCsv,
  SAMPLE_CSV,
  SAMPLE_PLACE,
} from '../src/weather/sample';

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(text),
  );
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

describe('bundled sample', () => {
  it('is imported unchanged from examples/open-meteo', async () => {
    expect(SAMPLE_CSV.startsWith('latitude,longitude')).toBe(true);
    const pinned = /SHA-256:\*\*\s*`([0-9a-f]{64})`/.exec(attribution)?.[1];
    expect(pinned).toBeDefined();
    expect(await sha256(SAMPLE_CSV)).toBe(pinned);
  });

  it('reads 360 hours of temperature with ages 1, 3 and 5', () => {
    const d = loadSample();
    expect(d.source).toBe('sample');
    expect(d.place).toBe(SAMPLE_PLACE);
    expect(d.retrieved).toBe('2026-11-22');
    expect(d.variable).toBe('temperature_2m');
    expect(d.unit).toBe('°C');
    expect(d.time.length).toBe(360);
    expect(d.time[0]).toBe(1793836800);
    expect(d.time[359]).toBe(1793836800 + 359 * 3600);
    expect([...d.ages.keys()]).toEqual([1, 3, 5]);
    expect([
      d.latest[0],
      d.ages.get(1)?.[0],
      d.ages.get(3)?.[0],
      d.ages.get(5)?.[0],
    ]).toEqual([4.3, 3.9, 4.4, 3.9]);
  });

  it('reads empty cells as missing', () => {
    const text = [
      'latitude,longitude',
      '1,2',
      '',
      'time,precipitation (mm),precipitation_previous_day2 (mm)',
      '2026-01-01T00:00,0.1,',
      '2026-01-01T01:00,,0.3',
      '',
    ].join('\n');
    const d = parseSampleCsv(text, 'Somewhere');
    expect(d.variable).toBe('precipitation');
    expect(d.unit).toBe('mm');
    expect(d.time[1] - d.time[0]).toBe(3600);
    expect(d.latest[0]).toBe(0.1);
    expect(Number.isNaN(d.latest[1])).toBe(true);
    expect(Number.isNaN(d.ages.get(2)?.[0] ?? 0)).toBe(true);
  });

  it('rejects a file of another shape', () => {
    expect(() => parseSampleCsv('a\nb\nc\nx,y\n')).toThrow(/time column/);
    expect(() =>
      parseSampleCsv('a\nb\n\ntime,pressure_msl (hPa)\n2026-01-01T00:00,1\n'),
    ).toThrow(/unexpected column/);
  });
});
