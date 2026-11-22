/** The two Open-Meteo hosts the weather part may call. */
export declare const OPEN_METEO_ORIGINS: string[];
/** Whether a raw VITE_WEATHER_LIVE value enables live weather search. */
export declare function isWeatherLive(value: string | undefined): boolean;
/** The Cloudflare Pages `_headers` file content for the deploy root. */
export declare function headersText(live: boolean): string;
