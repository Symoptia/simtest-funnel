# Design

## Context

See proposal.md (Why, Decisions) for motivation and the owner's
decisions, and the spec delta for the required behaviour. Current state:

- `examples/web/` is a Vite app (`base: './'`, `vite-plugin-wasm`) with
  one module, `src/main.ts`: it fetches `./reference.csv` and
  `./test.csv`, splits `time,x,y,z` into three pairs, runs
  `compare()` with `atolx = atoly = 0.1` and draws three plots with the
  SDK's `createFunnelPlot`, Plotly being a CDN script
  (`plotly-3.6.0.min.js`, `async`) injected through `PlotlyLike`; if
  Plotly never loads the status is shown as text. No framework, inline
  CSS in `index.html`, Biome lint (`make lint-js`), `tsc --noEmit` in
  `pnpm build`.
- The demo has **no tests** and **CI never builds it**: `ci.yml` lints it
  (`make lint` → `lint-js`), and only `release.yml` `publish-docs` runs
  `make demo` (`build-sdk`, `pnpm build`, copy `dist/` to
  `target/doc/demo/`, write `target/doc/_headers` with the wasm MIME
  rule; Cloudflare Pages honours one `_headers` at the deploy root).
  There is no Content-Security-Policy today.
- SDK (`packages/sdk/src/index.ts`): `compare()`, `summarize()` (with
  `pointsCompared`, `pointsOutside`, `fractionOfPointsOutside`,
  `intervals`, `worst`), `downsampleMinMax()`, `createFunnelPlot()`
  (traces reference, test, lower/upper bound, |error| on `y2`; numeric
  x as given). Tolerances resolve per axis; an axis with no coefficient
  given gets x: all 0, y: `rtoly = 2e-3`. The SDK is tested with vitest
  5 in a `node` environment.
- The bundled sample of `add-mcp-url-ingestion` exists in the working
  tree (`examples/open-meteo/stockholm-2026-11-05-to-19.csv` and
  `ATTRIBUTION.md`, committed): the byte-identical CSV response
  for Stockholm, `models=ecmwf_ifs`, 2026-11-05..19, hourly
  `temperature_2m` and `_previous_day1/3/5`, a three-line preamble,
  ISO times in GMT, 360 rows, SHA-256 pinned in `ATTRIBUTION.md`.

### Facts checked on 2026-11-22

All with `curl`, a generic `User-Agent` and `Origin: https://example.org`
(no personal data), Stockholm unless stated.

**CORS.** Both APIs answered `200` with
`access-control-allow-origin: *`, `access-control-allow-methods: GET,
POST, OPTIONS` (geocoding: `GET, OPTIONS`) and `access-control-max-age:
600`. The Previous Runs API also sends
`access-control-expose-headers: x-ratelimit-cost, x-ratelimit-limit,
x-ratelimit-remaining, x-ratelimit-reset, x-ratelimit-window,
retry-after` and `X-RateLimit-Limit: 600.0`, `X-RateLimit-Window: 60`.
A `400` (end date before start date) also carries
`access-control-allow-origin: *` and the body
`{"reason":"End-date must be larger or equals than start-date","error":true}`,
so the browser can read error reasons. A plain `GET` without custom
headers is a CORS "simple request": no preflight. Geocoding responses
carry `cache-control: public, max-age=86400`; forecast responses carry
no cache header.

**Previous Runs JSON**
(`/v1/forecast?latitude=..&longitude=..&hourly=..&models=ecmwf_ifs&start_date=..&end_date=..&timeformat=unixtime`):
`Content-Type: application/json; charset=utf-8`;

```json
{"latitude":59.36731,"longitude":18.0,"generationtime_ms":0.07,
 "utc_offset_seconds":0,"timezone":"GMT","timezone_abbreviation":"GMT",
 "elevation":24.0,
 "hourly_units":{"time":"unixtime","temperature_2m":"°C",
                 "temperature_2m_previous_day1":"°C", "...": "..."},
 "hourly":{"time":[1794960000,1794963600,...],
           "temperature_2m":[2.0,2.3,...],
           "temperature_2m_previous_day1":[...]}}
```

