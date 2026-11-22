# mcp-server Specification

## Purpose
A local MCP server that lets AI agents compare signals stored in
local CSV files with the funnel (tolerance-tube) algorithm, without raw samples
ever entering the model's context.

## Requirements

### Requirement: Local stdio server distribution

The server SHALL be distributed as its own Python package, `simtest-funnel-mcp`,
whose console script of the same name starts an MCP server on the stdio
transport. The server SHALL expose the tools `describe_signals` and
`compare_signals`, both annotated as read-only, idempotent and closed-world.
Other capabilities MAY add further tools (for example the plot tool of
`mcp-plots`).

#### Scenario: Client lists the tools
- **WHEN** an MCP client starts `simtest-funnel-mcp` as a subprocess, initializes
  a session over stdio and lists the tools
- **THEN** the list contains `describe_signals` and `compare_signals`, each
  marked read-only

### Requirement: Stateless file access

Each tool call SHALL name the files it reads by path; the server MUST keep no
state between calls and MUST NOT open network connections. `describe_signals`
and `compare_signals` MUST NOT write any file; the only file the server ever
writes on request is the plot file of the `mcp-plots` capability. A relative path SHALL be resolved against the first workspace root
when the client declares roots, otherwise against the server's working directory.

#### Scenario: Same call twice
- **WHEN** an agent calls `describe_signals` twice with the same path and the file
  is unchanged
- **THEN** both calls return identical results and no file is created or modified

### Requirement: Workspace roots are honoured

When the client declares one or more `file://` workspace roots, the server SHALL
refuse to read any path whose resolved location (symbolic links followed) is not
inside one of those roots. Only local `file://` roots (empty host or
`localhost`) SHALL be used, converted to local paths with the platform's URL
path rules; other roots SHALL be ignored with a note in the result. When the
client declares no usable roots, any readable path SHALL be accepted.

#### Scenario: Path outside the roots
- **WHEN** the client declares the root `/work/project` and an agent calls
  `describe_signals` with `/etc/hosts`
- **THEN** the call fails with an error that names the path and the declared roots

#### Scenario: Non-local root
- **WHEN** the client declares the root `file://fileserver/share`
- **THEN** that root is ignored and the result carries a note saying so

#### Scenario: No roots declared
- **WHEN** the client does not support roots and an agent passes an absolute path
  to a readable CSV file
- **THEN** the file is read

### Requirement: CSV dialect and time column

The server SHALL read comma-separated files with one header row (see header
line), ignoring blank lines and lines whose first non-blank character is `#`;
a `#` elsewhere SHALL be read as data. A data row with more fields than the
header SHALL fail the call with an error naming the row and its line; a
trailing delimiter on every line including the header SHALL be accepted,
dropping the resulting unnamed empty last column. The server SHALL never
infer a row index from surplus fields.

#### Scenario: Hash inside the header
- **WHEN** a file has the header `time,a#1,b`
- **THEN** the signal columns are `a#1` and `b`

#### Scenario: Trailing delimiter on data rows only
- **WHEN** the header is `time,a` and the first data row is `0,1,`
- **THEN** the call fails with an error saying data row 1 has 3 fields while the
  header has 2

#### Scenario: Comment lines before the header with the default header line
- **WHEN** a file starts with two `#` lines followed by the header `time,a` and
  no header line is given
- **THEN** the header is `time,a`, exactly as before header lines existed

### Requirement: Time column choice

The time column SHALL be the first column whose name equals `time`
case-insensitively, otherwise the first column; other columns whose names differ
from `time` only by case SHALL be signal columns. Every result SHALL echo the
time column chosen for each file.

#### Scenario: Time column named Time
- **WHEN** a file has the header `signal,Time,value`
- **THEN** the time column is `Time` and `signal` and `value` are signal columns

#### Scenario: Two columns named time up to case
- **WHEN** a file has the header `Time,time,a`
- **THEN** the time column is `Time` and `time` and `a` are compared as signals

#### Scenario: No column named time
- **WHEN** a file has the header `t,u,v`
- **THEN** the time column is `t` and the result says it was chosen as the first
  column

### Requirement: Unreadable files fail the call

A file that does not exist, cannot be read, cannot be parsed as CSV, or has no
signal column besides the time column SHALL make the tool call fail with an
error message naming the file and the reason.

#### Scenario: Missing file
- **WHEN** an agent calls `compare_signals` with a reference path that does not
  exist
- **THEN** the call returns an error result naming that path

### Requirement: describe_signals reports file characteristics

