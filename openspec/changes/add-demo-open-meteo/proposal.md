# Proposal

## Why

The browser demo at `/demo` compares three synthetic signals. It shows
that the funnel runs in the browser, but not why anyone would want a
tolerance tube with a time tolerance. The owner wants a real, public
example a visitor can play with: weather forecasts against what
happened, answering **"was the forecast made N days ahead close enough
to what happened?"** The same story is planned for the MCP server in
`add-mcp-url-ingestion` (hand trial, Stockholm, 15 days hourly: share of
points outside the tube for the day-1/3/5 forecasts drops from
2.2 / 25.3 / 32.0 % with ±2 °C alone to 0.6 / 9.7 / 19.5 % with
±2 °C ±3 h). In the browser the visitor can pick their own place,
variable, forecast age and tolerances and see the tube react at once.

The owner chose a modest extension of the existing demo over a separate
map application: no map, no new heavy dependency, same page, same build
and deploy.

Open-Meteo makes this possible without a server of our own (checked on
2026-11-22, design.md "Context"): its Previous Runs API and Geocoding
API need no API key, answer JSON and send
`Access-Control-Allow-Origin: *`, so the visitor's browser can call them
directly from the docs site.

## What Changes

- **A "Real weather" part of the demo** next to the existing synthetic
  signals, which stay as they are (design.md §1: tabs, synthetic first).
- **Place search by name** through Open-Meteo's Geocoding API: type at
  least two characters, pick from a short result list showing name,
  region and country. No map.
- **Choice of weather variable** from a short list (temperature,
  precipitation, wind speed; design.md §3) and of **forecast age**:
  the forecast made 1 to 7 days before each hour.
- **Comparison in the browser**: the forecast made N days ahead
  (`<variable>_previous_dayN`, test) against the latest model run
  (`<variable>`, reference) over a past window (the last 14 full days
  in UTC, design.md §4), with the existing WASM `compare()` and
  `summarize()`.
- **Adjustable tolerances**: a value tolerance and a time tolerance with
  per-variable presets (for example ±2 °C and ±3 h). The time tolerance
  is always visible and explained in one sentence, because the default
  x tolerance is zero in every API.
- **Results**: verdict (pass/fail), share of points outside the tube and
  the funnel plot the demo already draws (with a date axis), plus a
  small table with verdict and share outside for every forecast age at
  once (computed from the same response, no extra request).
- **Works without network**: the weather part opens on the bundled
  Open-Meteo sample of `add-mcp-url-ingestion`
  (`examples/open-meteo/stockholm-2026-11-05-to-19.csv`, Stockholm,
  temperature, day 1/3/5) and makes no request until the visitor
  searches for a place. One sample, read by the demo directly; no second
  copy in another format (design.md §8).
- **Request hygiene**: no API key, no credentials, no cookies; one
  geocoding request per (debounced) search and one forecast request per
  place, variable and window, which covers all seven forecast ages;
  responses cached in memory for the page's lifetime; requests go only
  to the two Open-Meteo hosts (enforced by a `connect-src` policy,
  design.md §11).
- **Clear states**: loading, offline, rate limit (HTTP 429, with the
  retry time when given), bad request, no place found, no data for the
  chosen forecast age.
- **Attribution and caveats** always visible in the weather part:
  "Weather data by Open-Meteo.com" (CC BY 4.0, link to the licence),
  forecasts by ECMWF, "Location data based on GeoNames", that the
  "latest run" is a model analysis and not station measurements, and a
  usage note on Open-Meteo's free tier (non-commercial use; requests go
  from the browser directly to Open-Meteo).
- **Live requests can be switched off at build time**, leaving a
  sample-only weather part. Live search is on by default (owner
  decision 1, Decisions).
- **Tests and CI**: the demo gets its first automated tests (vitest,
  already used by the SDK) for the pure parts (URL building, JSON and
  sample parsing, missing values, caching, error mapping, the comparison
  pipeline on the bundled sample); no test touches the network. CI
  builds the demo and runs these tests, so a broken demo is caught
  before the release job.

