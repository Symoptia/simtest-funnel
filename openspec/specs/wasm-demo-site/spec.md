# wasm-demo-site Specification

## Purpose
The public documentation site: a landing page linking to the repository, the
API references and an interactive demo that runs funnel comparisons in the
browser through the WebAssembly build.

## Requirements

### Requirement: Landing page navigation hub

The site root (`docs/index.html`, deployed to `target/doc/index.html`) SHALL
present a navigation hub instead of redirecting to the Rust API docs. It MUST
link to the GitHub repository (absolute URL) and, using relative paths that
resolve on the deployed site, to the interactive demo at `demo/` and the three
API documentation trees (Rust `simtest_funnel_core/`, Python `python/`, and
JavaScript `js/`).

#### Scenario: Root page lists all destinations
- **WHEN** a visitor opens the site root
- **THEN** the page renders without an automatic redirect
- **AND** it shows working links to the GitHub repository, `/demo`, and the
  Rust, Python, and JavaScript API doc trees

#### Scenario: API docs remain reachable
- **WHEN** a visitor follows the Rust, Python, or JavaScript doc link
- **THEN** the corresponding existing API reference loads as before

### Requirement: Browser demo runs WASM comparison

The site SHALL host an interactive demo at `/demo` that runs the
`@simtest-js/funnel` WASM `compare()` function entirely in the browser using
the deployed static assets. Apart from the static assets and the Plotly CDN
script, the demo SHALL make network requests only in its weather part, only to
the Open-Meteo Geocoding and Previous Runs APIs, and only after a visitor
action.

#### Scenario: Demo loads and computes
- **WHEN** a visitor opens `/demo`
- **THEN** the page loads the two committed CSV files and the WASM module
- **AND** it runs one funnel comparison per signal without a server round-trip

#### Scenario: No third-party data request without a visitor action
- **WHEN** a visitor opens `/demo` or `/demo/#weather` and does not search for
  a place
- **THEN** no request is sent to any host other than the site itself and the
  Plotly CDN

#### Scenario: Weather requests go only to Open-Meteo
- **WHEN** a visitor searches for a place and picks a result
- **THEN** the only additional requests go to
  `https://geocoding-api.open-meteo.com` and
  `https://previous-runs-api.open-meteo.com`

### Requirement: CSV fixtures and signal preprocessing

The demo SHALL load two committed CSV files (`reference.csv` and `test.csv`),
each comma-delimited with a header row `time,x,y,z` and 1001 data rows over
`t ∈ [0, 1]`, fetched with relative URLs so they resolve under `demo/`. It SHALL
split each file into three `(time, value)` signal pairs as a preprocessing step
before comparison.

#### Scenario: Columns split into per-signal pairs
- **WHEN** the demo parses a CSV with columns `time,x,y,z`
- **THEN** it produces three `(time, value)` series — one for x, one for y, and
  one for z — preserving full sample resolution

#### Scenario: Fixtures are reproducible and verified
- **WHEN** the Python test suite runs
- **THEN** a test regenerates the reference and test signals and asserts the
  committed `reference.csv` and `test.csv` contents match

### Requirement: Per-signal funnel comparison outcomes

Using tolerances `atolx = atoly = 0.1`, the demo SHALL compare each test signal
against its reference and surface the funnel result, demonstrating both passing
and failing cases.

#### Scenario: In-tube ripple passes
- **WHEN** the x signal `sin(2πt)` is compared against `sin(2πt) + 0.05·sin(30πt)`
- **THEN** the result status is pass with no reported errors

#### Scenario: Frequency-insensitive comparison passes
- **WHEN** the y signal `cos(2πt)·sin(100t)` is compared against `cos(2πt)·sin(150t)`
- **THEN** the result status is pass because the horizontal tolerance makes the
  tube insensitive to the modulation frequency difference

#### Scenario: Out-of-tube signal fails
- **WHEN** the z signal `sin(4πt)` is compared against `sin(5πt)`
- **THEN** the result status is fail and errors are reported

#### Scenario: Non-pass status displayed as failure
- **WHEN** a comparison returns any status other than pass (a fail or an error
  code such as length mismatch)
- **THEN** the demo displays that signal as failed with its status message
- **AND** only a pass status is shown as passing

### Requirement: Three Plotly funnel plots