`describe_signals(path)` SHALL return the resolved path, time column and how it
was chosen, row count, time start, end and span, sampling (uniform or not and
the minimum, median and maximum time step), and for each signal column its
minimum, maximum and range. It SHALL NOT return sample values.

#### Scenario: Demo reference file
- **WHEN** an agent describes a file with columns `time,x,y,z` and 1001 rows
  sampled every 0.001 s from 0 to 1
- **THEN** the result reports time column `time`, 1001 rows, span 1, uniform
  sampling with step 0.001, and three signal columns with their min, max and
  range

### Requirement: describe_signals output is bounded

`describe_signals` SHALL accept an optional `columns` filter of exact names and
glob patterns and a `max_columns` cap (default 100) on the columns and on the
problems listed, and SHALL report the total, selected and omitted column counts
and the omitted problem count.

#### Scenario: Very wide file
- **WHEN** an agent describes a file with 3000 signal columns without options
- **THEN** the result lists 100 columns, reports 3000 columns in total and 2900
  omitted, and stays a few tens of kilobytes at most

#### Scenario: Glob filter
- **WHEN** an agent describes a file with `columns` `["*.port.signal"]`
- **THEN** only columns whose names end in `.port.signal` are described

### Requirement: describe_signals reports data problems

`describe_signals` SHALL report, without failing, non-numeric or empty cells
per column (with counts), and a time column that is neither numeric nor an
ISO 8601 date-time column, contains empty cells or is not non-decreasing.

#### Scenario: Non-numeric values
- **WHEN** a column `y` contains two cells that are not numbers
- **THEN** the description of `y` reports two non-numeric or empty values and
  the call succeeds

#### Scenario: Time goes backwards
- **WHEN** the time column decreases somewhere
- **THEN** the description reports that the time column is not non-decreasing

#### Scenario: Partly date-time time column
- **WHEN** 98 cells of the time column are ISO 8601 date-times and 2 are not
- **THEN** the time column is reported as non-numeric, as before date-time
  columns existed, the problem text says that 98 of 100 non-empty cells are ISO
  8601 date-times and gives the line of the first other value, and no sample
  value is quoted

### Requirement: Column selection

`compare_signals` SHALL compare every signal column present in both files when
neither columns nor pairs are given, and otherwise exactly the given columns,
where an entry that is not an existing column name and contains `*`, `?` or
`[` SHALL select every signal column of either file matching it as a glob
pattern; a pattern that matches nothing SHALL be noted. With the default
selection it SHALL list the signal columns present in only one of the files.

#### Scenario: Different column sets
- **WHEN** the reference has columns `time,a,b` and the test has `time,b,c` and no
  columns are given
- **THEN** only `b` is compared and the result lists `a` as only in the reference
  and `c` as only in the test

#### Scenario: Glob pattern
- **WHEN** both files have `time,m.a.y,m.b.y,m.c.u` and the agent requests
  columns `["m.*.y"]`
- **THEN** the result contains rows for `m.a.y` and `m.b.y`

#### Scenario: Subset
- **WHEN** both files have `time,x,y,z` and the agent requests columns `["z"]`
- **THEN** the result contains rows for `z` only

### Requirement: Explicit tolerance sets resolved by the library

`compare_signals` SHALL accept zero or more tolerance sets, each with an optional
unique label and any of the six coefficients `atolx`, `atoly`, `ltolx`, `ltoly`,
`rtolx`, `rtoly`. The server SHALL pass the given coefficients unchanged to the
library, which resolves omitted ones; each set's six resolved values SHALL be
echoed. No sets means one set with nothing given.

#### Scenario: Only a y tolerance
- **WHEN** an agent passes one set `{"label": "y1pct", "rtoly": 0.01}`
- **THEN** the echoed resolved values are `rtoly = 0.01`, `atoly = ltoly = 0`
  and `atolx = ltolx = rtolx = 0` (no time tolerance), as the library resolves
  them

#### Scenario: No tolerance set
- **WHEN** an agent passes no tolerance set
- **THEN** the single set's echoed resolved values are `rtoly = 0.002` and every
  other coefficient `0`

#### Scenario: Several sets in one call
- **WHEN** an agent passes the sets `strict` and `loose` and three columns are
  compared
- **THEN** the result contains six rows, one per (column, set)

#### Scenario: Unknown coefficient name
- **WHEN** a tolerance set contains the key `rtol_y`
- **THEN** the call fails with an argument validation error

#### Scenario: Duplicate labels
- **WHEN** two tolerance sets carry the same label
- **THEN** the call fails with an error naming the duplicate label

### Requirement: Per-column tolerance overrides

