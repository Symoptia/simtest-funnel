/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 'true' or 'false': live Open-Meteo search (set by vite.config.ts). */
  readonly VITE_WEATHER_LIVE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