The demo SHALL render three separate plots, one per signal, using Plotly loaded
from a CDN and injected through the SDK's `PlotlyLike` interface. Each plot MUST
show the reference, the test, the funnel tube bounds, and the comparison errors.

#### Scenario: Each signal has its own plot
- **WHEN** the demo finishes computing all three comparisons
- **THEN** it displays three distinct plots, each showing reference, test, tube
  bounds, and errors for that signal

#### Scenario: Plot rendering degrades gracefully
- **WHEN** the Plotly CDN script fails to load
- **THEN** the demo still renders each signal's pass/fail status as text
- **AND** a failure in rendering one plot does not prevent the others

### Requirement: Demo included in release deploy

The demo's built output SHALL be assembled into `target/doc/demo/` during the
`publish-docs` release job so it deploys to Cloudflare Pages alongside the API
docs, without changing the existing release gating.

#### Scenario: Demo ships with a release
- **WHEN** the `publish-docs` job runs for a new release
- **THEN** the demo is built and placed under `target/doc/demo/` before
  `wrangler pages deploy`
- **AND** the demo is reachable at `/demo` on the deployed site

### Requirement: Weather part next to the synthetic demo

The demo SHALL offer a "Real weather" part in addition to the existing
synthetic-signal part, which stays the default view and keeps its content and
behaviour. The weather part SHALL be reachable directly through the URL
fragment `#weather`.

#### Scenario: Synthetic part unchanged and shown first
- **WHEN** a visitor opens `/demo`
- **THEN** the synthetic signals x, y and z are shown with their verdicts and
  plots as before
- **AND** a control switches to the weather part

#### Scenario: Direct link to the weather part
- **WHEN** a visitor opens `/demo/#weather`
- **THEN** the weather part is shown

### Requirement: Place search by name

When live data is enabled, the weather part SHALL let a visitor find a place
by typing its name, using the Open-Meteo Geocoding API, and pick one from a
short result list that shows each place's name, first-level region and
country. It SHALL NOT show a map or ask for the visitor's location.

#### Scenario: Debounced search
- **WHEN** a visitor types "Stockh" quickly, one character after another
- **THEN** at most one geocoding request is sent after typing pauses for about
  300 ms, or at once on Enter
- **AND** an earlier search still in flight is abandoned and its answer is not
  shown

#### Scenario: Too short to search
- **WHEN** the trimmed input has fewer than 2 characters
- **THEN** no geocoding request is sent

#### Scenario: Results disambiguate places
- **WHEN** the search for "Stockholm" returns places in Sweden and the United
  States
- **THEN** each entry shows name, region (when given) and country, so
  "Stockholm, Stockholm County, Sweden" and "Stockholm, Maine, United States"
  are distinguishable

#### Scenario: No place found
- **WHEN** the geocoding answer has no `results`
- **THEN** the list says no place was found for the typed text

### Requirement: Weather variable and forecast age

The weather part SHALL let the visitor choose a weather variable from a short
fixed list (temperature at 2 m, precipitation, wind speed at 10 m) and a
forecast age from 1 to 7 days, offering only variables and ages present in the
loaded data.

#### Scenario: Ages for live data
- **WHEN** live data for a place has been loaded
- **THEN** forecast ages 1 to 7 days are offered

#### Scenario: Ages and variable for the sample
- **WHEN** the bundled sample is shown
- **THEN** only temperature and the ages 1, 3 and 5 days are offered

#### Scenario: Changing age needs no request
- **WHEN** the visitor changes the forecast age for a place and variable
  already loaded
- **THEN** results update without a network request

### Requirement: Forecast against latest run

For a chosen place and variable the demo SHALL compare, in the browser, the
forecast made N days ahead (test) against the latest model run (reference) on
hourly data of one pinned model (`ecmwf_ifs`) over a window of the last 14 full
days in UTC that ends before the current day, with time in seconds.

#### Scenario: One request covers all ages
- **WHEN** a visitor picks a place with temperature selected
- **THEN** one Previous Runs request is sent with `models=ecmwf_ifs`,
  `timeformat=unixtime`, explicit `start_date` and `end_date`, and hourly
  `temperature_2m` plus `temperature_2m_previous_day1` to `_previous_day7`