`compare_signals` SHALL accept per-column overrides. For an overridden column, an
axis for which the override gives at least one coefficient SHALL take all three
of its coefficients from the override (unspecified ones not given); other axes
SHALL keep the set's values. Rows affected SHALL echo their resolved values.

#### Scenario: Override the y axis of one column
- **WHEN** the set gives `atolx = 0.1, atoly = 0.1` and the override for `z`
  gives `rtoly = 0.5`
- **THEN** column `z` is compared with `atolx = 0.1`, `rtoly = 0.5` and the
  library's resolution for the rest, other columns with the set as given, and the
  `z` rows echo their resolved values

### Requirement: Optional x-range

`compare_signals` SHALL accept an optional x-range with an optional lower and
upper bound in time units, passed to the library, and SHALL echo it. Bounds
MUST be finite; an omitted bound means unbounded. Non-finite tolerance
coefficients MUST be rejected as well.

#### Scenario: Restrict the comparison window
- **WHEN** an agent passes the x-range `{"lo": 0.0, "hi": 0.5}`
- **THEN** only test points with time in `[0, 0.5]` are judged and the result
  echoes the range

#### Scenario: Infinite bound
- **WHEN** an agent passes the x-range `{"lo": "-inf"}`
- **THEN** the call fails with an argument validation error

### Requirement: One row per column and tolerance set

The result SHALL contain one row per (column, tolerance set) whose comparison
completed, with the column, the set label, a verdict (`pass`, `fail` or
`error`), the library status code and name and the number of judged points;
failing rows add the points outside the tube, the fractions of points and of
span outside, the worst deviation and the number of intervals. Comparisons
stopped by the time limit SHALL have no row and SHALL be listed as not
completed instead.

#### Scenario: Failing column
- **WHEN** a column fails
- **THEN** its row has verdict `fail`, status `-1` named `FAIL`, a non-zero
  count of points outside and the worst deviation with its time and tube
  half-width

#### Scenario: Passing column
- **WHEN** a column passes
- **THEN** its row carries the verdict, status and judged-point count only

#### Scenario: All comparisons complete
- **WHEN** every comparison finishes within the time limit
- **THEN** there is one row per (column, tolerance set) and the result
  contains no not-completed list

### Requirement: Per-column problems do not fail the call

A column missing from one file, a non-monotonic time column and any other
library status SHALL be reported in that column's rows, with the library status
code (`MISSING_TEST` when absent from the test file, `MISSING_REFERENCE` when
absent from the reference) and a problem text, while other columns are compared.

#### Scenario: Requested column missing from the test file
- **WHEN** an agent requests columns `["x", "q"]` and `q` exists only in the
  reference
- **THEN** the `q` rows have verdict `error`, status `MISSING_TEST` and a problem
  text saying the column is absent from the test file, and the `x` rows carry
  normal verdicts

#### Scenario: Column with non-numeric data
- **WHEN** column `y` of the test file contains a non-numeric cell
- **THEN** the `y` rows have verdict `error` and a problem text, are not passed to
  the library, and other columns are compared

#### Scenario: Test covers a longer time range
- **WHEN** the reference covers time 0 to 1 and the test covers time 0 to 1.1
  and no x-range is given
- **THEN** the rows have verdict `error` and status `MISSING_REFERENCE`, carry
  the judged-point and outside counts, and their problem text states both time
  ranges and the x-range `{"lo": 0.0, "hi": 1.0}` that compares the overlap

#### Scenario: Comparing the overlap
- **WHEN** the same files are compared with the x-range `{"lo": 0, "hi": 1}`
- **THEN** the library judges coverage within that window and the rows carry
  normal `pass` / `fail` verdicts

#### Scenario: Disjoint time ranges
- **WHEN** the reference covers time 0 to 1 and the test covers time 2 to 3
- **THEN** every row reports the library status for that situation as an error
  and the result contains a note that the time ranges do not overlap

### Requirement: Interval details only for failures

Violation intervals SHALL be returned only for rows with verdict `fail`, ordered
by absolute worst deviation, largest first, and capped at a caller-adjustable
maximum per row (default 5). Each row SHALL state the total number of intervals.

#### Scenario: More intervals than the cap
- **WHEN** a failing column has 44 violation intervals and `max_intervals` is 3
- **THEN** its row lists the 3 intervals with the largest absolute deviation and
  reports an interval count of 44

#### Scenario: Passing row
- **WHEN** a column passes
- **THEN** its row lists no intervals

### Requirement: Result size is bounded