- Columns are named `<variable>_previous_dayN`; N = 1..7 return data
  (one 14-day request with `temperature_2m` and all seven ages: 336
  rows per column, no nulls, 22 300 bytes uncompressed).
  `_previous_day8` is not an error but all `null`.
- `null` marks missing values: for `ecmwf_ifs` the archive of previous
  runs starts in early October 2025 (`_previous_day3` all `null` on
  2025-10-01, present on 2025-10-05; `_previous_day7` `null` on
  2025-10-05, present on 2025-10-10), while the latest-run column has
  values back to at least 2024. Open-Meteo's docs say most models are
  archived from January 2024 and name no ECMWF exception.
- **Future valid times are not forecasts of different ages.** With
  `forecast_days=7`, `_previous_day1` equalled the latest run for
  100 % of hours more than one day ahead, and `_previous_day5` for
  100 % of hours more than five days ahead (for past hours they agree on
  15 % and 2 % of hours, i.e. by coincidence of rounding). The API fills
  an age whose run does not exist yet with the newest run, so a window
  reaching into the future compares a forecast with itself and passes
  trivially. The window must end in the past (§4).
- `timeformat=unixtime` gives integer epoch seconds (UTC);
  default `iso8601` gives `2026-11-05T00:00` in GMT.
- Other variables checked with `_previous_day3`: `precipitation` (mm),
  `wind_speed_10m` (km/h), `pressure_msl` (hPa), `relative_humidity_2m`
  (%), `cloud_cover` (%); all populated. A Sydney request also answered,
  so `ecmwf_ifs` is global.
- **The bundled sample equals the JSON response.** The same request as
  the sample, as JSON with `timeformat=unixtime`, gave 0 differences
  over 360 rows × 4 columns against the bundled CSV, and its first time
  `1793836800` is `2026-11-05T00:00Z`. So the CSV, read with times as
  UTC, is exactly the data the live path would get (§8).

**Geocoding JSON** (`/v1/search?name=Stockholm&count=3&language=en&format=json`):

```json
{"results":[{"id":2673730,"name":"Stockholm","latitude":59.32938,
  "longitude":18.06871,"elevation":17.0,"feature_code":"PPLC",
  "country_code":"SE","timezone":"Europe/Stockholm","population":1515017,
  "country":"Sweden","admin1":"Stockholm County",
  "admin2":"Stockholm Municipality", "...": "..."}, "..."],
 "generationtime_ms":0.09}
```

- No match (`name=Xqzzqx`) and a single character (`name=S`) both answer
  `200` with **no `results` key** at all: `{"generationtime_ms":...}`.
  Docs: "Empty and single-character searches return no results"; two
  characters match exact names, three or more use prefix matching;
  empty fields are omitted (`admin1`, `country` may be missing);
  `count` up to 100; bad parameters give `400` with
  `{"error":true,"reason":"..."}`.

**Terms and licences** (open-meteo.com/en/terms, /en/licence,
/en/docs/geocoding-api, geonames.org/about.html):

- Free API: "You may only use the free API services for non-commercial
  purposes"; limits "less than 10'000 API calls per day, 5'000 per hour
  and 600 per minute" (table: 300 000 a month); "Rate limits are applied
  by IP addresses and application". Non-commercial examples include
  "Private or non-profit websites or apps that do not have subscriptions
  or advertising"; commercial examples include "Websites or apps that
  have subscriptions or display advertisements" and "Commercial products
  or promotional activities". Nothing on browser-side calls or on open
  source projects of companies. Misuse may be blocked without notice.
- Data licence CC BY 4.0: "You must give appropriate credit, provide a
  link to the licence, and indicate if changes were made", with "a link
  next to any location Open-Meteo data are displayed"; example text
  "Weather data by Open-Meteo.com" linking to `https://open-meteo.com/`.
  The licence page lists ECMWF forecasts under CC-BY and "Location
  database from GeoNames" under CC-BY. The geocoding docs attribute
  "Location data based on GeoNames" linking to geonames.org; GeoNames
  states its database is under "a creative commons attribution license"
  (page footer: CC BY 4.0).
