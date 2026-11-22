// Build-time helpers shared by vite.config.ts and `make demo`.
//
// `isWeatherLive` reads the VITE_WEATHER_LIVE build switch (live Open-Meteo
// search on unless set to "false", "0", "off" or "no"). `headersText` is the
// Cloudflare Pages `_headers` file written to the deploy root: the wasm MIME
// rule plus a connect-src policy for the demo.
//
// Run as a script it writes that file:
//   node examples/web/scripts/headers.mjs target/doc/_headers

import { writeFileSync } from 'node:fs';
import { argv, env } from 'node:process';
import { pathToFileURL } from 'node:url';

/** The two Open-Meteo hosts the weather part may call. */
export const OPEN_METEO_ORIGINS = [
  'https://geocoding-api.open-meteo.com',
  'https://previous-runs-api.open-meteo.com',
];

/**
 * @param {string | undefined} value raw VITE_WEATHER_LIVE value
 * @returns {boolean} whether live weather search is enabled
 */
export function isWeatherLive(value) {
  if (value === undefined) {
    return true;
  }
  return !['false', '0', 'off', 'no'].includes(value.trim().toLowerCase());
}

/**
 * @param {boolean} live whether live weather search is enabled
 * @returns {string} the `_headers` file content
 */
export function headersText(live) {
  const connect = live ? ["'self'", ...OPEN_METEO_ORIGINS] : ["'self'"];
  return [
    '/*.wasm',
    '  Content-Type: application/wasm',
    '/demo/*',
    `  Content-Security-Policy: connect-src ${connect.join(' ')}`,
    '',
  ].join('\n');
}

if (argv[1] && import.meta.url === pathToFileURL(argv[1]).href) {
  const out = argv[2];
  if (!out) {
    throw new Error('usage: node headers.mjs <output path>');
  }
  writeFileSync(out, headersText(isWeatherLive(env.VITE_WEATHER_LIVE)));
}
