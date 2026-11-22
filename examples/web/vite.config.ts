import { env } from 'node:process';
import { defineConfig } from 'vite';
import wasm from 'vite-plugin-wasm';
import { isWeatherLive } from './scripts/headers.mjs';

// Live Open-Meteo search is on unless the build runs with
// VITE_WEATHER_LIVE=false. The value is normalised to 'true' / 'false' so the
// app's check folds to a constant and a sample-only build drops the live code.
const weatherLive = isWeatherLive(env.VITE_WEATHER_LIVE);

// Built under "/demo/" on the deployed docs site; relative base keeps asset
// and CSV URLs working regardless of the mount point.
export default defineConfig({
  base: './',
  plugins: [wasm()],
  define: {
    'import.meta.env.VITE_WEATHER_LIVE': JSON.stringify(String(weatherLive)),
  },
  build: {
    target: 'esnext',
    outDir: 'dist',
  },
});
