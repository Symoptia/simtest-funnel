# Design

## Context

See proposal.md (Why, Decisions) for motivation and the owner's binding
decisions, and the spec deltas for the required behaviour. Relevant
current state of `python/simtest-funnel-mcp/src/simtest_funnel_mcp/`:

- `reader.py` is embedded verbatim in generated snippets.
  `read_signal_columns(path)` strips a BOM, drops blank and `#` lines,
  takes the first remaining line as the header, reads the rest with
  pandas as strings and coerces **every** column with `pd.to_numeric`
  (non-numeric cells become NaN). Duplicate or empty header names fail
  the file. Rows with fewer fields than the header are padded silently.
- `csvio.py` chooses the time column (`time` case-insensitively, else
  the first column) after reading and builds `SignalFile` (float64
  values, bad-cell counts, `time_problems()`).
- `selection.py` expands exact names and globs; `compare.run_compare`
  works on one name per row: `_column_problem(name, ref, tst)`,
  `ref.values[c]` against `tst.values[c]`, overrides keyed by `c`,
  `RowRecord` / `Row.column` / `NotCompleted.column` hold that name.
- `plot.prepare_plot` calls `run_compare(columns=[column])` and labels
  the axes with the reference time column and the column name.
- `snippet.py` writes `CASES = [(column, label, Tolerances, status)]` and
  a test that indexes both files with the same `column`.
- `models.py`: `XRange.lo/hi` are `float | None`; output times are plain
  floats (`FileInfo.time_start/end`, `Worst.x`, `Interval.*_x`,
  `RangeOut`, describe `TimeInfo`). `server._trim` never rounds time
  fields; `render.time_digits` picks significant digits for times.
- The default x tolerance is being changed to zero in all APIs by
  `zero-default-x-tolerance`; this change assumes it has landed.

## Goals / Non-Goals

**Goals:**

- Open-Meteo's Previous Runs CSV (preamble, unit-suffixed names, ISO
  times, reference and test in one file) works with explicit, visible
  arguments and no guessing.
- An ISO file and its `unixtime` twin give bit-identical comparisons.
- Existing calls on existing files give identical results; existing
  output fields keep their meaning.
- The snippet stays self-contained: the embedded reader does the header
  line and date-time handling itself.

**Non-Goals:**

- No change to the Rust core or the Python / WASM bindings.
- No time zone database (no `zoneinfo`): only UTC and fixed offsets.
- No `time_format`, duration strings, header auto-detection (proposal,
  Decisions).

## Decisions

Items marked **(design choice, not yet confirmed by the owner)** are
this design's answer to something the owner's decisions leave open;
each lists the recommendation and the main alternative.

### 1. Argument names and JSON shapes (design choice, not yet confirmed by the owner)

`compare_signals`:

```json
{
  "reference_path": "/data/stockholm.csv",
  "header_line": 4,
  "pairs": [
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day1 (°C)", "label": "day1"},
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day3 (°C)", "label": "day3"}
  ],
  "tolerances": [{"label": "2C_3h", "atoly": 2, "atolx": 10800}],
  "column_tolerances": {"day3": {"atoly": 3}},
  "x_range": {"lo": "2026-11-05T00:00", "hi": "2026-11-19T23:00"}
}
```

- `pairs`: list of `{reference: str, test: str, label?: str}` (all
  non-empty, extra keys forbidden). An empty list is an argument error,
  like an empty `columns`.
- `test_path`: optional; omitted means the reference file.
- `header_line` (int ≥ 1, default 1) for the reference file and
  `test_header_line` (int ≥ 1) for the test file. `test_header_line`
  defaults to `header_line`: the common cases are one file, or two files
  from the same source. Alternative: one `header_line` for both (cannot
  express a preamble file against a plain file) or required separate
  values (verbose for the one-file case).
- `x_range.lo` / `hi`: number or ISO 8601 string.