- **AND** `end_date` is the day before the current UTC day and the window spans
  14 days

#### Scenario: Window never reaches into the future
- **WHEN** the visitor's clock is ahead and the answer contains hours later
  than the current time
- **THEN** those hours are left out of the comparison

#### Scenario: Window shown
- **WHEN** results are shown
- **THEN** the page states the compared date range in UTC and the number of
  hours compared

### Requirement: Missing forecast values

The demo SHALL leave out of a comparison every hour where the latest run or
the chosen forecast has no value, and SHALL report a forecast age with fewer
than two remaining hours as having no data instead of giving a verdict.

#### Scenario: Gaps are dropped and reported
- **WHEN** the day-3 series has `null` for 24 of 336 hours
- **THEN** the day-3 comparison uses the remaining 312 hours
- **AND** the result says 24 of 336 hours are missing

#### Scenario: Age without data
- **WHEN** every value of the day-7 series is `null`
- **THEN** day 7 shows "no forecast data" and no verdict

### Requirement: Adjustable value and time tolerance

The weather part SHALL provide a value tolerance and a time tolerance input,
both always visible, filled from presets of the chosen variable and freely
editable, and SHALL show one sentence explaining the time tolerance. A time
tolerance of zero SHALL be accepted.

#### Scenario: Temperature presets
- **WHEN** temperature is selected
- **THEN** the inputs show ±2 °C and ±3 h
- **AND** the comparison uses `atoly = 2` and `atolx = 10800`

#### Scenario: Time tolerance explained
- **WHEN** the weather part is shown
- **THEN** a sentence next to the inputs says that the time tolerance lets a
  forecast that is right but a few hours early or late count as inside the
  tube, and that 0 h checks each hour only against the same hour

#### Scenario: Zero time tolerance
- **WHEN** the visitor sets the time tolerance to 0
- **THEN** the comparison runs with `atolx = 0`

#### Scenario: Both axes always explicit
- **WHEN** any comparison runs in the weather part
- **THEN** both `atoly` and `atolx` are passed, so no library default
  tolerance applies

### Requirement: Weather results with verdict, share outside and plot

For the chosen forecast age the weather part SHALL show the verdict, the share
of compared hours outside the tube and the funnel plot with a UTC date axis;
for all available ages at once it SHALL show a table of verdict and share
outside, computed from the already loaded data.

#### Scenario: Selected age
- **WHEN** results for day 3 are computed
- **THEN** the verdict, the share of hours outside the tube (percentage and
  "k of n hours") and a plot with latest run, forecast, tube bounds and errors
  over dates in UTC are shown

#### Scenario: All ages table
- **WHEN** live data for a place is loaded
- **THEN** a table lists ages 1 to 7 with verdict and share outside
- **AND** selecting a row shows that age's plot

#### Scenario: Results follow tolerance changes
- **WHEN** the visitor edits a tolerance
- **THEN** the verdicts, shares and plot update without a network request

#### Scenario: Plot unavailable
- **WHEN** the Plotly script has not loaded
- **THEN** the verdicts and the table are still shown and the plot area says
  the plot is unavailable

### Requirement: Weather request hygiene

The weather part SHALL send requests without an API key, credentials, cookies
or referrer, send at most one geocoding request per search and one forecast
request per place, variable and window, keep answers in memory for the life of
the page, and store nothing in the browser.

#### Scenario: Repeated choice uses the cache
- **WHEN** a visitor picks Stockholm, switches to another place and picks
  Stockholm again with the same variable
- **THEN** no second forecast request for Stockholm is sent

#### Scenario: Concurrent identical requests shared
- **WHEN** the same forecast is requested twice before the first answer
  arrives
- **THEN** only one request is sent

#### Scenario: Failures are not cached
- **WHEN** a request fails and the visitor tries the same choice again
- **THEN** a new request is sent

#### Scenario: Nothing persisted
- **WHEN** the visitor reloads the page
- **THEN** no earlier search, place or answer is restored from browser storage

### Requirement: Weather error states

The weather part SHALL show a specific message for an unreachable service, a
rate limit (HTTP 429), a refused request (HTTP 400 with its reason), other HTTP
errors, an unexpected answer and a timeout, without breaking the rest of the
page.

