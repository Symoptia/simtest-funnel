# Spec Delta

## Purpose

A local, read-only MCP server that lets AI agents compare signals stored in
local CSV files with the funnel (tolerance-tube) algorithm, without raw samples
ever entering the model's context.

## ADDED Requirements

### Requirement: Local stdio server distribution

The server SHALL be distributed as its own Python package, `simtest-funnel-mcp`,
whose console script of the same name starts an MCP server on the stdio
transport. The server SHALL expose exactly two tools, `describe_signals` and
`compare_signals`, both annotated as read-only, idempotent and closed-world.

#### Scenario: Client lists the tools
- **WHEN** an MCP client starts `simtest-funnel-mcp` as a subprocess, initializes
  a session over stdio and lists the tools
- **THEN** the list contains exactly `describe_signals` and `compare_signals`,
  each marked read-only

### Requirement: Stateless file access

Each tool call SHALL name the files it reads by path; the server MUST keep no
state between calls, MUST NOT write any file and MUST NOT open network
connections. A relative path SHALL be resolved against the first workspace root
when the client declares roots, otherwise against the server's working directory.

#### Scenario: Same call twice
- **WHEN** an agent calls `describe_signals` twice with the same path and the file
  is unchanged
- **THEN** both calls return identical results and no file is created or modified

### Requirement: Workspace roots are honoured

When the client declares one or more `file://` workspace roots, the server SHALL
refuse to read any path whose resolved location (symbolic links followed) is not
inside one of those roots. When the client declares no roots, any readable path
SHALL be accepted.

#### Scenario: Path outside the roots
- **WHEN** the client declares the root `/work/project` and an agent calls
  `describe_signals` with `/etc/hosts`
- **THEN** the call fails with an error that names the path and the declared roots

#### Scenario: No roots declared
- **WHEN** the client does not support roots and an agent passes an absolute path
  to a readable CSV file
- **THEN** the file is read

### Requirement: CSV dialect and time column

The server SHALL read comma-separated files with one header row, ignoring lines
starting with `#`. The time column SHALL be the first column whose name equals
`time` case-insensitively, otherwise the first column. Every result SHALL echo
the time column chosen for each file.

#### Scenario: Time column named Time
- **WHEN** a file has the header `signal,Time,value`
- **THEN** the time column is `Time` and `signal` and `value` are signal columns

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
no columns are given, and otherwise exactly the given columns. With the default
selection it SHALL list the signal columns present in only one of the files.

#### Scenario: Different column sets
- **WHEN** the reference has columns `time,a,b` and the test has `time,b,c` and no
  columns are given
- **THEN** only `b` is compared and the result lists `a` as only in the reference
  and `c` as only in the test

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
upper bound in time units, passed to the library, and SHALL echo it.

#### Scenario: Restrict the comparison window
- **WHEN** an agent passes the x-range `{"lo": 0.0, "hi": 0.5}`
- **THEN** only test points with time in `[0, 0.5]` are judged and the result
  echoes the range

### Requirement: One row per column and tolerance set

The result SHALL contain one row per (column, tolerance set) with the column, the
set label, a verdict (`pass`, `fail` or `error`), the library status code and
name and the number of judged points; failing rows add the points outside the
tube, the fractions of points and of span outside, the worst deviation and the
number of intervals.

#### Scenario: Failing column
- **WHEN** a column fails
- **THEN** its row has verdict `fail`, status `-1` named `FAIL`, a non-zero
  count of points outside and the worst deviation with its time and tube
  half-width

#### Scenario: Passing column
- **WHEN** a column passes
- **THEN** its row carries the verdict, status and judged-point count only

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
groups passing columns per tolerance set on one line.

#### Scenario: Client reads the text
- **WHEN** a client that ignores structured content calls `compare_signals`
- **THEN** the text content states the verdict counts, each failing or erroring
  row with its headline numbers, and the passing columns

### Requirement: Reproducible pytest snippet

When requested, `compare_signals` SHALL include one self-contained Python/pytest
snippet that reads the same files with the same dialect and compares the same
columns with the same tolerances as given and x-range through `simtest.funnel`,
asserting the status codes the server observed. Rows not decided by the library
SHALL be listed as comments only.

#### Scenario: Snippet reproduces the verdict
- **WHEN** an agent requests a snippet and the generated file is run with pytest
- **THEN** every test case passes, reproducing the status codes in the result

#### Scenario: Snippet not requested
- **WHEN** an agent does not request a snippet
- **THEN** the result contains no snippet

### Requirement: Tool descriptions explain tolerances

The `compare_signals` description SHALL give the tube half-width formula for the
six coefficients, the library's per-axis resolution rule and default, what a
tolerance in x (time) means, and a worked mapping of "1 % in y, 0.5 s in x" onto
coefficients.

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
