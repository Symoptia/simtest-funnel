# Tasks

All paths are under `examples/web/` unless stated otherwise. Owner
decision 1 (proposal, Decisions: may the public demo call Open-Meteo's
free API) is settled: live search ships enabled.

## 1. Prerequisites and test setup

- [x] 1.1 Confirm `add-mcp-url-ingestion` has committed `examples/open-meteo/stockholm-2026-11-05-to-19.csv` and `ATTRIBUTION.md` unchanged (SHA-256 in `ATTRIBUTION.md` matches `sha256sum` of the CSV) and note the shares outside it pins for day 1/3/5 at ±2 °C ±3 h and ±2 °C 0 h; verify by running its walkthrough test
- [x] 1.2 Add `vitest` (`^5.1.0`, as in `packages/sdk`) as a dev dependency, a `test` script (`vitest run`), `vitest.config.ts` (`environment: 'node'`, wasm plugin if the SDK import needs it), `tests/setup.ts` replacing global `fetch` with a function that throws "network access in tests", and `tests/**/*` in `tsconfig.json` `include`; verify `pnpm test` runs a placeholder test, a test calling global `fetch` fails, and `pnpm lint` passes
- [x] 1.3 Check that `import sampleCsv from '../../open-meteo/stockholm-2026-11-05-to-19.csv?raw'` works in `pnpm build`, in `pnpm dev` (Vite `server.fs.allow` default = workspace root) and in vitest; verify a test asserting the imported text starts with `latitude,longitude` and the built bundle contains the sample

## 2. Data layer: model, Open-Meteo client, sample reader

- [x] 2.1 `src/weather/model.ts`: shared types (`WeatherData { place, unit, time: Float64Array (epoch s), latest, ages: Map<number, Float64Array with NaN for missing>, source: 'sample' | 'live', retrieved? }`) and the variable table (design §3: `temperature_2m` ±2 °C, `precipitation` ±1 mm, `wind_speed_10m` ±10 km/h, all ±3 h; value-input step per variable); verify unit tests over the table (three entries, presets as listed)
- [x] 2.2 `src/weather/openmeteo.ts`: URL builders for geocoding (`name`, `count=8`, `language=en`, `format=json`) and Previous Runs (design §4: rounded lat/lon to 4 decimals, variable plus `_previous_day1..7`, `models=ecmwf_ifs`, `timeformat=unixtime`, `start_date`/`end_date` from an injected "now": end = yesterday UTC, start = end − 13 days); verify tests with a fixed now (window 14 days, end before today, around a month and year boundary) and exact expected URLs
- [x] 2.3 In `openmeteo.ts`: JSON parsing into `WeatherData` (checks `hourly.time` and the requested keys, `null` → NaN, unit from `hourly_units`) and into place results (missing `results` → empty list, optional `admin1`/`country`); verify tests with small handwritten fixtures shaped like the answers recorded in design.md "Facts checked" (normal, gaps, all-`null` day 7, no `results`, missing `admin1`, missing keys → "unexpected answer")
- [x] 2.4 In `openmeteo.ts`: `fetchJson(url, { fetch, signal })` with `credentials: 'omit'`, `referrerPolicy: 'no-referrer'`, no custom headers, 15 s timeout, and the error mapping of design §10 (rejected fetch, 429 with/without `retry-after`, 400 with `reason`, other status, bad JSON, timeout, abort); verify tests with a fake `fetch` for each row of the table and that the request init has exactly those options
- [x] 2.5 `src/weather/cache.ts`: in-memory cache keyed by URL holding results or in-flight promises, failures evicted; verify tests: same URL twice → one fake-fetch call, concurrent calls → one call, failure then retry → two calls
- [x] 2.6 `src/weather/sample.ts`: reader for the bundled CSV (skip three-line preamble, header `time,<name> (<unit>),...`, ISO times as UTC epoch seconds, empty cells → NaN, `_previous_dayN` columns to ages) producing `WeatherData` with `source: 'sample'`, place "Stockholm (sample)" and retrieval date 2026-11-22; verify tests: 360 rows, first time `1793836800`, ages {1, 3, 5}, unit `°C`, first row values 4.3/3.9/4.4/3.9

## 3. Comparison pipeline

- [x] 3.1 `src/weather/compare.ts`: per age, drop hours where latest or forecast is NaN, drop hours later than now (design Risks: clock safeguard), skip ages with fewer than 2 hours ("no forecast data"), run `compare()` with `{ atoly, atolx: hours * 3600 }` (both always given) and `summarize()`, return rows (age, status, pass, pointsCompared, pointsOutside, fractionOfPointsOutside, missing count) plus the selected age's series and result; verify unit tests with synthetic data (a 2 h shifted series fails at 0 h and passes at ±3 h; gaps reported as "k of n missing"; all-NaN age skipped; future hours dropped)
- [x] 3.2 Pipeline test on the bundled sample with the real WASM: ages 1/3/5 at ±2 °C ±3 h and ±2 °C 0 h; verify the shares outside equal the numbers noted in 1.1 (same core as the MCP server) and pin them in the test

## 4. Page structure and synthetic part

