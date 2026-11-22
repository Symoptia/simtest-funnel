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

- **Column pairs** in `compare_signals`: a new argument
  `pairs: [{reference, test, label?}]` compares a named reference
  column against a differently named test column. Several pairs may be
  given, including one reference column against several test columns
  (`temperature_2m (°C)` against the day 1, day 3 and day 5 columns).
  - `pairs` and `columns` are mutually exclusive in one call.
  - `test_path` becomes optional and defaults to the reference file, so
    both columns of a pair may come from one file.
  - Pairs take exact column names only; glob patterns stay with
    `columns`.
  - Each result row carries both column names. A row is keyed by the
    pair's label when given, else by its test column; per-column
    tolerance overrides use the same key.
  - The existing same-name selection (`columns` with exact names and
    glob patterns, or no selection) is unchanged.
  - The pytest snippet reproduces pair comparisons.
- **Column pairs** in `plot_signals`: an optional test column name (the
  reference column keeps its existing argument) and an optional test
  path (default: the reference file).
- **Header line**: `describe_signals`, `compare_signals` and
  `plot_signals` take an explicit `header_line` (1-based file line of
  the header row; the default 1 reads files exactly as today). There is
  no auto-detection. When reading fails or the header looks wrong and
  the top of the file looks like a preamble (for example a blank line
  before a later line that looks like a header row), the error or
  problem text says so and suggests the likely `header_line`.
  `describe_signals` echoes the header line used.
- **Date-time time columns**: a time column whose cells all parse as
  ISO 8601 date-times (seconds optional, `T` or space, fractional
  seconds, optional `Z` or offset) is detected automatically.
  - The numeric time is seconds since the Unix epoch, so an ISO file and
    its `unixtime` twin give identical results. x tolerances are in
    seconds (±3 h is `atolx = 10800`).
  - Results echo times both as numbers and as ISO 8601 strings, and the
    text rendering shows dates; `x_range` also accepts ISO strings.
  - A non-zero `ltolx` on a date-time axis is refused (relative to about
    1.7e9 epoch seconds it is meaningless). An explicit `rtolx` is
    allowed; its resolved half-width is echoed in seconds and as a
    duration.
  - A timestamp without an offset is read as UTC and
    `describe_signals` flags the column as having no time zone.
    Comparing a zone-less time column against one with offsets, or a
    numeric time column against a date-time one, is refused with an
    explanation; two zone-less columns compare fine (a constant offset
    cancels).
- **`describe_signals` reports what it read**: the header line used, the
  time column kind (numeric or date-time, with or without time zone),
  and for a date-time column its start and end as dates and its span
  and steps as durations.
- Tool descriptions explain pairs, `header_line`, the date-time time
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
- Reading EnergyPlus EPW / IWEC2 weather files directly (no
  column-name row, separate Year/Month/Day/Hour/Minute columns, hours
  1-24, non-continuous years).
- Time formats other than ISO 8601 (locale formats such as `01/02/2026`,
  Excel serial dates), a `time_format` option, user-supplied `strftime`
  formats and duration strings (`"3h"`, `"PT3H"`) as tolerance input.
- A `time_zone` argument (zone-less timestamps are always read as UTC).
- Auto-detection of the header line.
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
  pairs (including one file, with `test_path` optional); the CSV
  dialect gains an explicit header line and a preamble hint; the time
  column may be an ISO 8601 date-time (epoch seconds, time zone rules,
  `ltolx` refused, ISO `x_range` bounds); `describe_signals` reports the
  header line and time column kind; structured and text output echo
  date-time times; the snippet covers the new options.
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
  callers and existing files, except that the generated snippet's case
  tuples gain the reference and test column names. No change to the Rust core or the other
  bindings: the funnel still receives float64 time values.
- **Depends on `zero-default-x-tolerance`**, which makes the default x
  tolerance zero in all APIs (the default y tolerance stays
  `rtoly = 2e-3`). Without it, a date-time comparison without explicit
  x tolerance would get a hidden time tolerance of 0.2 % of the span
  (about 43 minutes for 15 days). This change lands after that one.
- `add-cancellation` has landed; this change builds on its `time_limit`
  and worker-thread structure in `compare.py`, `plot.py` and
  `server.py`.
- Prerequisite of `add-mcp-url-ingestion` (its Open-Meteo example needs
  all three parts).

## Decisions

Decided by the owner (binding for design and specs):

1. **Column pairs**: `pairs: [{reference, test, label?}]` on
   `compare_signals`, mutually exclusive with `columns`; `test_path`
   optional, defaulting to the reference file; `plot_signals` gains a
   way to name a different test column; exact names only in pairs; rows
   carry both column names; overrides key on the label if given, else
   the test column.
2. **Preamble**: explicit `header_line` only (1-based, default 1 =
   today's behaviour), no auto-detection; a preamble hint with the
   likely `header_line` in error messages; `describe_signals` takes the
   same argument and echoes the header line used. Rationale: explicit
   skip counts are the standard mechanism (pandas `skiprows` / `header`,
   W3C CSV on the Web `skipRows`); the Open-Meteo CSV layout is not
   documented in its API docs, so a heuristic tuned to it would be
   fragile.
3. **Date-time time columns**: detected automatically when every time
   cell parses as ISO 8601 (seconds optional, `T` or space, fractional
   seconds, optional `Z` / offset); numeric x is seconds since the Unix
   epoch; x tolerances in seconds; results echo the number and an ISO
   string; `x_range` also accepts ISO strings; no duration strings and
   no `time_format` option.
4. **Default x tolerance**: zero, changed separately in all APIs by
   `zero-default-x-tolerance`; a non-zero `ltolx` on a date-time axis is
   refused; an explicit `rtolx` is allowed and echoed in seconds and as
   a duration.
5. **Time zones**: no offset means UTC, flagged by `describe_signals`;
   zone-less against offset is refused; both zone-less is fine; no
   `time_zone` argument.
6. **Out of scope** as listed above (EPW / IWEC2, stacked multi-location
   CSVs, non-ISO time formats, other delimiters, unit conversion).

design.md works out the remaining details (argument names and JSON
shapes, matching rules, error wording, output fields) and marks each as
a design choice not yet confirmed by the owner.