- **Not verified (assumed):** how Open-Meteo's commercial plans
  authenticate (an API key on separate customer hosts, from general
  knowledge) and whether those hosts send CORS headers; whether Plotly
  3.6 works under a strict `script-src` (only relevant if §11 grows
  beyond `connect-src`). A 429 response was not provoked on purpose;
  its handling relies on the documented limits and the exposed
  `retry-after` header.

## Goals / Non-Goals

**Goals:**

- A visitor gets a verdict for their own town in two actions (search,
  pick) and can then change age and tolerances with no further request.
- The page stays a static site; the only third-party requests are the
  Plotly script and, after a visitor action, the two Open-Meteo hosts.
- The weather part is fully usable offline on the bundled sample, and
  the build can ship it sample-only.
- Numbers agree with every other API: the same sample and tolerances
  give the same share outside in the demo as in the MCP walkthrough.

**Non-Goals:**

- No new runtime dependency, framework or component library; plain
  TypeScript and DOM as today.
- No persistence (no `localStorage`, no URL state), no analytics.
- No accessibility or styling overhaul of the existing synthetic part
  beyond what the tabs need.

## Decisions

Items marked **(design choice, not yet confirmed by the owner)** were
this design's answer to something the owner's decisions left open; each
gives the recommendation and the main alternative. **The owner accepted
all of them as recommended (2026-11-22)**; the markers are kept for
history. Deviations made during implementation are listed under
"Implementation notes" at the end.

### 1. Place in the page: two tabs, synthetic first (design choice, not yet confirmed by the owner)

Two tabs at the top of `/demo`: "Synthetic signals" (today's content,
unchanged, default) and "Real weather". Plain buttons with
`role="tab"`/`aria-selected`, panels toggled with `hidden`; the
selected tab is also reflected in the URL hash (`#weather`) so the docs
landing page can link straight to it (the hash carries no place or
settings, so opening it makes no request). The weather panel is built
lazily on first open.

Rationale: keeps the existing spec scenarios and the synthetic story
intact, and keeps the weather controls from pushing the synthetic plots
far down. Alternative: one long page with a second section below the
synthetic plots — simpler markup, but the weather part would be below
the fold and the page would load Plotly plots for both parts at once.
Alternative: weather first — more engaging for visitors, but changes
the first impression of a technical demo; easy to flip later.

### 2. Place search UX (design choice, not yet confirmed by the owner)

- One text input labelled "Place". A search runs 300 ms after the last
  keystroke when the trimmed input has at least 2 characters (shorter
  inputs never reach the API: it returns nothing for them anyway). Enter
  runs it at once. An in-flight search is aborted (`AbortController`)
  when a newer one starts; only the newest answer is shown.
- Request: `https://geocoding-api.open-meteo.com/v1/search?name=<input>&count=8&language=en&format=json`.
  `language=en` fixed (alternative: `navigator.language`, nicer names
  but less predictable tests).
- Result list (up to 8, `role="listbox"`, keyboard navigable): name in
  bold, then `admin1, country` (missing parts left out), then
  coordinates rounded to 2 decimals as a disambiguator. No map, no
  flags. Picking a result closes the list and starts the forecast
  request (§4).
- "No place found for “…”" when `results` is absent or empty.
- Answers are cached in memory by normalised input (trimmed,
  lower-cased) for the page's lifetime, so backspacing and retyping
  causes no request.

### 3. Variables and presets (design choice, not yet confirmed by the owner)

Three variables, Open-Meteo's default units:

| Variable | API name | Unit | Preset value tolerance | Preset time tolerance |
| --- | --- | --- | --- | --- |
| Temperature (2 m) | `temperature_2m` | °C | ±2 °C | ±3 h |
| Precipitation | `precipitation` | mm (per hour) | ±1 mm | ±3 h |
| Wind speed (10 m) | `wind_speed_10m` | km/h | ±10 km/h | ±3 h |

