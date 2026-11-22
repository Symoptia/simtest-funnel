import { fileURLToPath } from 'node:url';
import wasm from 'vite-plugin-wasm';
import { defineConfig } from 'vitest/config';

// Tests use the SDK source and its wasm glue (packages/sdk/src/wasm, built by
// `pnpm run build:wasm` in packages/sdk), as the SDK's own tests do, so they
// do not need the SDK's dist build.
export default defineConfig({
  plugins: [wasm()],
  resolve: {
    alias: {
      '@simtest-js/funnel': fileURLToPath(
        new URL('../../packages/sdk/src/index.ts', import.meta.url),
      ),
    },
  },
  define: {
    'import.meta.env.VITE_WEATHER_LIVE': JSON.stringify('true'),
  },
  test: {
    environment: 'node',
    setupFiles: ['./tests/setup.ts'],
  },
});
