# Tasks

All paths are under `python/simtest-funnel-mcp/` unless stated otherwise.

## 1. Prerequisite

- [ ] 1.1 Confirm `zero-default-x-tolerance` has landed: `resolve_with_library({})` in `compare.py` returns `atolx = ltolx = rtolx = 0` and `rtoly = 0.002`; verify with a one-line pytest in `tests/test_mcp_compare.py` that fails if a non-zero default x tolerance comes back

## 2. Reader: header line and date-time time column

- [ ] 2.1 `src/simtest_funnel_mcp/reader.py` (embedded in snippets): add `header_line` (physical 1-based line; lines before it skipped unread; header = first non-blank, non-`#` line at or after it; error naming the line count when none), keep physical line numbers in the "data row N (line L)" error, and move the time-column rule from `csvio.choose_time_column` into the reader; return a named tuple (header, values, time column, time column rule, time kind, zone kind, header line used); verify existing `tests/test_mcp_csv.py` passes unchanged with the default
- [ ] 2.2 In `reader.py`, detect and convert an ISO 8601 time column (design §4: regex over non-empty cells, date-only allowed, `Z` / `±hh[:mm]` / `±hhmm` offsets converted to UTC, zone-less read as UTC, invalid dates or `24:00` not matching; epoch seconds built as the decimal string `"<int>.<fraction>"` and parsed with the same numeric parser); report mixed-offset columns and partly matching columns as described in design §4; verify new tests in `tests/test_mcp_csv.py`: each accepted form, `2026-11-20T00:00:00.25Z` == `1795132800.25` bit for bit, `+01:00` conversion, mixed offsets, partly ISO column, years 0001 and 9999, a 1M-row ISO file reads within a small multiple of the numeric read time
- [ ] 2.3 `src/simtest_funnel_mcp/csvio.py`: thread `header_line` through `load_csv`, add `header_line`, `time_kind`, `time_zone` to `SignalFile`, extend `time_problems()` (no time zone, mixed offsets, partly ISO); add the preamble-candidate scan and hint text (design §3) appended to `SignalFileError` messages and exposed as `SignalFile.hints` for successful reads; read a file once when reference and test resolve to the same path and header line; verify tests with a synthetic Open-Meteo-shaped fixture (metadata line, values line, blank line, header with `(°C)` names, `2026-11-20T00:00` times): read with header line 4, hint without it (both the failing and the padded-successful read), no hint on a plain file with a blank line after the header, header line past the end
- [ ] 2.4 New `src/simtest_funnel_mcp/timeaxis.py`: ISO formatting of epoch seconds (UTC `Z` for offset axes, no suffix for zone-less, fraction only when non-zero), ISO 8601 durations (`PT3H`, `P14DT23H`, `PT3H35M24S`, `PT0.5S`), parsing of ISO x-range bounds with the zone rule; verify unit tests in a new `tests/test_mcp_timeaxis.py`

## 3. describe_signals

- [ ] 3.1 `src/simtest_funnel_mcp/models.py` and `describe.py`: add `DescribeResult.header_line`, `TimeInfo.kind`, and for date-time axes `time_zone`, `start_iso`, `end_iso`, `span_duration`, `Sampling.median_step_duration`; the uniform-sampling tolerance `max(1e-6 * median, 4 * spacing(max|t|))` for date-time axes only; the "no time zone" problem; the >6-fraction-digit resolution note; preamble hints as problems; verify `tests/test_mcp_describe.py` covers the Open-Meteo fixture (header line 4, kind datetime, zone none, start/end numbers and ISO strings, `PT1H` uniform), 0.1 s ISO data reported uniform, and numeric files giving exactly the previous result plus `header_line = 1` and `kind = numeric`
- [ ] 3.2 `src/simtest_funnel_mcp/render.py` `render_describe`: header line, ISO start/end and durations on date-time axes; verify text snapshots in `tests/test_mcp_describe.py`

## 4. compare_signals: pairs and date-time axis