- [x] 4.1 Move today's `src/main.ts` logic unchanged into `src/synthetic.ts`; `src/main.ts` sets up two tabs ("Synthetic signals" default, "Real weather"; `role="tab"`, `aria-selected`, panels with `hidden`, `#weather` selects the weather tab, hash updated on switch) and builds the weather panel lazily; verify `pnpm build` passes and, in `make demo-serve`, `/` shows the three synthetic plots as before and `/#weather` opens the weather tab with no request in the browser's network panel besides site assets and Plotly
- [x] 4.2 Update the header text in `index.html` to mention both parts and keep the synthetic footer; verify by viewing the page and `pnpm lint`

## 5. Weather UI on the sample

- [x] 5.1 `src/weather/ui.ts`: controls for variable (only variables in the loaded data), forecast age (only ages present), value tolerance (unit and per-variable step) and time tolerance (0-24 h, step 0.5) with the explanation sentence of design §7 always visible, presets applied on variable change with a "reset to preset" link, inputs debounced by 150 ms; verify in `make demo-serve` with the sample: ages 1/3/5 offered, ±2 °C ±3 h shown, setting 0 h changes the result
- [x] 5.2 Results view: one-line answer, window line (dates in UTC, hours compared, missing hours), ages table with verdict badge and share outside (percent with one decimal and "k of n hours"), row click selects the age, plot via `createFunnelPlot` with series and result x arrays scaled to milliseconds, `xaxis.type = 'date'`, axis title "time (UTC)", trace names "latest run" / "forecast made N days ahead", unit on the y axis; Plotly-missing fallback text; verify in the browser that the plot shows dates, the table matches 3.2's numbers, and with Plotly blocked the table still appears
- [x] 5.3 Attribution block (design §8 and spec "Weather data attribution"): "Weather data by Open-Meteo.com" linked to `https://open-meteo.com/`, CC BY 4.0 link, "Forecasts: ECMWF IFS HRES 9 km", for the sample "sample retrieved 2026-11-22", the "latest run is a model analysis, not measurements" note; GeoNames line and usage note only when search is offered (group 7); verify by viewing the sample and a test on the attribution text builder for sample and live

## 6. Build, network policy and CI

- [x] 6.1 Build-time switch `VITE_WEATHER_LIVE` (default true) read via `import.meta.env`; when false the search UI is not rendered and the live-data module is not imported (dead-code eliminated); verify `VITE_WEATHER_LIVE=false pnpm build` produces a bundle without the strings `geocoding-api.open-meteo.com` and `previous-runs-api.open-meteo.com`, and the default build contains them
- [x] 6.2 `Makefile` `demo`: pass `VITE_WEATHER_LIVE` through and write the `/demo/*` `connect-src` rule into `target/doc/_headers` after the wasm rule (design §11; `'self'` only when live is off); verify `make demo` and `VITE_WEATHER_LIVE=false make demo` give the two expected `_headers` texts (checked by a small test or a `grep` in the task log) and the wasm rule is unchanged
- [ ] 6.3 `Makefile` `test-js`: after the SDK tests run `cd examples/web && pnpm install && pnpm test`; `.github/workflows/ci.yml` `js-test`: run `make demo` and the demo tests after the SDK tests; verify `make test-js` passes locally (done) and the CI run on the branch shows the demo build and tests (pending: not pushed)
- [ ] 6.4 Verify `release.yml` `publish-docs` needs no change (it runs `make demo`) and, on a Cloudflare Pages preview deploy or `wrangler pages dev target/doc`, that `/demo/` serves the policy header and the sample tab works (`release.yml` checked: no change needed; policy and tab checked on a local static server applying `target/doc/_headers`, not yet on Pages)

## 7. Live search (owner decision 1: enabled)

- [x] 7.1 Place search in `ui.ts`: input "Place", 300 ms debounce, minimum 2 characters, Enter searches at once, `AbortController` for superseded searches, result list (up to 8, `role="listbox"`, keyboard navigable) with name, `admin1, country`, coordinates to 2 decimals, "No place found" state, geocoding cache by normalised input; verify unit tests for debounce and abort with fake timers and a fake `fetch`, and by hand: "Stockholm" lists Sweden and Maine entries
- [x] 7.2 Picking a place loads the forecast through the cache (one request for all ages), shows the place name with region and country, the 14-day window and the ages table 1-7; changing age or tolerances sends no request; "Back to sample" returns; errors (design §10) shown in place with earlier results greyed; verify unit tests for the controller logic with a fake `fetch` (one request per place/variable, cache hit on re-pick, error keeps previous results) and by hand in the browser network panel
- [x] 7.3 Add the GeoNames line and the usage note (design §12: live data from Open-Meteo's free API for non-commercial use, requests straight from the browser, no key, nothing stored); `publish-docs` keeps building with live search on (no `VITE_WEATHER_LIVE` set); verify in a local browser that the note is shown with live data (done) and, after deploy, on the Pages preview (pending)
- [x] 7.4 Optionally update `docs/index.html` demo link text to mention the weather tab (`demo/#weather`); verify the landing page links still resolve

## 8. Integration checks

- [x] 8.1 Run `make lint`, `make test-js`, `make demo` and `openspec validate add-demo-open-meteo --strict`; verify all pass and that there is no diff under `crates/`, `packages/sdk/src/` or `python/`

## Workflow follow-up

- Archive after review, after `add-mcp-url-ingestion` has been archived (it owns the sample this change reads).
- If Open-Meteo ever objects, set `VITE_WEATHER_LIVE=false` on the "Build browser demo" step of `release.yml`; no code or spec change needed.
