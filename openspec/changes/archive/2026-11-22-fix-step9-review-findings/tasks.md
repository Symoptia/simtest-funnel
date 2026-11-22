# Tasks

## 1. Core: window extension (finding 1)

- [x] 1.1 Add `CornerObserver` / `CornerTrace` to `corners.rs` (no-op observer for the plain comparison). Verify corpus parity and the differential tests unchanged (`cargo test --workspace --features simtest-funnel-core/json`).
- [x] 1.2 Add `window.rs`: initial extension (former margin), the synchronization check (firm corner point, pairs of consecutive common gap corners on both sides, bounds from monotone reach), geometric growth, whole reference beyond half of it; wire into `compare.rs`. Verify `cargo test -p simtest-funnel-core`.
- [x] 1.3 Regression tests from the reviewer's dumped cases, collinear-run and constant-reference extension tests, bit-identity in the property tests, port of the reviewer's harness as `adversarial_windows_match_full_range_bit_for_bit`. Verify each fixture fails at 41882ff and passes now.
- [x] 1.4 Run the differential harnesses at scale against 41882ff: the reviewer's original harness (6 seeds × 25 000 cases: 624 489 windows) and the extended one (14 distinct seeds × 20 000 cases: 1 133 000 windows): 0 verdict flips, 0 bit differences in judged deviations, 0 parity differences without x-range.
- [x] 1.5 Update rustdoc (`compare` module, `window` module with the argument), the core, Python, SDK, MCP and root READMEs and the `compare_signals` description to state the guarantee and its assumption.

## 2. MCP server (findings 2-11)

- [x] 2.1 Always pass the URL host as `server_hostname`; turn any TLS-layer exception into a `FetchError`. Tests: IP-literal fetch (certificate with the 127.0.0.1 entry, and one without), injected failing context.
- [x] 2.2 Stop quoting error bodies; standard status phrase, content type, sanitised and bounded JSON `reason`. Document untrusted content and the host-name DNS channel in the README, server instructions and INPUT FILES text. Tests: text/HTML bodies not quoted, hostile JSON reason sanitised, instructions wording.
- [x] 2.3 Refuse a pair (and a plot) of one column with itself in the same loaded file. Tests in `test_mcp_compare.py` and `test_mcp_plot.py`.
- [x] 2.4 ASCII digits only in `ISO_DATETIME` and the tail pattern of `parse_iso`. Tests with fullwidth, Arabic-Indic and Devanagari digits (cells and x-range bounds).
- [x] 2.5 Explicit deny-list beside `is_global` (`fec0::/10`, `5f00::/16`, ...); bounded lookup in a helper thread. Tests: new refused addresses, slow resolver with timeout and with cancellation (late answer unused).
- [x] 2.6 Count bytes of downloads in progress toward the cache bound, limit concurrent downloads, cap `_seen`. Tests in `test_mcp_urlcache.py`.
- [x] 2.7 Snippet download: final URL, no redirects, identity encoding, overall deadline (`read1`), exclusive link/create. Tests: redirect refused, final URL with identity, deadline.
- [x] 2.8 CSV timing test at 100 000 rows with best of three and absolute slack.
- [x] 2.9 Align the `x_range` argument and plot descriptions with compare's and with D1. Test: both argument descriptions.
- [x] 2.10 Accept NUL padding after gzip members only; split preamble-hint lines at CR too; skip `test_mcp_examples.py` without the sample. Tests: padding, junk after padding, CR-only preamble file.
- [x] 2.11 Verify `make build`, `make lint`, `make test` and `openspec validate fix-step9-review-findings --strict`.