- Temperature is the default (and the only variable in the sample).
  Precipitation is what most people care about and shows the funnel's
  strength with showers that come a few hours early or late; it is spiky,
  so verdicts will be harsher. Wind speed adds a variable people feel.
- Selecting a variable applies its presets (replacing what the visitor
  typed, with the preset shown in a "Preset: ±2 °C, ±3 h" hint and a
  "reset to preset" link).
- Alternative: add `pressure_msl` (±3 hPa; smooth, forecasts very well)
  or `relative_humidity_2m` — checked to work, left out to keep the list
  short. Adding one later is a table row.

### 4. Date window: the last 14 full days in UTC (design choice, not yet confirmed by the owner)

- `end_date` = yesterday in UTC, `start_date` = `end_date − 13 days`:
  336 hourly points, all valid times in the past, every age 1..7 has had
  its run. Dates are computed from the visitor's clock in UTC; the
  request uses `start_date`/`end_date` (not `past_days`), so the cache key
  and the shown window are explicit.
- Shown above the results as "5 Nov – 18 Nov 2026 (UTC), 336 hours".
- Not selectable in the first version. Rationale: no date picker, and no
  way to choose a window that reaches into the future (where both series
  are the same run, §Context) or before the archive (early October 2025
  for `ecmwf_ifs`). Alternative: an end-date picker bounded to
  `[2025-10-15, yesterday]` — useful for "how did the forecast do during
  the storm last month?"; can be added without changing the rest.
- One request per (place, variable, window) asks for the variable and
  all seven `_previous_dayN` columns:
  `https://previous-runs-api.open-meteo.com/v1/forecast?latitude=<lat>&longitude=<lon>&hourly=<v>,<v>_previous_day1,...,<v>_previous_day7&models=ecmwf_ifs&start_date=<d>&end_date=<d>&timeformat=unixtime`
  (about 22 kB). Changing forecast age or tolerances never requests
  again. Latitude and longitude are the geocoding result's values,
  rounded to 4 decimals (about 10 m; keeps cache keys stable and URLs
  short).
- Model pinned to `ecmwf_ifs` for the reasons recorded in
  `add-mcp-url-ingestion` design §12: ECMWF IFS HRES 9 km, CC BY 4.0
  (ECMWF open data since October 2025), global, hourly to 90 h and
  interpolated to hourly beyond, 15-day horizon so all seven ages are
  populated; and the bundled sample uses it, so live and offline data
  come from the same model.
- Times in GMT (`utc_offset_seconds` 0) as epoch seconds; the plot axis
  says "(UTC)". Alternative: `timezone=auto` for local times — nicer to
  read, but brings daylight-saving gaps and duplicates into a
  monotonic time axis; not worth it.

### 5. Comparison pipeline (design choice, not yet confirmed by the owner, for the details)

- Reference = `<variable>` (latest run), test = `<variable>_previous_dayN`,
  x = epoch seconds. Tolerances `{ atoly: <value tol>, atolx: <hours> * 3600 }`.
  Both coefficients are always given explicitly, so no axis falls back to
  a library default (the y default `rtoly = 2e-3` would be a surprising
  0.2 % of the range).
- Epoch seconds, not hours since the window start, so the demo computes
  exactly what the MCP server computes for the same data (its date-time
  axis is epoch seconds, `add-mcp-column-mapping-and-formats` design §4);
  that column-mapping change also tests that zero x tolerance on
  epoch-second data behaves like the same data shifted to 0.
- Missing values: an hour where either series is `null` is dropped from
  both series before comparing (both series share Open-Meteo's time
  axis). If fewer than 2 points remain, that age shows "no forecast data
  for this window" instead of a verdict, and is not compared. A partial
  gap is reported as "N of 336 hours missing" under the result.
- For each available age 1..7: `compare()` then `summarize()`; verdict =
  status `Pass`; share outside = `fractionOfPointsOutside` (shown as a
  percentage with one decimal; also "k of n hours"). Seven comparisons
  of 336 points take well under a frame, so all ages are recomputed on
  every tolerance change (inputs debounced by 150 ms).