`plot_signals`: `column` stays the reference column; new optional
`test_column` (default: `column`), optional `test_path` (default: the
reference file), `header_line`, `test_header_line`. Alternative: a
`pair` object like one entry of `pairs`; rejected because it would make
`column` redundant or conflicting and break the existing argument shape.

`describe_signals`: new `header_line` (int ≥ 1, default 1).

### 2. Header line semantics (design choice, not yet confirmed by the owner)

`header_line` counts physical lines of the file (1-based, after a BOM,
any line ending). Lines before it are skipped unparsed, whatever they
contain. The header is the first line **at or after** `header_line`
that is neither blank nor a `#` comment; after it, blank and comment
lines are skipped as today.

- This makes the default 1 exactly today's behaviour ("first
  non-comment line"), also for files starting with comments, which a
  literal "line 1 is the header" would break. This is the reading of the
  owner's "default 1 = today's behaviour".
- For Open-Meteo, `header_line = 4` (line 3 is blank; 3 would also work).
- `header_line` past the end of the file, or with no header line at or
  after it, fails the file with an error naming the line count.
- Data row line numbers in errors stay physical file lines.
- Alternative: strict (line N must be the header, blank or comment is an
  error). Safer against off-by-one, but breaks the default for files
  with leading comments.

### 3. Preamble hint (design choice, not yet confirmed by the owner)

Reading never changes because of the hint; it only adds text. A
**preamble candidate** is the first line L after the header line used,
within the first 100 physical lines, such that:

1. the physical line before L is blank;
2. L has at least two fields, none of which is a number or an ISO 8601
   date-time;
3. the next non-blank, non-comment line after L has the same number of
   fields as L and at least one field that is a number or an ISO 8601
   date-time (it looks like data).

The hint is given when a candidate exists **and** either reading the
file failed (too many fields, duplicate or empty header names, no data),
or the read succeeded but the header used has a different field count
than L, or the time column has a problem cell (a non-numeric, empty or
non-finite cell, or mixed time zones).

*Changed during implementation:* the last condition originally read "the
time column is unusable (no numeric or date-time cell)". An Open-Meteo
file whose header row has exactly six fields reads with the metadata line
as header, so the time column (`latitude`) holds one number (the metadata
value) and 360 ISO cells: it has a numeric cell, so the original condition
would not fire, and the field counts are equal. Any bad time cell is
enough of a signal together with a preamble candidate; a plain file never
has a candidate (its later lines contain numbers).
Where it appears:

- read failure: appended to the error of the failing call (all three
  tools);
- successful read: a `problems` entry in `describe_signals` and a note
  in `compare_signals` / `plot_signals` results.

Wording (quoted lines truncated to 80 characters):

> `<path>: data row 3 (line 5) has 4 fields, header has 6. The file seems
> to start with a preamble: line 3 is blank and line 4
> ('time,temperature_2m (°C),temperature_2m_previous_day1 (°C),...')
> looks like a header row. If it is, pass header_line=4.`

> `header taken from line 1 ('latitude,longitude,elevation,...'), but the
> file seems to start with a preamble: line 3 is blank and line 4
> ('time,temperature_2m (°C),...') looks like a header row; if it is,
> pass header_line=4`

Header and preamble text are metadata, not samples, so quoting them is
allowed; data lines are never quoted. Alternative: hint only on read
failure. Rejected: Open-Meteo with a short header usually *reads*
(rows narrower than the 6-field metadata header are padded), so the
hint must also fire on a successful but implausible read.

### 4. Date-time detection and conversion (design choice, not yet confirmed by the owner, for the details below)

Only the chosen time column is examined (signal columns stay numeric;
date-time cells there are non-numeric as today). The column is a
date-time column when it has at least one non-empty cell and **every
non-empty** cell matches

```
YYYY-MM-DD[(T| )hh:mm[:ss[.f+]][Z|±hh[:mm]|±hhmm]]
```