Explicitly out of scope:

- A map, geolocation ("use my position"), or any map/tile library.
- Station observations or any data source other than Open-Meteo.
- Weather models other than one pinned model (`ecmwf_ifs`), daily
  aggregates, ensembles, units other than Open-Meteo's defaults.
- Shareable links that encode place and settings (they would trigger a
  request on page load without a user action); a later change may add
  them.
- A server-side proxy, an API key or any backend; the docs site stays
  static.
- Changes to the SDK, the Rust core, the WASM bindings, the MCP server or
  the landing page beyond the link text.

## Capabilities

### New Capabilities

None. The weather part is part of the existing demo site.

### Modified Capabilities

- `wasm-demo-site`: "Browser demo runs WASM comparison" changes from
  "only the deployed static assets" to "static assets plus, in the
  weather part and only after a visitor action, the two Open-Meteo
  APIs". New requirements cover the weather part: its place in the
  page, place search, variable and forecast age, the comparison,
  tolerances and the time-tolerance explanation, results, missing data,
  request hygiene, error states, attribution, the offline sample, the
  build-time switch for live data, the `connect-src` policy and
  network-free tests run in CI.

## Impact

- `examples/web/`: `index.html` (tabs, weather controls, attribution),
  `src/main.ts` split into the synthetic part and new weather modules,
  `vite.config.ts` (build-time live-data switch, vitest config),
  `package.json` (vitest dev dependency, `test` script), new tests.
- Reads `examples/open-meteo/stockholm-2026-11-05-to-19.csv` at build
  time (bundled into the demo's JavaScript, about 12 kB).
- `Makefile`: `make demo` writes a `connect-src` rule for `/demo/*` into
  `target/doc/_headers` next to the existing wasm rule; `test-js` also
  runs the demo tests.
- `.github/workflows/ci.yml`: the `js-test` job builds the demo and runs
  its tests. `release.yml` `publish-docs` is unchanged (it already runs
  `make demo`).
- No new runtime dependency; Plotly stays on its pinned CDN script.
  New dev dependency: `vitest` in `examples/web` (same major as the SDK).
- **Depends on `add-mcp-url-ingestion`** for the bundled sample
  (`examples/open-meteo/`, committed); the demo uses it unchanged.
- External: visitors' browsers call `geocoding-api.open-meteo.com` and
  `previous-runs-api.open-meteo.com`. Open-Meteo limits free use per IP
  address, so each visitor has their own budget; the owner judges the
  open-source library demo to be non-commercial use (Decisions).
- The remaining details (tabs, variables and presets, window, ages
  table, sample reuse, CSP, tests in CI) are worked out in design.md,
  each a design choice the owner accepted as recommended.

## Decisions

Decided by the owner (binding for design and specs):

- **A modest extension of the existing demo**, not a separate map
  application: place search by name (no map), a choice of weather
  variable and forecast age, "forecast made N days ahead" against
  "latest run", compared in the browser, with adjustable value and time
  tolerance, showing verdict, share of points outside the tube and the
  existing plot.
- **The default x tolerance is zero in all APIs**; the demo makes the
  time tolerance visible and explains it.

- **Live search ships enabled (owner decision 1, settled 2026-11-22).**
  The owner judges the demo of the open-source library to be within
  Open-Meteo's free non-commercial terms: no ads, no subscriptions, no
  API key, each visitor's browser calls Open-Meteo directly within its
  own per-IP budget. The build-time switch `VITE_WEATHER_LIVE` stays
  (default on) so live search can be turned off without a code change if
  Open-Meteo ever asks; the visible attribution, the usage note and the
  request hygiene are unchanged. Options considered before the decision:
  (a) ask Open-Meteo for written confirmation first, (b) ship sample-only
  until then, (c) a commercial plan behind a key-hiding proxy, (d) an
  opt-in click before the first live request.
- **All design choices of design.md are accepted as recommended**;
  deviations found during implementation are recorded there.