- Non-pass, non-fail statuses (validation errors) are shown as failed
  with the status name, as the synthetic part does.

### 6. Results view: one plot, a table for all ages (design choice, not yet confirmed by the owner)

- A table "Forecast made … days ahead" with one row per age (1..7, or
  1/3/5 for the sample): age, verdict badge, share outside. The selected
  age is highlighted; clicking a row selects it (same as the age
  selector). This answers "how does skill drop with lead time?" at a
  glance at no extra cost (same response).
- Below: the funnel plot for the selected age via `createFunnelPlot`.
  `createFunnelPlot` uses x values as given, so the demo passes copies
  of the series and of the result's x arrays scaled from seconds to
  milliseconds and sets `xaxis: { type: 'date', title: 'time (UTC)' }`;
  Plotly reads millisecond numbers on a date axis as UTC. The comparison
  itself stays in seconds. Trace names: "latest run" and "forecast made
  N days ahead"; y axis title with the unit from `hourly_units`.
- Above the table, a one-line answer: "The forecast made 3 days ahead
  stayed within ±2 °C and ±3 h for 90.3 % of the hours" (or "… did
  not stay within …: 9.7 % of hours outside").
- No downsampling: 336 points per trace is small.
- Alternative: one age at a time without the table — simpler, but the
  lead-time story needs several clicks.

### 7. Time tolerance: visible and explained (owner decision; wording is a design choice, not yet confirmed by the owner)

Two number inputs side by side, "Value tolerance ± [2] °C" and
"Time tolerance ± [3] h" (0 to 24 h, step 0.5; value tolerance > 0,
step per variable), with this sentence directly below:

> The time tolerance lets a forecast that is right but a few hours early
> or late still count as inside the tube; at 0 h every hour is checked
> only against the same hour.

Setting 0 h is allowed and is the library default; the presets use
±3 h. The sentence stays visible (not a tooltip).

### 8. Offline default: the one bundled sample, read as CSV (design choice, not yet confirmed by the owner)

- The weather tab opens on the sample: "Stockholm (sample, 5–19 Nov
  2026)", temperature, day 1/3/5, presets ±2 °C ±3 h, results computed
  at once. No request is made until the visitor searches. A "sample"
  badge and the sample's own date range distinguish it from live data.
  Picking a live place replaces it; a "Back to sample" link returns.
- The demo imports the CSV of `add-mcp-url-ingestion` directly
  (`import sampleCsv from '../../open-meteo/stockholm-2026-11-05-to-19.csv?raw'`,
  bundled into the JavaScript, about 12 kB) and parses it with a small
  reader for exactly this shape: skip the three-line preamble, header
  `time,<name> (<unit>),...`, ISO times read as UTC epoch seconds,
  empty cells as missing. Both the CSV reader and the JSON reader
  produce the same in-memory shape (`time` in epoch seconds, latest run,
  a map age → series, unit), so everything after reading is shared.
- Why not a JSON copy of the sample: two committed samples of the same
  data would drift (Open-Meteo reprocesses archives, design of
  `add-mcp-url-ingestion` "Risks"), and attribution would have to be
  kept twice. The JSON of the same request was checked to carry
  identical values and times (§Context), so reading the CSV loses
  nothing. Alternative: a build step that converts the CSV to JSON — an
  extra moving part for no gain.
- The sample only offers temperature and ages 1, 3 and 5; the variable
  selector and the ages table show only what the loaded data has. The
  sample stays owned by `add-mcp-url-ingestion`; extending it (more
  ages or variables) is a change there, which the demo then picks up.
- The attribution shown for the sample is the same as for live data,
  plus "sample retrieved 2026-11-22" (from `ATTRIBUTION.md`).

### 9. Request hygiene (design choice, not yet confirmed by the owner, for the details)

- `fetch(url, { credentials: 'omit', referrerPolicy: 'no-referrer',
  cache: 'default' })`; no custom headers (keeps requests "simple": no
  preflight), no API key. Nothing about the visitor is sent beyond what
  any request carries (IP address, browser `User-Agent`); the search
  text and chosen coordinates go only to Open-Meteo.
