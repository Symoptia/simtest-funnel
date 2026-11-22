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

The server SHALL read comma-separated files with one header row, ignoring blank
lines and lines whose first non-blank character is `#`; a `#` elsewhere SHALL be
read as data. A data row with more fields than the header SHALL make the call
fail with an error naming the row and its line; a trailing delimiter on every
line including the header SHALL be accepted, dropping the resulting unnamed
empty last column. The server SHALL never infer a row index from surplus fields.

#### Scenario: Hash inside the header
- **WHEN** a file has the header `time,a#1,b`
- **THEN** the signal columns are `a#1` and `b`

#### Scenario: Trailing delimiter on data rows only
- **WHEN** the header is `time,a` and the first data row is `0,1,`
- **THEN** the call fails with an error saying data row 1 has 3 fields while the
  header has 2

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
per column (with counts), and a time column that is non-numeric, contains
empty cells or is not non-decreasing.

#### Scenario: Non-numeric values
- **WHEN** a column `y` contains two cells that are not numbers
- **THEN** the description of `y` reports two non-numeric or empty values and
  the call succeeds

#### Scenario: Time goes backwards
- **WHEN** the time column decreases somewhere
- **THEN** the description reports that the time column is not non-decreasing

### Requirement: Column selection

`compare_signals` SHALL compare every signal column present in both files when
no columns are given, and otherwise exactly the given columns, where an entry
that is not an existing column name and contains `*`, `?` or `[` SHALL select
every signal column of either file matching it as a glob pattern; a pattern
that matches nothing SHALL be noted. With the default selection it SHALL list
the signal columns present in only one of the files.

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
- **THEN** the echoed resolved values are `rtoly = 0.01`, `atoly = ltoly = 0`,
  `rtolx = 0.002` and `atolx = ltolx = 0`, as the library resolves them

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
