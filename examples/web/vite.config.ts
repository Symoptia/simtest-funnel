import { defineConfig } from 'vite';
import wasm from 'vite-plugin-wasm';

// Built under "/demo/" on the deployed docs site; relative base keeps asset
// and CSV URLs working regardless of the mount point.
export default defineConfig({
  base: './',
  plugins: [wasm()],
  build: {
    target: 'esnext',
    outDir: 'dist',
  },
});
