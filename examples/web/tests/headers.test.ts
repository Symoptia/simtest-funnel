import { describe, expect, it } from 'vitest';
import { headersText, isWeatherLive } from '../scripts/headers.mjs';

describe('_headers for the deploy root', () => {
  it('keeps the wasm rule and allows the two Open-Meteo hosts when live', () => {
    expect(headersText(true)).toBe(
      [
        '/*.wasm',
        '  Content-Type: application/wasm',
        '/demo/*',
        "  Content-Security-Policy: connect-src 'self' https://geocoding-api.open-meteo.com https://previous-runs-api.open-meteo.com",
        '',
      ].join('\n'),
    );
  });

  it("allows only 'self' without live data", () => {
    expect(headersText(false)).toBe(
      [
        '/*.wasm',
        '  Content-Type: application/wasm',
        '/demo/*',
        "  Content-Security-Policy: connect-src 'self'",
        '',
      ].join('\n'),
    );
  });

  it('reads the build switch with live on by default', () => {
    expect(isWeatherLive(undefined)).toBe(true);
    expect(isWeatherLive('')).toBe(true);
    expect(isWeatherLive('true')).toBe(true);
    expect(isWeatherLive('1')).toBe(true);
    for (const off of ['false', 'FALSE', '0', 'off', 'no', ' false ']) {
      expect(isWeatherLive(off)).toBe(false);
    }
  });
});
