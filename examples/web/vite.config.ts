import { defineConfig } from 'vite';
import topLevelAwait from 'vite-plugin-top-level-await';
import wasm from 'vite-plugin-wasm';

// Built under "/demo/" on the deployed docs site; relative base keeps asset
// and CSV URLs working regardless of the mount point.
export default defineConfig({
  base: './',
  plugins: [wasm(), topLevelAwait()],
  build: {
    target: 'esnext',
    outDir: 'dist',
  },
});