The result SHALL contain at most a caller-adjustable number of rows (default
100), ordered errors first, then failures, then passes, with the totals per
verdict always covering all rows and the number of omitted rows stated.

#### Scenario: Many columns
- **WHEN** 200 columns are compared with one tolerance set and `max_rows` is
  left at its default
- **THEN** the result contains 100 rows, the totals cover all 200 rows and the
  result states that 100 rows were omitted

### Requirement: Structured and text output

Both tools SHALL return structured content conforming to a published output
schema together with a short plain-text rendering of the same result that
groups passing columns per tolerance set on one line. Time (x) values MUST NOT
be rounded in the structured content; the text SHALL print times with enough
significant digits to distinguish adjacent samples.

#### Scenario: Epoch-second times
- **WHEN** a failing interval spans 1731628800.25 to 1731628800.75
- **THEN** the structured content carries those exact values and the text shows
  `t=1731628800.25..1731628800.75`

#### Scenario: Client reads the text
- **WHEN** a client that ignores structured content calls `compare_signals`
- **THEN** the text content states the verdict counts, each failing or erroring
  row with its headline numbers, and the passing columns

### Requirement: Reproducible pytest snippet

When requested, `compare_signals` SHALL include one self-contained Python/pytest
snippet that reads the same files with the same dialect (the server's reader,
embedded verbatim) and compares the same columns with the same tolerances as
given and x-range through `simtest.funnel`, asserting the status codes the
server observed. Rows not decided by the library SHALL be listed as comments
only.

#### Scenario: Snippet reproduces the verdict
- **WHEN** an agent requests a snippet and the generated file is run with pytest
- **THEN** every test case passes, reproducing the status codes in the result

#### Scenario: Snippet not requested
- **WHEN** an agent does not request a snippet
- **THEN** the result contains no snippet

### Requirement: Snippet scope and size

The snippet SHALL cover only the rows returned in the result, stating how many
were omitted, SHALL appear exactly once (in the structured content; the text
rendering points to it) and SHALL be capped in size.

#### Scenario: Snippet for many columns
- **WHEN** an agent compares 3000 columns with `max_rows` 5 and requests a
  snippet
- **THEN** the snippet has 5 cases and a comment that 2995 rows are not included,
  and it is not repeated in the text content

### Requirement: Snippet paths are portable

File paths under the first workspace root, else the server's working directory,
SHALL be written relative to it and resolved against the
`SIMTEST_FUNNEL_DATA_ROOT` environment variable, defaulting to the current
directory; other paths SHALL stay absolute with a comment that they will not
resolve elsewhere.

#### Scenario: Snippet run in a CI checkout
- **WHEN** the files lie under the workspace root and the snippet is run with
  `SIMTEST_FUNNEL_DATA_ROOT` pointing at a copy of that tree elsewhere
- **THEN** every test case passes

#### Scenario: File outside the base
- **WHEN** a compared file lies outside the workspace root
- **THEN** the snippet uses its absolute path and says it will not resolve on
  another machine

### Requirement: Tool descriptions explain tolerances

The `compare_signals` description SHALL give the tube half-width formula for the
six coefficients, the library's per-axis resolution rule and default, what a
tolerance in x (time) means, the fallback when a half-width is effectively zero
(`rtol * max|reference value|`, then `1e-10`; give `atoly` for constant
signals), when a column passes (including the coverage condition), and a worked
mapping of "1 % in y, 0.5 s in x" onto coefficients.

#### Scenario: Agent maps a request onto coefficients
- **WHEN** an agent reads the `compare_signals` description
- **THEN** it finds that "1 % in y, 0.5 s in x" corresponds to `rtoly = 0.01`
  (or `ltoly = 0.01` for 1 % of the local value) and `atolx = 0.5`

### Requirement: Registration documentation

The repository SHALL document how to register the server with Claude Code and
Claude Desktop and SHALL contain a root `.mcp.json` that runs the server from
the repository workspace.

#### Scenario: Using the server on this repository
- **WHEN** a developer opens this repository in Claude Code
- **THEN** the checked-in `.mcp.json` offers a `simtest-funnel` server started
  with `uv run` from the workspace

### Requirement: compare_signals time limit

`compare_signals` SHALL accept a time limit in seconds, 60 by default,
which MUST be positive and finite: a deadline for the whole call, counted
from its start, so the time spent reading the files counts against it.
Comparisons SHALL be started only while time remains, and a running
comparison SHALL be stopped when the limit is reached. Reading the files is
not interrupted, so a call can exceed the limit by the time spent reading.

#### Scenario: Default limit
- **WHEN** an agent calls `compare_signals` without a time limit
- **THEN** the comparisons are limited to 60 seconds in total