#### Scenario: Offline
- **WHEN** a request cannot reach Open-Meteo
- **THEN** a message says Open-Meteo could not be reached and the sample is
  still available

#### Scenario: Rate limited
- **WHEN** Open-Meteo answers 429 with `retry-after: 30`
- **THEN** a message says the rate limit was reached and to try again in 30 s

#### Scenario: Refused request
- **WHEN** Open-Meteo answers 400 with
  `{"error":true,"reason":"End-date must be larger or equals than start-date"}`
- **THEN** the message quotes that reason

#### Scenario: Earlier results kept
- **WHEN** a request fails while results for another place are shown
- **THEN** those results stay visible, marked as not current

### Requirement: Weather data attribution

Wherever weather data is shown, the weather part SHALL show "Weather data by
Open-Meteo.com" linked to Open-Meteo, the CC BY 4.0 licence link, the model
credit (ECMWF IFS), "Location data based on GeoNames" when search is offered, a
note that the latest run is a model analysis and not station measurements, and
a usage note on Open-Meteo's free tier.

#### Scenario: Attribution with live data
- **WHEN** results for a searched place are shown
- **THEN** the attribution line with the Open-Meteo, licence, ECMWF and
  GeoNames credits is visible next to the results

#### Scenario: Attribution with the sample
- **WHEN** the bundled sample is shown
- **THEN** the same Open-Meteo, licence and ECMWF credits are visible together
  with the sample's retrieval date

#### Scenario: What "actual" means
- **WHEN** results are shown
- **THEN** the page says that the reference is the latest model run, not
  measured weather

### Requirement: Offline weather sample

The weather part SHALL open on the repository's bundled Open-Meteo sample
(`examples/open-meteo/`), included in the demo build unchanged, and SHALL be
fully usable on it without network access. It SHALL NOT ship a second copy of
the sample in another format.

#### Scenario: Opens on the sample
- **WHEN** a visitor opens the weather part
- **THEN** results for the Stockholm sample (temperature, day 1, ±2 °C, ±3 h)
  are shown at once and marked as sample data

#### Scenario: Works offline
- **WHEN** the network is unavailable after the page has loaded
- **THEN** the sample comparison, age and tolerance changes and the plot all
  work

#### Scenario: Same numbers as the other APIs
- **WHEN** the demo compares the sample's day-1, day-3 and day-5 forecasts
  with ±2 °C and ±3 h
- **THEN** the shares outside equal those pinned for the same sample and
  tolerances in the MCP server's Open-Meteo walkthrough

### Requirement: Live weather data can be switched off at build time

The demo build SHALL accept a setting that disables live weather data. With it,
the weather part SHALL show only the bundled sample, offer no place search and
contain no request to Open-Meteo.

#### Scenario: Sample-only build
- **WHEN** the demo is built with live data disabled
- **THEN** the weather part shows the sample and a note that live search is
  not available on this site
- **AND** no request to an Open-Meteo host can be triggered from the page

#### Scenario: Default build
- **WHEN** the demo is built without the setting
- **THEN** place search is offered

### Requirement: Demo network policy

The deployed site SHALL serve the demo with a Content-Security-Policy whose
`connect-src` allows only the site itself and, when live weather data is
enabled, the two Open-Meteo API hosts.

#### Scenario: Policy with live data
- **WHEN** `make demo` runs with live data enabled
- **THEN** `target/doc/_headers` contains, for `/demo/*`,
  `Content-Security-Policy: connect-src 'self' https://geocoding-api.open-meteo.com https://previous-runs-api.open-meteo.com`
- **AND** the existing wasm MIME rule is kept

#### Scenario: Policy without live data
- **WHEN** `make demo` runs with live data disabled
- **THEN** the `/demo/*` policy is `connect-src 'self'`

### Requirement: Demo tested without network in CI

The weather part's request building, response parsing, error mapping, caching
and comparison pipeline SHALL be covered by automated tests that never access
the network, and CI SHALL build the demo and run these tests on every push.

#### Scenario: Tests cannot reach the network
- **WHEN** a demo test calls the global `fetch`
- **THEN** the call fails the test instead of reaching the network

#### Scenario: CI builds and tests the demo
- **WHEN** CI runs for a push or pull request
- **THEN** the demo is built (including its type check) and its tests run
- **AND** a failure fails the CI run
