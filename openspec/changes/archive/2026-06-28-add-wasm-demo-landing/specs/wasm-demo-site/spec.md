## ADDED Requirements

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
the deployed static assets.

#### Scenario: Demo loads and computes
- **WHEN** a visitor opens `/demo`
- **THEN** the page loads the two committed CSV files and the WASM module
- **AND** it runs one funnel comparison per signal without a server round-trip

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