#### Scenario: Invalid limit
- **WHEN** an agent passes a time limit of 0 or a negative number
- **THEN** the call fails with an argument validation error

### Requirement: Time limit described as a deadline for the call

The descriptions of the `time_limit` argument and of the `compare_signals`
and `plot_signals` tools SHALL state that the limit counts from the start
of the call and includes reading the files (and, for `plot_signals`,
rendering).

#### Scenario: Agent reads the argument description
- **WHEN** an MCP client lists the tools
- **THEN** the `time_limit` description of both tools says the deadline
  counts from the start of the call and includes reading the files

### Requirement: Partial results on timeout

When the time limit stops `compare_signals`, the call SHALL still succeed and
return the rows of the comparisons that completed, the number of comparisons
not completed, the (column, tolerance set) pairs not completed (capped like
the rows), a flag that the limit was reached and a note suggesting a larger
time limit, fewer columns or a narrower x-range. The text SHALL say so too.

#### Scenario: Tiny time limit
- **WHEN** a fast column `a` and a column `b` whose comparison takes seconds
  are compared with a time limit of 0.3 s
- **THEN** the call succeeds, `a` has its normal row, `b` is listed as not
  completed with its tolerance set, the totals count one comparison not
  completed and the result says the time limit was reached

#### Scenario: Snippet with partial results
- **WHEN** the same call requests a snippet
- **THEN** the snippet reproduces only the completed rows

### Requirement: Server stays responsive during comparisons

The server SHALL run comparisons outside its message loop and without holding
the Python interpreter lock, so it keeps reading and answering messages while
a comparison runs.

#### Scenario: Request during a long comparison
- **WHEN** a `compare_signals` call with a comparison that takes seconds is
  running and the client sends a `tools/list` request on the same session
- **THEN** the server answers `tools/list` before the comparison finishes

### Requirement: Protocol cancellation stops the comparison

When the client sends the protocol's cancellation notification for a running
`compare_signals` or `plot_signals` call, the server SHALL stop the running
comparison promptly and SHALL NOT start further comparisons for that call.

#### Scenario: Client cancels a slow call
- **WHEN** a client cancels a `compare_signals` call whose comparison would
  take seconds
- **THEN** the comparison stops within a fraction of a second and the server
  goes on serving further calls

### Requirement: Descriptions state that there is no default time tolerance

The `compare_signals` description and the server instructions SHALL state that
there is no time tolerance unless an x coefficient is given. The description
SHALL also say that a slightly shifted steep edge then fails, and that the x
half-width is then the `1e-10` floor.

#### Scenario: Agent learns the x default
- **WHEN** an agent reads the `compare_signals` description or the server
  instructions
- **THEN** it finds that there is no time tolerance unless an x coefficient is
  given, and that a slightly shifted steep edge then fails

### Requirement: Hint when a failure had no x tolerance

When at least one row of a `compare_signals` result has verdict fail and no x
coefficient (`atolx`, `ltolx`, `rtolx`) was given for it, neither in its
tolerance set nor in a per-column override, the result SHALL contain exactly
one note giving the number of such rows and suggesting an x tolerance (such as
`atolx`) if the test may be shifted or delayed in time. Otherwise no such note
SHALL appear.

#### Scenario: Shifted edge with no x coefficient
- **WHEN** a column whose test step is slightly delayed fails with a set that
  gives only `atoly`
- **THEN** the notes contain one hint saying 1 failing row had no x (time)
  tolerance and suggesting `atolx`

#### Scenario: Explicit zero x tolerance
- **WHEN** the same column fails with a set that gives `atolx = 0` and `atoly`
- **THEN** no such hint appears

#### Scenario: Only passing rows
- **WHEN** every compared row passes
- **THEN** no such hint appears

### Requirement: Header line argument

`describe_signals`, `compare_signals` and `plot_signals` SHALL accept a
1-based header line per input file (default 1), counting physical file
lines. Lines before it SHALL be skipped unread; the header SHALL be the first
line at or after it that is neither blank nor a `#` comment. A header line
with no header at or after it SHALL fail the call with an error naming the
file's line count. The header line SHALL NOT be detected automatically.

#### Scenario: Open-Meteo preamble
- **WHEN** a file starts with the line
  `latitude,longitude,elevation,utc_offset_seconds,timezone,timezone_abbreviation`,
  a line of values and a blank line, followed by the header
  `time,temperature_2m (°C),temperature_2m_previous_day1 (°C)` and hourly data,
  and an agent describes it with header line 4