- [ ] 4.1 `models.py`: `ColumnPair` input model (`reference`, `test`, optional `label`, extra forbidden); `XRange.lo/hi` as `float | str` with strings validated against the ISO pattern at model level (so `"-inf"` stays a validation error); `Row` and `NotCompleted` gain `reference_column` / `test_column`; `ToleranceSetOut` and `Row` gain `time_tolerance {seconds, duration}`; `FileInfo` gains `header_line`, `time_kind`, `time_zone`, `time_start_iso`, `time_end_iso`; `RangeOut` gains `lo_iso` / `hi_iso`; `Worst.x_iso`; `Interval.start_x_iso` / `end_x_iso` / `worst_x_iso`; verify the published output schema test in `tests/test_mcp_server.py` lists the new optional fields
- [ ] 4.2 `src/simtest_funnel_mcp/compare.py` `run_compare`: accept `pairs` (mutually exclusive with `columns`, empty list refused), build an internal list of (key, reference column, test column), key uniqueness check with the clash error, `_column_problem` per side with `difflib` close-name suggestions and the "pairs take exact names" hint, `ref.values[ref_col]` against `tst.values[test_col]`, overrides keyed by the row key, `columns_only_in_*` only for the default selection; same-name selection produces exactly the previous rows; verify new tests in `tests/test_mcp_compare.py`: one reference against day1/day3/day5 in one file with two sets (six rows), override by label and by test column, clashing keys, pairs plus columns refused, glob in a pair, unit-suffix suggestion, time column in a pair, existing compare tests unchanged
- [ ] 4.3 `compare.py`: time-axis compatibility check (numeric vs date-time, zone-less vs offset) failing the call with both files named; non-zero `ltolx` refused on date-time axes (sets and overrides); `time_tolerance` from `max(atolx, rtolx * reference span within x_range)`; ISO x-range bounds converted with the zone rule (refused on numeric axes); ISO siblings filled in `FileInfo`, `RangeOut`, `Worst`, `Interval`; preamble hints from `SignalFile.hints` as notes; verify tests: ISO file and its unixtime twin give identical `CompareResult` numeric fields, `atolx = 10800` forgives a 2 h shift that `atolx = 0` flags, `rtolx = 0.01` on 15 days echoes 12924 s / `PT3H35M24S`, `ltolx = 0.001` refused and `ltolx = 0` accepted, zone-less vs `Z` refused, numeric vs ISO refused, ISO x-range on zone-less and offset axes, ISO bound on a numeric axis refused, zero x tolerance on epoch-second data and on the same data shifted to 0 give the same status and counts
- [ ] 4.4 `render.py` `render_compare` / `_row_line`: pair rows show `key (reference -> test)` when names differ, ISO times and durations on date-time axes, time tolerance per set; verify text tests in `tests/test_mcp_compare.py` (interval `t=2026-11-20T03:00:00..2026-11-20T07:00:00`; numeric output unchanged)

## 5. Snippet

- [ ] 5.1 `src/simtest_funnel_mcp/snippet.py`: `REFERENCE_HEADER_LINE` / `TEST_HEADER_LINE`, `TEST = REFERENCE` for one file, case tuples `(key, reference_column, test_column, label, tolerances, status)`, the test indexing each side by its own column, ISO x-range bounds written as epoch seconds with the ISO form in a comment, the updated embedded reader; verify `tests/test_mcp_snippet.py` runs generated snippets with pytest for the one-file Open-Meteo pair comparison, a two-file comparison with different header lines, and the existing same-name cases (all pass, status codes reproduced)

## 6. plot_signals

- [ ] 6.1 `src/simtest_funnel_mcp/plot.py` `prepare_plot`: optional `test_column` (default `column`, glob refused like `column`), compare via one pair, legend "reference: ..." / "test: ...", title naming both columns when they differ, subtitle `x ±PT3H` on date-time axes; verify `tests/test_mcp_plot.py`: the pair plot row equals the `compare_signals` pair row, test column omitted behaves as before, glob test column refused
- [ ] 6.2 `plot.py` `render`: date-time tick locator and formatter on epoch-second x data (design §11), x label `<time column> (UTC)` / `(no time zone)`; `PlotResult.view` ISO siblings; verify SVG/PNG determinism tests still pass, a date-axis plot shows date tick labels (SVG text check), and the drawn-tube agreement tests pass on a date-time fixture

## 7. Server, descriptions and docs

- [ ] 7.1 `src/simtest_funnel_mcp/server.py`: `header_line` on `describe_signals`; `pairs`, optional `test_path`, `header_line`, `test_header_line` on `compare_signals`; optional `test_path`, `test_column`, `header_line`, `test_header_line` on `plot_signals`; impls resolve the default test path and refuse "no test path and no pairs"; verify `tests/test_mcp_server.py` (tool schemas list the arguments with `header_line` minimum 1, one-file call works in process) and one stdio call in `tests/test_mcp_stdio.py`
- [ ] 7.2 Update `INSTRUCTIONS`, `CSV_HELP`, `DESCRIBE_DESCRIPTION`, `COMPARE_DESCRIPTION` and `PLOT_DESCRIPTION`: pairs and row key, optional test path, header line and preamble hint, date-time axis in epoch seconds, UTC rule, ISO x-range, `ltolx` refused, worked example "±2 °C and ±3 hours" = `{"atoly": 2, "atolx": 10800}`; verify a description test asserts these phrases and that described fields exist in the output schema
- [ ] 7.3 Update `python/simtest-funnel-mcp/README.md` (pairs, header line, date-time times, time zones, an Open-Meteo-shaped example call) and verify the documented example call runs against the test fixture

## 8. Integration checks

- [ ] 8.1 Run `make lint` (including `mypy --strict` on the MCP package and tests), `make test-python` and `openspec validate add-mcp-column-mapping-and-formats --strict`, and verify all pass with no diff under `crates/` or `packages/`

## Workflow follow-up

- Archive the change after review, after `zero-default-x-tolerance` has been archived (both touch the `mcp-server` spec).
- `add-mcp-url-ingestion` can then build its Open-Meteo example on this change.