- Date-only cells (`2026-11-20`, midnight, zone-less) are accepted:
  Open-Meteo daily data uses them. Confirmed by the owner, also in a
  column that mixes dates and date-times. (One switch in `reader.py`,
  `ACCEPT_DATE_ONLY`, makes the time part mandatory.)
- Upper-case `T` and `Z` only; `.` as decimal mark; hour 00-23 (no
  `24:00`), no leap second `:60`; invalid dates (`2026-02-30`) make the
  column not a date-time column.
- Empty cells do not prevent detection; they are counted as bad cells
  as today (the time column then has a problem).
- A column where some non-empty cells match and others do not stays
  numeric (non-numeric problem as today, so its non-numeric count includes
  the ISO cells), and the problem text adds "N of M non-empty cells are
  ISO 8601 date-times (first other value at line L)" without quoting
  sample values.
- A column that mixes cells with and without offset is a time problem
  ("mixes timestamps with and without a time zone"); rows of such a file
  are errors, like a non-monotonic time column.

Conversion is vectorised: validity via pandas `str.fullmatch`, the
fixed-position fields (date, hour, minute, second) read from a NumPy
code-point view of the cells, a regex only for the variable tail
(fraction, zone) of the cells that have one, days from the civil date by
integer arithmetic (Hinnant's `days_from_civil`, which also validates the
day of the month), integer seconds and offsets. *Changed during
implementation:* the planned `str.extract` over all groups plus
`datetime64[D]` took 4x the numeric read on 1M rows (`str.extract` alone
3 s); this form takes about 1.6-1.8x. To make an ISO file and its `unixtime` twin bit-identical, the
float is produced by parsing the decimal string
`"<integer epoch seconds>.<fraction digits>"` with the same numeric
parser the numeric path uses, so `2026-11-20T00:00:00.25Z` and
`1795132800.25` give the same float64 (a single correctly rounded
conversion, never `int + float(fraction)`). Years 0001-9999 are
supported (no int64-nanosecond limit).

### 5. Float precision of epoch seconds

At |t| ≈ 1.7e9 s an f64 has a spacing of 2^-22 s ≈ 0.24 µs.

- Whole-second and millisecond timestamps are represented to within
  0.12 µs; adjacent samples 1 µs apart stay distinct; anything finer
  than about 0.25 µs is lost. When a time cell has more than 6 fraction
  digits, `describe_signals` notes that resolution below about 0.25 µs is
  lost (design choice, not yet confirmed by the owner). This is no worse
  than a numeric epoch-seconds file today.
- Step jitter: consecutive steps of sub-second data differ by up to
  ~0.5 µs, so the uniform-sampling test (`UNIFORM_RTOL = 1e-6` of the
  median step) would call 0.1 s data non-uniform. The tolerance becomes
  `max(1e-6 * median step, 4 * spacing(max|t|))` on **every** time axis,
  numeric and date-time (decided by the owner): a numeric epoch-seconds
  file and its ISO twin are described identically. For small times (e.g.
  simulation time from 0) `4 * spacing` is far below `1e-6 * median step`,
  so they are reported exactly as before; only large numeric times (e.g.
  sub-second epoch data, previously non-uniform) change.
- The 1e-10 tube floor: with zero x tolerance the library floors the
  half-width to 1e-10 s, below the f64 spacing at 1.7e9, so
  `t ± half_x == t` exactly: the x tube has zero width and the
  comparison is a pure value comparison at the sample times. The
  library's degenerate-segment threshold (1e-10) never merges distinct
  epoch samples (they differ by ≥ 0.24 µs). This matches what a
  numeric epoch file does today; a test pins it (zero x tolerance on
  epoch data and on the same data shifted to start at 0 give the same
  status and counts).
- x tolerances meant in seconds are well above the spacing (1 ms ≫
  0.24 µs), so they behave as on a small time axis.