- **THEN** the time column is `time` and the signal columns are
  `temperature_2m (°C)` and `temperature_2m_previous_day1 (°C)`

#### Scenario: Header line past the end
- **WHEN** an agent passes header line 50 for a file of 20 lines
- **THEN** the call fails with an error naming the file, header line 50 and
  the 20 lines of the file

#### Scenario: Separate header line for the test file
- **WHEN** an agent compares a reference file with header line 4 against a
  plain test file and passes test header line 1
- **THEN** both files are read with their own header line

#### Scenario: Test header line defaults to the reference header line
- **WHEN** an agent passes header line 4 and no test header line
- **THEN** the test file is also read with header line 4

### Requirement: Preamble hint

When reading a file fails, or its header has a different field count than a
later line that looks like a header, or its time column has non-numeric, empty
or non-finite cells or mixed time zones, and the top of the file looks like a
preamble (a blank line followed by a
non-data line whose next line looks like data with the same field count), the
error or a problem text SHALL say so and suggest that line as the header line.
The hint SHALL NOT change what is read.

#### Scenario: Open-Meteo file read without a header line
- **WHEN** an agent describes the Open-Meteo file above without a header line
- **THEN** the result (or the error, if reading fails) says the header was
  taken from line 1, that line 3 is blank and line 4 looks like a header row,
  and suggests `header_line=4`

#### Scenario: Plain file
- **WHEN** a plain CSV file has its header on line 1, a blank line and then
  numeric data
- **THEN** no preamble hint is given

#### Scenario: Read fails on the metadata header
- **WHEN** an Open-Meteo file whose header row has more fields than the
  metadata line is read without a header line
- **THEN** the call fails with the error naming the too-wide data row, followed
  by the preamble hint suggesting `header_line=4`

### Requirement: describe_signals reports the header line and time axis

`describe_signals` SHALL echo the header line used and the time column kind
(numeric or date-time). For a date-time column it SHALL also report whether
the timestamps carry a time zone, the time start and end as ISO 8601
strings, and the span and median step as ISO 8601 durations, next to the
numeric values in seconds.

#### Scenario: Open-Meteo time column
- **WHEN** an agent describes, with header line 4, an Open-Meteo file whose
  time cells run hourly from `2026-11-05T00:00` to `2026-11-19T23:00`
- **THEN** the result reports header line 4, a date-time time column without
  time zone, start `1793836800` and `2026-11-05T00:00:00`, end `1795129200`
  and `2026-11-19T23:00:00`, uniform sampling with step 3600 s (`PT1H`)
  and a problem saying the time column has no time zone and is read as UTC

#### Scenario: Numeric time column
- **WHEN** an agent describes a file with a numeric time column
- **THEN** the result reports header line 1 and time column kind numeric and
  otherwise the same fields as before

### Requirement: ISO 8601 date-time time column

A time column whose non-empty cells all parse as ISO 8601 date-times
(`YYYY-MM-DD`, optionally `T` or a space and `hh:mm`, optional seconds and
fraction, optional `Z` or offset) SHALL be read as seconds since the Unix
epoch, so x tolerances and numeric x-range bounds are in seconds. A file and
its copy with epoch-second times SHALL give identical results.

#### Scenario: ISO file and unixtime twin
- **WHEN** an agent compares the same columns once in a file with times
  `2026-11-20T00:00`, `2026-11-20T01:00`, ... and once in a copy with times
  `1795132800`, `1795136400`, ...
- **THEN** both results have identical rows, verdicts and counts

#### Scenario: Forms accepted
- **WHEN** time columns contain `2026-11-20T00:00`, `2026-11-20 00:00:00`,
  `2026-11-20T00:00:00.25Z` or `2026-11-20T01:00+01:00`
- **THEN** each is read as a date-time column, the last two as
  `1795132800.25` and `1795132800`

#### Scenario: Date-only cells
- **WHEN** a time column contains `2026-11-20` and `2026-11-21`
- **THEN** it is read as a date-time column without time zone, with the cells
  at midnight (`1795132800` and `1795219200`)

#### Scenario: Dates mixed with date-times
- **WHEN** a time column contains `2026-11-20`, `2026-11-20T12:00` and
  `2026-11-21`
- **THEN** it is read as one date-time column without time zone

#### Scenario: Not ISO 8601
- **WHEN** a time column contains `2026-02-30T00:00` or `2026-11-20T24:00`
  next to valid date-times
- **THEN** it is not read as a date-time column and the time column problem is
  reported

#### Scenario: Three hours in x
- **WHEN** an agent compares two date-time files with `atolx = 10800` and
  `atoly = 2`
