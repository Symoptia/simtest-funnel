# Spec Delta

## MODIFIED Requirements

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

## ADDED Requirements

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