### 6. Time zones and compatibility (design choice for the details, not yet confirmed by the owner)

- Each date-time column has a zone kind: `offset` (every cell has `Z` or
  an offset; values converted to UTC) or `none` (no cell has one; read
  as UTC). Fixed offsets may differ between cells (daylight saving
  written as `+01:00` / `+02:00` converts correctly).
- Zone-less local times across a daylight-saving change can repeat an
  hour; read as UTC that is time going backwards, reported by the
  existing "not non-decreasing" problem. No special handling.
- Incompatible reference and test time axes fail the call (not per
  row: the time axis is shared by every row): numeric against
  date-time, and `none` against `offset`. The error names both files,
  their time columns and kinds, and says how to fix it (e.g. "write both
  with offsets, or both without").
- ISO `x_range` bounds follow the axis: allowed only on a date-time
  axis; a zone-less bound on a zone-less axis, a bound with `Z` / offset
  on an offset axis; otherwise an argument error. Numeric bounds are
  always accepted as epoch seconds.

### 7. Tolerances on a date-time axis

- A non-zero `ltolx` in any tolerance set, override or plot tolerance
  fails the call when either time axis is a date-time axis; the error
  says `ltolx` scales with the absolute time (about 1.7e9 s) and
  suggests `atolx` in seconds. An explicit `ltolx = 0` is allowed.
- The resolved x half-width is `max(atolx, rtolx * reference span within
  x_range)` (`ltolx` is 0). On a date-time axis, when it is non-zero,
  each `tolerance_sets[]` entry gains (design choice, not yet confirmed
  by the owner)
  `"time_tolerance": {"seconds": 10800.0, "duration": "PT3H"}`, and rows
  with an override that changes the x axis carry the same object. The
  plot subtitle shows `x ±PT3H` instead of `atolx=1.08e+04`.
- Durations are ISO 8601 (`PT3H`, `PT1H30M`, `P1DT3H`, `PT0.5S`;
  seconds trimmed of trailing zeros, at most microseconds). Alternative:
  human text (`3 h 36 min`); ISO matches the rest of the date-time
  output and is unambiguous for agents.

### 8. How times are echoed (design choice, not yet confirmed by the owner)

Structured content keeps every existing numeric field unchanged and,
only when the axis is a date-time axis, adds an ISO sibling named
`<field>_iso`: `FileInfo.time_start_iso / time_end_iso`,
`RangeOut.lo_iso / hi_iso` (x-range and plot view), `Worst.x_iso`,
`Interval.start_x_iso / end_x_iso / worst_x_iso`, describe
`TimeInfo.start_iso / end_iso`. ISO strings are UTC with `Z` for offset
axes and without suffix for zone-less axes (matching what the file
said), seconds always present, fraction only when non-zero (up to 6
digits). The text rendering shows only the ISO form on date-time axes
(`t=2026-11-20T03:00:00..2026-11-20T07:00:00`) and durations for spans
and steps. Alternative: ISO only in text and a single axis descriptor in
structured content; rejected because the owner asked for both forms in
results.

### 9. describe_signals for a date-time column (design choice, not yet confirmed by the owner)

```json
{
  "header_line": 4,
  "time_column": "time",
  "time_column_rule": "named time",
  "time": {
    "kind": "datetime",
    "time_zone": "none",
    "start": 1793836800.0, "start_iso": "2026-11-05T00:00:00",
    "end": 1795129200.0,   "end_iso": "2026-11-19T23:00:00",
    "span": 1292400.0, "span_duration": "P14DT23H",
    "sampling": {"uniform": true, "min_step": 3600.0, "median_step": 3600.0,
                 "max_step": 3600.0, "median_step_duration": "PT1H"}
  },
  "problems": ["time column 'time' has no time zone; read as UTC"]
}
```

- `header_line` (always present: the physical line of the header used)
  and `time.kind` (`numeric` or `datetime`, always present) are new;
  `time.time_zone` (`offset` / `none`) and the `*_iso` / `*_duration`
  fields only for date-time axes.
- "No time zone" is reported in `problems` (it is a property the agent
  must notice, not a failure) — alternative: a `notes` entry. `problems`
  is preferred because agents already look there.
- Preamble lines are not echoed beyond the count implied by
  `header_line` and the hint text; their content can be large and is not
  needed to choose `header_line`. Alternative: a bounded echo (first 5
  lines, 200 characters each) to show e.g. Open-Meteo's
  `utc_offset_seconds`; easy to add later.

### 10. Pairs: matching, row identity and interactions (design choice, not yet confirmed by the owner)

- **Matching**: exact, case-sensitive equality with the header name
  after the reader's whitespace strip; units are part of the name
  (`temperature_2m (°C)`). A name not found is a per-row error
  (`MISSING_REFERENCE` / `MISSING_TEST`, as today) whose problem text
  suggests close names (`difflib.get_close_matches`, at most 3), e.g.
  "column 'temperature_2m' absent from the reference file; did you mean
  'temperature_2m (°C)'?" A pair name containing glob characters that is
  not a column adds "pairs take exact names; use columns for patterns".
- **Duplicate header names** keep failing the file (a name in a pair
  would be ambiguous); the message lists the duplicated names and,
  when applicable, the preamble hint.
- **Row key**: `Row.column` holds the key (the label if given, else the
  test column), so existing consumers, sorting, text rendering and the
  snippet ids keep working; pair rows add `reference_column` and
  `test_column` (same-name rows omit them). Keys must be unique across
  pairs: two pairs without labels sharing a test column, or a label
  equal to another pair's key, fail the call naming the clash and
  suggesting labels. `NotCompleted` gains the same two fields.
- **`tolerances[]`**: every set applies to every pair (rows = pairs ×
  sets), unchanged.
- **`column_tolerances`**: keyed by the row key; a key that matches no
  row gives the existing "override ignored" note. With same-name
  selection the key is the column name, as today.
- **`max_rows`**: unchanged ordering and capping over all rows;
  `columns_only_in_*` lists are only produced by the default
  same-name selection, never with pairs.
- **Same file**: when `test_path` is omitted or resolves to the same
  path with the same header line, the file is read once and used for
  both sides (same content guaranteed, half the reading time).
- **`test_path` omitted without pairs**: refused ("comparing a file with
  itself; pass test_path or pairs"), because every column would pass
  trivially. Alternative: allow it as the owner's wording literally
  permits; the refusal protects agents from a meaningless all-pass.
- **Time column in a pair**: a per-row error, as for `columns` today.
- **Snippet**: header constants `REFERENCE_HEADER_LINE` /
  `TEST_HEADER_LINE`, `TEST = REFERENCE` for one file, and case tuples
  `(key, reference_column, test_column, label, tolerances, status)` for
  all rows (same-name rows repeat the name). The test indexes
  `ref[reference_column]` and `tst[test_column]`. Date-time conversion
  happens in the embedded reader; `X_RANGE` bounds are epoch seconds
  with the ISO form in a comment.
- **Plot**: `run_compare` is called with one pair; legend entries
  "reference: <ref column>" / "test: <test column>", title starts with
  both columns when they differ
  (`temperature_2m_previous_day1 (°C) vs temperature_2m (°C)`, then the
  verdict line; one name as today when they are equal), y label the
  reference column. A glob in `test_column` gets the same
  "one exact column name" error as `column`. *Changed during
  implementation (after looking at the rendered preview):* with Open-Meteo
  names the one-line title ran off the figure and the four-column legend
  squeezed the axes, so for pairs the column names get a title line of
  their own and the legend has two columns. Same-name plots are unchanged.

### 11. Plot date axis (design choice, not yet confirmed by the owner)

x data stay epoch seconds (so the "drawn tube agrees with the
comparison" checks are unchanged); a tick locator picks nice UTC-aligned
steps (1, 2, 5, 10, 15, 30 min; 1, 2, 3, 6, 12 h; 1, 2, 7 days; also
sub-second and second steps for short windows and 14 days to a year for
long ones) and a formatter prints `MM-DD hh:mm` (`YYYY-MM-DD hh:mm` on the
first tick and at year changes; `MM-DD` alone for day steps; `hh:mm:ss[.f]`
for steps under a minute). At most 6 ticks with time-of-day labels and 10
with day labels, so 15 days of hourly data get a tick every 2 days
(implementation detail found by looking at the preview: a single limit of
6 gave only 3 ticks, one per week). The x label is `<time column> (UTC)` for offset axes and
`<time column> (no time zone)` for zone-less axes. No matplotlib date
units (they convert to float days and would change the drawn values).
Output stays deterministic.

### 12. Reader structure

`reader.py` (embedded in snippets) gains `header_line` and the
date-time conversion, and takes over the time-column rule from
`csvio.choose_time_column` so the snippet converts the same column. Its
main function returns a small named tuple (header, values, time column,
time column rule, time kind, zone kind, header line used, plus the
counts behind the partly-ISO problem and the most fraction digits)
instead of a 2-tuple; `csvio` keeps the server-side concerns (hint text,
`SignalFile`). The preamble hint lives in `csvio`, not in the embedded
reader, to keep snippets small. The reader grew from about 4.8 kB to
11.5 kB (about 125 lines), so every snippet is about 7 kB larger than
before; the snippet constants `REFERENCE_HEADER_LINE` / `TEST_HEADER_LINE`
hold the physical line of the header the server used (equivalent to the
argument, and also right when the argument pointed at blank or comment
lines before the header).

### 13. Smaller implementation choices

- Numeric strings in `x_range` (`"0.5"`) are still read as numbers, as
  before the bounds accepted strings; a string that is neither a finite
  number nor an ISO 8601 date-time is a validation error (so `"-inf"`
  still fails).
- A preamble hint for the test file names `test_header_line`; the
  time-axis mismatch error (which a test file read without its header line
  usually causes) carries the hints of both files.
- The "no x tolerance" note says "seconds on this date-time axis, e.g.
  atolx = 10800 for 3 h" instead of "time units" on date-time axes.
- Duplicate header names are listed in the error (`duplicated: [...]`).
- The `describe_signals` text shows the header line only when it is not 1,
  so numeric files render exactly as before.

## Risks / Trade-offs

- [`float | str` x-range bounds would accept `"-inf"` as a string] →
  validate strings against the ISO pattern in the model, so the existing
  "Infinite bound" scenario still fails as an argument validation error.
- [Hint false positives on files with several blank-separated blocks] →
  the hint only fires together with a failed or implausible read and
  only suggests; it never changes what is read.
- [Default `test_header_line = header_line` is wrong for a preamble file
  against a plain file] → the hint names the likely line for the test
  file too; the description says to set both.
- [Landing before `zero-default-x-tolerance` would give date-time
  comparisons a hidden ~0.2 % time tolerance] → tasks start with a check
  that the default x tolerance resolves to zero; the change is ordered
  after that one.
- [Rows keyed by label change `Row.column` semantics for pair rows] →
  existing same-name rows are unchanged; pair rows always carry
  `reference_column` / `test_column`.
- [Regex date parsing on very large files] → vectorised pandas string
  operations; a 1M-row test checks reading stays within a small multiple
  of today's numeric read.
- [Spec overlap with `zero-default-x-tolerance`] → this change adds
  requirements instead of modifying "Explicit tolerance sets resolved by
  the library" and "Tool descriptions explain tolerances", which that
  change is expected to modify.

## Migration Plan

Additive arguments and output fields; existing calls are unchanged.
Snippets generated before this change keep working (they embed their own
reader). Rollback is a package downgrade.