- **THEN** a test curve shifted by up to three hours stays inside the tube in x

### Requirement: Uniform sampling allows for float rounding of large times

`describe_signals` SHALL call the sampling uniform when no step is negative
and the spread between the largest and smallest step is at most the larger of
`1e-6` times the median step and four float64 spacings of the largest absolute
time, for numeric and date-time time columns alike.

#### Scenario: Sub-second epoch seconds
- **WHEN** a numeric time column holds epoch seconds `1795132800.0`,
  `1795132800.1`, ... in steps of 0.1 s
- **THEN** the sampling is reported uniform with median step 0.1, and its ISO
  twin with times `2026-11-20T00:00:00.0`, ... is described with the same
  numbers

#### Scenario: Small time values unchanged
- **WHEN** a time column runs from 0 in steps that alternate between
  `1 + 2e-6` and `1 - 2e-6`
- **THEN** the sampling is reported non-uniform, as before

### Requirement: Time zones of date-time columns

A date-time cell without an offset SHALL be read as UTC. Comparing a
reference and a test whose time columns differ in kind (numeric against
date-time, or date-time without time zone against date-time with offsets)
SHALL fail the call with an error naming both files, their time columns and
kinds. A time column that mixes cells with and without an offset SHALL be
reported as a time column problem.

#### Scenario: Both without time zone
- **WHEN** both files have zone-less date-time time columns
- **THEN** they are compared normally

#### Scenario: Zone-less against offsets
- **WHEN** the reference times are `2026-11-20T00:00` and the test times are
  `2026-11-20T00:00Z`
- **THEN** the call fails with an error explaining that one time column has a
  time zone and the other has none, and how to make them match

#### Scenario: Numeric against date-time
- **WHEN** the reference time column is numeric and the test time column is a
  date-time column
- **THEN** the call fails with an error naming both kinds

#### Scenario: Mixed offsets in one column
- **WHEN** a time column holds `2026-11-20T00:00` and `2026-11-20T01:00Z`
- **THEN** describe reports that it mixes timestamps with and without a time
  zone, and its compare rows have verdict `error`

### Requirement: Relative-to-time x tolerance refused on date-time axes

A non-zero `ltolx` in any tolerance set or override SHALL fail the call when
a time column is a date-time column, with an error explaining that `ltolx`
scales with the absolute epoch time and suggesting `atolx` in seconds. An
explicit `ltolx` of 0 SHALL be accepted.

#### Scenario: ltolx on dates
- **WHEN** an agent compares date-time files with `ltolx = 0.001`
- **THEN** the call fails with an error that names `ltolx` and suggests
  `atolx`

### Requirement: Time tolerance echoed as a duration

On a date-time axis, every tolerance set and every row with an x-axis
override whose resolved x half-width is non-zero SHALL echo that half-width
in seconds and as an ISO 8601 duration, also when it comes from `rtolx`.

#### Scenario: Explicit rtolx on dates
- **WHEN** an agent compares 15 days of hourly date-time data (span 1292400 s)
  with `rtolx = 0.01`
- **THEN** the tolerance set echoes `rtolx = 0.01`, a time tolerance of
  12924 s and its duration `PT3H35M24S`

#### Scenario: atolx in seconds
- **WHEN** the set gives `atolx = 10800`
- **THEN** the time tolerance is echoed as 10800 s and `PT3H`

### Requirement: Date-time x-range bounds

On a date-time axis, x-range bounds SHALL accept ISO 8601 strings as well as
epoch seconds; a string bound SHALL carry a time zone exactly when the time
columns do. ISO bounds on a numeric axis, and strings that are not ISO 8601
date-times, SHALL fail the call with an argument validation error.

#### Scenario: ISO bounds
- **WHEN** an agent compares zone-less date-time files with the x-range
  `{"lo": "2026-11-05T00:00", "hi": "2026-11-10T00:00"}`
- **THEN** only test points in that window are judged and the result echoes
  the bounds as epoch seconds and as ISO strings

#### Scenario: ISO bound on a numeric axis
- **WHEN** an agent passes an ISO string bound while the time columns are
  numeric
- **THEN** the call fails with an argument validation error

### Requirement: Date-time times in results

On a date-time axis, every time value in the structured content (file time
start and end, x-range, worst deviation time, interval times) SHALL keep its
exact number and add an ISO 8601 string, and the text rendering SHALL print
times as ISO 8601 strings and spans as durations. Numeric axes SHALL be
rendered as before.