- One geocoding request per debounced search, one forecast request per
  (place, variable, window). In-memory `Map` caches keyed by the full
  request URL, holding the parsed result (or the in-flight promise, so
  two quick clicks share one request). Failed requests are not cached.
  Cache lives as long as the page; nothing is written to storage.
- A request in flight for a superseded choice is aborted and its result
  ignored.
- All URL building and response parsing lives in one module with
  `fetch` injected, so tests can supply a fake.

### 10. Error states (design choice, not yet confirmed by the owner, for the wording)

| Situation | Detected by | Shown |
| --- | --- | --- |
| Offline / DNS / CORS failure | `fetch` rejects (`TypeError`) | "Could not reach Open-Meteo. Check your connection; the sample still works." |
| Rate limit | HTTP 429 | "Open-Meteo's rate limit was reached; try again in N s" (N from `retry-after` when present, else "in a minute") |
| Bad request | HTTP 400 with `{"error":true,"reason":...}` | "Open-Meteo refused the request: <reason>" |
| Other HTTP error | status ≥ 400 | "Open-Meteo answered <status>" |
| Malformed body | JSON parse fails or expected keys missing | "Unexpected answer from Open-Meteo" |
| No place | `results` missing or empty | "No place found for “…”" |
| Age without data | all `null` after alignment | per-row "no forecast data" |
| Timeout | no answer in 15 s (abort) | as offline |

Errors replace only the affected area (search list or results); the
previous results stay visible, greyed, until a new success. Plotly
missing: verdicts and table still shown, plot area says so (as the
synthetic part does).

### 11. `connect-src` policy for `/demo/*` (design choice, not yet confirmed by the owner)

`make demo` appends to `target/doc/_headers`:

```text
/demo/*
  Content-Security-Policy: connect-src 'self' https://geocoding-api.open-meteo.com https://previous-runs-api.open-meteo.com
```

Only `connect-src` is set, so `fetch`/XHR can reach nothing but the site
itself and the two Open-Meteo hosts — the browser enforces "nothing is
sent anywhere else", whatever a future edit or dependency does. Other
directives stay unset, so the Plotly CDN script, the inline styles and
WebAssembly keep working without testing every directive against
Plotly. Vite's dev server does not apply `_headers`; the policy is
checked by a small test on the generated `_headers` text and once by
hand on the Pages preview. With live data switched off (§12) the rule
becomes `connect-src 'self'`. Alternative: a full policy (`default-src
'self'; script-src 'self' https://cdn.plot.ly 'wasm-unsafe-eval'; ...`) —
stronger, but needs Plotly's needs verified (style injection, possible
`eval`), more risk than this change needs. Alternative: no policy —
fewer moving parts, but then the hygiene promise is only by inspection.

### 12. Live data switch and the terms question (owner decision 1: live search enabled; mechanism is a design choice, accepted)

