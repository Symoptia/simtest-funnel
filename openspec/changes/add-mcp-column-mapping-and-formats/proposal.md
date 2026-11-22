# Proposal

## Why

The owner wants a public, real example: weather forecasts against what
actually happened, using Open-Meteo data, to answer "was the forecast
made N days ahead close enough?" with a funnel tube (for example ±2 °C
and ±3 h). A trial done by hand (Stockholm, 15 days of hourly
temperature) gives a clear result. Share of points outside the tube for
the forecasts made 1, 3 and 5 days ahead:

| tube              | day 1 | day 3  | day 5  |
| ----------------- | ----- | ------ | ------ |
| ±2 °C, no time    | 2.2 % | 25.3 % | 32.0 % |
| ±2 °C, ±3 h       | 0.6 % | 9.7 %  | 19.5 % |
| ±1 °C, ±3 h       | 5.3 % | 46.8 % | 47.4 % |

The MCP server could not do this trial on its own, for three reasons
that also apply to many other real-world files:

1. **Reference and test are differently named columns, often in one
   file.** The Previous Runs API returns one CSV with `time`,
   `temperature_2m (°C)`, `temperature_2m_previous_day1 (°C)`,
   `temperature_2m_previous_day3 (°C)`, ... side by side. Today
   `compare_signals` and `plot_signals` only compare a column with the
   column of the *same name* in a second file.
2. **A preamble comes before the header.** Open-Meteo CSV starts with a
   metadata block (a `latitude,longitude,elevation,utc_offset_seconds,
   timezone,timezone_abbreviation` line, a line of values and a blank
   line). The server takes the first non-comment line as the header, so
   it reads the metadata as the column names.
3. **Time is a date-time, not a number.** Open-Meteo writes
   `2026-11-20T00:00`; data loggers, building systems and spreadsheets
   write ISO 8601 timestamps too. The server needs numbers for time and
   reports such a column as non-numeric. (Open-Meteo offers
   `timeformat=unixtime` as a workaround; most real files have no such
   option.)

Fetching data from URLs is the fourth gap and is a separate change
(`add-mcp-url-ingestion`), which depends on this one.

## What Changes

- **Column mapping** in `compare_signals` and `plot_signals`: an agent
  can compare a named reference column against a differently named test
  column. Both columns may come from the same file (the test file may be
  the reference file). Several pairs may be compared in one call,
  including one reference column against several test columns
  (`temperature_2m` against day 1, day 3 and day 5).
  - Each result row names both the reference and the test column, and
    rows stay uniquely identifiable when one reference column appears in
    several pairs.
  - Per-column tolerance overrides can be addressed to a pair.
  - The existing same-name selection (`columns` with exact names and
    glob patterns) keeps working unchanged; how it combines with
    explicit pairs is settled in design (see open points).
  - The pytest snippet reproduces mapped comparisons.
- **Preamble before the header**: the reader can skip metadata lines
  before the real header row. The default reading of existing plain CSV
  files does not change (a file whose header is followed by a blank line
  and then data is still read as today).
- **Date-time time columns**: a time column of ISO 8601 date-times is
  accepted and converted to a numeric time axis for the funnel, with a
  defined unit for x tolerances and x-ranges and defined handling of
  time zones (timestamps with an offset, `Z`, or none).
  - Results echo times in a form a person can read as dates, while
    structured content keeps exact values.
  - Time-axis tolerances that make no sense on an absolute date axis
    (for example `ltolx`, which scales with the absolute time value) are
    flagged or refused rather than silently applied.
  - Reference and test with incompatible time columns (for example one
    numeric and one date-time, or one with and one without time zone)
    are reported per file/row, not guessed.
- **`describe_signals` reports what it detected**: preamble lines
  skipped (and, bounded, what they contained), the header line used,
  the time column type (numeric or date-time, with time zone handling),
  and the time start/end as dates when the time column is a date-time.
- Tool descriptions explain the mapping argument, the date-time time
  axis and the unit of x tolerances well enough for an agent to turn
  "±2 °C and ±3 hours" into the right call.
- Plain CSV files with a numeric time column and the header on the
  first non-comment line give exactly the results they give today.

Explicitly out of scope:

- Fetching from URLs and the Open-Meteo example files
  (`add-mcp-url-ingestion`).
- Files with several locations or entities stacked in one CSV (for
  example Open-Meteo's multi-location layout with a `location_id`
  column): one file holds one shared time axis.
- Time formats other than ISO 8601 (locale formats such as `01/02/2026`,
  Excel serial dates), and user-supplied `strftime` formats.
- Other delimiters, encodings and file formats.
- Unit conversion between columns (both columns of a pair are compared
  as given; units in names such as `(°C)` are just part of the name).
- Pattern-based renaming between reference and test (for example
  `plant.*` against `model.*` across many columns); possibly a later
  change, once the explicit mapping exists.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities

- `mcp-server`: column selection gains explicit reference/test column
  pairs (including one file); the CSV dialect gains preamble skipping;
  the time column may be an ISO 8601 date-time; `describe_signals`
  reports the header line, skipped preamble and time column type;
  structured and text output echo date-time times; the snippet covers
  the new options.
- `mcp-plots`: `plot_signals` can plot one reference column against a
  differently named test column, from one or two files, on a date-time
  time axis.

## Impact

- `python/simtest-funnel-mcp`: `reader.py` (embedded verbatim in
  generated snippets, so snippets grow accordingly), `csvio.py`,
  `selection.py`, `compare.py`, `describe.py`, `plot.py` (date axis
  labels), `models.py` (output schemas), `server.py` (arguments and
  tool descriptions), `snippet.py`, README, tests.
- Additive tool arguments and output fields; no change for existing
  callers and existing files. No change to the Rust core or the other
  bindings: the funnel still receives float64 time values.
- Should land after `add-cancellation` or be merged with care: that
  change also adds arguments to `compare_signals` and `plot_signals`
  and touches the same modules.
- Prerequisite of `add-mcp-url-ingestion` (its Open-Meteo example needs
  all three parts).
- Open points for design:
  - **Shape of the mapping argument.** A list of pairs
    (`[{"reference": "...", "test": "...", "label": ...}]`) next to
    `columns`, a `"ref=test"` string syntax inside `columns`, or a
    single `test_column` for `plot_signals` plus pairs for
    `compare_signals`; whether pairs and `columns` may be combined in
    one call; whether `test_path` becomes optional (defaulting to the
    reference file) when both columns are in one file.
  - **Row identity and overrides.** What a row's `column` field holds
    for a pair (test column, label, or `ref -> test`), and what keys
    `column_tolerances` uses for pairs.
  - **Globs in pairs.** Exact names only, or patterns on the test side
    (`temperature_2m_previous_day*`) against one reference column.
  - **Preamble: auto-detection versus explicit option.** An explicit
    header-line / skip-lines argument on all three tools, a
    conservative auto-detection (for example: a block, a blank line,
    then a block whose first line is not data), or both; how a wrong
    guess is made visible.
  - **What `describe_signals` echoes from a preamble** (line count only,
    or a bounded key/value view such as Open-Meteo's
    `utc_offset_seconds`).
  - **Date-time detection.** Automatic (every non-empty time cell
    parses as ISO 8601) or an explicit `time_format` option; which ISO
    8601 forms are accepted (seconds optional, space instead of `T`,
    fractional seconds, date only).
  - **Numeric x for date-times and the unit of x tolerances.** Seconds
    since the Unix epoch (so an ISO file and its `unixtime` twin give
    identical results) or seconds since the reference start (smaller
    numbers); x tolerances and `x_range` in seconds only, or also
    duration strings such as `"3h"` / `"PT3H"` and ISO date-times in
    `x_range`.
  - **Time zones.** Whether timestamps without an offset are taken as
    UTC (flagged as "no time zone") or as unknown wall-clock time that
    may only be compared with another zone-less column; what happens
    with local times across a daylight-saving change (repeated or
    missing hours).
  - **`ltolx` and default `rtolx` on date axes.** Refuse a non-zero
    `ltolx` on a date-time axis or only warn; state the resolved default
    `rtolx` (0.2 % of the reference span, about 43 minutes for 15 days)
    in seconds so the hidden time tolerance is visible.
  - **How results echo times.** Numeric values plus ISO 8601 strings in
    structured content, ISO only in the text rendering, or both.