#### Scenario: Failing interval on a date axis
- **WHEN** a failing interval runs from `2026-11-20T03:00` to
  `2026-11-20T07:00` in zone-less files
- **THEN** the structured interval carries `1795143600` and `1795158000` with
  `2026-11-20T03:00:00` and `2026-11-20T07:00:00`, and the text shows
  `t=2026-11-20T03:00:00..2026-11-20T07:00:00`

### Requirement: Column pairs

`compare_signals` SHALL accept pairs of exact column names, each naming a
reference column, a test column and an optional label, and SHALL then compare
each pair's reference column with its test column under every tolerance set.
Pairs and `columns` SHALL NOT be combined in one call. Glob characters in a
pair SHALL NOT be expanded.

#### Scenario: Forecasts against the latest run in one file
- **WHEN** an agent passes one file with header line 4 and the pairs
  `temperature_2m (°C)` against `temperature_2m_previous_day1 (°C)`,
  `..._day3 (°C)` and `..._day5 (°C)` with labels `day1`, `day3`, `day5` and
  two tolerance sets
- **THEN** the result contains six rows, one per (pair, tolerance set)

#### Scenario: Pairs together with columns
- **WHEN** an agent passes both `pairs` and `columns`
- **THEN** the call fails with an error saying they cannot be combined

#### Scenario: Pattern in a pair
- **WHEN** a pair names the test column `temperature_2m_previous_day*` and no
  column has that name
- **THEN** that pair's rows have verdict `error` and status `MISSING_TEST`, and
  the problem says pairs take exact names and patterns belong in `columns`

#### Scenario: Name without the unit suffix
- **WHEN** a pair names the reference column `temperature_2m` and the file has
  `temperature_2m (°C)`
- **THEN** the rows have verdict `error`, status `MISSING_REFERENCE` and a
  problem text suggesting `temperature_2m (°C)`

### Requirement: Rows of column pairs

A row of a pair SHALL carry the reference and the test column name, and its
column key SHALL be the pair's label when given, otherwise its test column.
Keys SHALL be unique across pairs; a clash SHALL fail the call with an error
naming it. Per-column tolerance overrides, not-completed entries and the
result size cap SHALL use these keys and rows.

#### Scenario: Override addressed by label
- **WHEN** pairs `day1` and `day3` are compared and `column_tolerances` gives
  `{"day3": {"atoly": 3}}`
- **THEN** only the `day3` rows use `atoly = 3` and echo their resolved values

#### Scenario: Override addressed by test column
- **WHEN** a pair without label has the test column `b_model` and
  `column_tolerances` gives an override for `b_model`
- **THEN** that pair's rows use the override

#### Scenario: Clashing keys
- **WHEN** two pairs without labels share the test column `x`
- **THEN** the call fails with an error naming `x` and suggesting labels

#### Scenario: Same-name rows unchanged
- **WHEN** an agent compares with `columns` or without selection
- **THEN** rows carry the column name as before and no separate reference or
  test column fields

### Requirement: Test file defaults to the reference file

`compare_signals` SHALL accept a call without a test path when pairs are
given, comparing within the reference file. A call with neither a test path
nor pairs SHALL fail with an error explaining that a file would be compared
with itself.

#### Scenario: One file
- **WHEN** an agent passes a reference path, pairs and no test path
- **THEN** each pair compares two columns of the reference file and the
  result names the same file as reference and test

#### Scenario: No test path and no pairs
- **WHEN** an agent passes only a reference path
- **THEN** the call fails with an error saying to pass a test path or pairs

### Requirement: Snippet reproduces pairs, header lines and date-time times

The pytest snippet SHALL read each file with its header line, convert
date-time time columns exactly as the server does, compare each row's
reference column with its test column, and use one file for both sides when
the server did.

#### Scenario: Snippet of a one-file pair comparison
- **WHEN** an agent requests a snippet for the Open-Meteo pair comparison
  above and runs it with pytest
- **THEN** every test case passes, reproducing the status codes in the result

### Requirement: Tool descriptions explain pairs, header line and date-time axis

The tool descriptions SHALL explain `pairs` and the row key, the optional
test path, the header line and the preamble hint, the date-time time axis in
epoch seconds, the time zone rule, ISO x-range bounds and that x tolerances
are seconds on a date-time axis, with a worked mapping of "±2 °C and
±3 hours" onto coefficients.

#### Scenario: Agent maps a weather request onto coefficients
- **WHEN** an agent reads the `compare_signals` description
- **THEN** it finds that "±2 °C and ±3 hours" on a date-time axis corresponds
  to `atoly = 2` and `atolx = 10800`