- Build-time constant `VITE_WEATHER_LIVE` (default `true`, read through
  `import.meta.env`). When `false`, the place search is not rendered
  (replaced by "Live search is not available on this site; the sample
  shows how it works"), no Open-Meteo URL is reachable from the code
  path, and the `_headers` rule drops the Open-Meteo hosts. `make demo`
  passes it through from the environment, so `publish-docs` can switch
  it without code changes.
- Usage note under the attribution, with live data: "Live data comes
  from Open-Meteo's free API, which is for non-commercial use (terms).
  Requests go from your browser directly to Open-Meteo, without an API
  key; nothing is stored." In a sample-only build: "Live search is not
  available on this site; the sample shows how it works." plus the
  non-commercial note.
- **Decision (owner, 2026-11-22): live search ships enabled**; the owner
  judges the open-source library demo to be within Open-Meteo's free
  non-commercial terms. `publish-docs` runs `make demo` without the
  switch, so the deployed demo has live search. The options considered
  before were (a) written confirmation from Open-Meteo first, (b) a
  sample-only build until then, (c) a commercial plan behind a key-hiding
  proxy, (d) an opt-in click before the first live request. Rate limits
  are per IP address, so call volume is not the concern: a visitor makes
  a handful of calls. If Open-Meteo objects, `VITE_WEATHER_LIVE=false`
  on the "Build browser demo" step of `release.yml` turns live search
  off without a code change.

### 13. Tests without network, and CI (design choice, not yet confirmed by the owner)

- `examples/web` gets `vitest` (dev dependency, same major as the SDK,
  `^5.1.0`), a `vitest.config.ts` (`environment: 'node'`, wasm plugin as
  in the SDK's config if needed) and a `test` script. Tests live in
  `examples/web/tests/` and cover pure modules only (no DOM rendering):
  URL building (both APIs, rounding, all seven ages, window dates for a
  fixed "now"), JSON parsing (handwritten small fixtures: normal, `null`
  gaps, all-`null` age, missing `results`, missing `admin1`, 400 body),
  the CSV sample reader, error mapping (429 with and without
  `retry-after`, 400, 500, rejected fetch, timeout), cache and in-flight
  sharing with a fake `fetch`, debounce with fake timers, the `_headers`
  text for both switch values.
- No test can reach the network: a setup file replaces global `fetch`
  with one that throws ("network access in tests"), and every module
  that fetches takes an injected `fetch`.
- One pipeline test runs the real WASM `compare`/`summarize` on the
  bundled sample (ages 1/3/5, ±2 °C ±3 h and ±2 °C 0 h) and pins the
  shares outside. The same numbers are pinned by the MCP walkthrough
  test of `add-mcp-url-ingestion`; the implementation copies them from
  there and the task checks they match (same core, so they must be
  equal).
- The tests need the SDK's WASM glue (`packages/sdk/src/wasm`), as the
  SDK tests do. `make test-js` runs `build:wasm`, the SDK tests and then
  `cd examples/web && pnpm test`. In `ci.yml`, the `js-test` job adds
  `make demo` (which also type-checks) and the demo tests after the SDK
  tests, so CI builds the demo on every push; `publish-docs` is
  unchanged.
- The `tsconfig.json` `include` gains `tests/**/*` so `tsc --noEmit`
  checks the tests too; Biome already lints the whole folder.
- Alternative: Playwright end-to-end tests of the page — real DOM
  coverage, but a browser download in CI and more upkeep; not needed for
  a demo whose logic sits in pure modules.

### 14. Code layout and build (design choice, not yet confirmed by the owner)

- `src/main.ts`: tab switching, then `synthetic.ts` (today's code, moved
  unchanged) and, on first open, `weather/ui.ts`.
- `src/weather/openmeteo.ts` (URLs, fetch with injected `fetch`, JSON
  parsing, error mapping), `src/weather/sample.ts` (CSV reader and the
  `?raw` import), `src/weather/model.ts` (shared types, variable table
  with presets), `src/weather/compare.ts` (alignment, all-ages
  comparison, summary rows), `src/weather/cache.ts`, `src/weather/ui.ts`
  (DOM only).
- `vite.config.ts` unchanged except the vitest block if kept in one file;
  the `?raw` import of a file outside `examples/web` works in builds,
  and in the dev server because Vite's `server.fs.allow` defaults to the
  pnpm workspace root (checked during implementation, task 1.3).
- Bundle grows by the weather code and the 12 kB sample (a few tens of
  kB before gzip); no new runtime package.
- `docs/index.html`: the demo link text may mention the weather tab
  (`demo/#weather`); the landing-page requirement is unchanged.

## Risks / Trade-offs

- [Open-Meteo considers the docs site commercial use and blocks it or
  asks us to stop] → the owner judged the use non-commercial and ships
  live search (decision 1); the build switch
  turns live search off without a code change; the sample keeps the tab
  useful.
- [Open-Meteo changes the API (column names, null semantics, CORS)] →
  errors are shown, the sample keeps working; parsing checks expected
  keys and says "unexpected answer" instead of plotting nonsense.
- [The "latest run" is a model analysis, not measurements, so a "pass"
  means agreement with a later model run, not with the weather that was
  observed] → stated next to the results in plain words, as the MCP
  walkthrough does.
- [Visitors read "fail" as "the forecast was bad"] → the one-line answer
  says "stayed within ±… for X % of the hours", and the presets are
  moderate; the table shows the trend rather than a single verdict.
- [Precipitation fails almost always with a tight tube] → preset ±1 mm
  ±3 h; the sentence under the tolerances explains the time tolerance;
  acceptable for a demo.
- [The visitor's clock is wrong, making "yesterday" wrong] → a future
  `end_date` would include filled-in ages; safeguard: hours of live data
  later than "now" are left out of the comparison (the bundled sample is
  never trimmed, so a clock behind 2026 does not empty it).
- [CI time grows by a demo build] → seconds; the SDK build is already
  done in that job.
- [The sample's owner change is not archived yet] → this change depends
  on `add-mcp-url-ingestion`; its committed sample is used unchanged.

## Migration Plan

Additive: the synthetic part and its URL stay as they are. Deploy with
the next release through `publish-docs`. Rollback: build with
`VITE_WEATHER_LIVE=false` (sample-only) or revert the change; no data or
state to migrate.

## Open Questions

None. (The usage-note wording was tied to owner decision 1, now
settled.)

## Implementation notes

Deviations from the decisions above, found while implementing:

- **§9, superseded forecast requests are not aborted.** A forecast
  request for a superseded choice is left to finish and its answer is
  ignored by the UI (a token check in `controller.ts`), but it lands in
  the cache, so going back to that choice needs no new request. Aborting
  it would waste the request and break sharing of the in-flight promise.
  Geocoding searches are aborted as designed.
- **§5 / Risks, clock safeguard for live data only.** Hours later than
  now are left out only for live data; the bundled sample is compared in
  full whatever the visitor's clock says.
- **§11, `_headers` written by a script.** `make demo` writes
  `target/doc/_headers` with `node examples/web/scripts/headers.mjs`,
  which also holds the switch parsing used by `vite.config.ts`
  (`isWeatherLive`: on unless `false`, `0`, `off` or `no`), so the policy
  text is unit-tested and the build and the policy cannot disagree.
  `make demo` also empties `target/doc/demo/` before copying, so a local
  rebuild leaves no stale chunk (for example the live-data chunk after a
  sample-only build).
- **§12, switch normalised at build time.** `vite.config.ts` `define`s
  `import.meta.env.VITE_WEATHER_LIVE` as `'true'` / `'false'`; the UI
  imports `weather/live.ts` (the only module holding the API hosts,
  through `openmeteo.ts`) dynamically behind that constant, so a
  sample-only build contains no Open-Meteo API host (checked by grep on
  the bundle). Errors and query normalisation live in `errors.ts` so the
  sample path does not pull in the client.
- **§13, tests.** `vitest.config.ts` aliases `@simtest-js/funnel` to
  `packages/sdk/src/index.ts`, so the demo tests need only the SDK's
  wasm glue (`build:wasm`), not its dist build. The setup file both makes
  the global `fetch` throw and fails the test in `afterEach` if it was
  called, so a swallowed error cannot hide a network call. Tests avoid
  Node APIs (the bundled sample and its `ATTRIBUTION.md` are read with
  `?raw`, the SHA-256 with WebCrypto), so no `@types/node` is needed.
- **§14, module layout.** Besides the planned modules: `errors.ts`,
  `search.ts` (debounce and abort, DOM-free), `controller.ts` (shown
  data, loading, error and stale state, DOM-free), `live.ts` (client with
  both caches), `text.ts` (all wording, including the attribution);
  `synthetic.ts` exports its existing `waitForPlotly` for reuse.
- **§6, plot.** No plot title (the one-line answer above states place,
  age and tolerances, and a long title is cut off at phone width); the
  legend sits above the plot, ticks read "9 Nov", hover "9 Nov 2026
  12:00 UTC". The demo has no dark theme, so the weather tab is light
  only like the rest of the page.
