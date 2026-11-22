## MODIFIED Requirements

### Requirement: Description explains the x-range window

The `compare_signals` description SHALL state that only test points inside
the x-range are judged, that the tube there is built from the reference
extended beyond the x-range as far as needed for it to equal the tube of
the whole reference there, so that without `rtolx` / `rtoly` every judged
point gets the same deviation and verdict as for the whole files, and that
the bases of `rtolx` / `rtoly` are the reference inside the x-range.

#### Scenario: Agent learns the window semantics
- **WHEN** an agent reads the `compare_signals` description
- **THEN** it finds that only points inside x_range are judged, against a
  tube built from the reference extended beyond x_range, with the same
  verdicts as a comparison of the whole files when rtolx and rtoly are 0

### Requirement: Column pairs

`compare_signals` SHALL accept pairs of exact column names, each naming a
reference column, a test column and an optional label, and SHALL then compare
each pair's reference column with its test column under every tolerance set.
Pairs and `columns` SHALL NOT be combined in one call. Glob characters in a
pair SHALL NOT be expanded. A pair naming the same column of the same loaded
file on both sides SHALL get an error row, not a trivial pass.

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

#### Scenario: A column paired with itself
- **WHEN** an agent passes the pair `{"reference": "x", "test": "x"}` without
  `test_path` (or with the reference file as `test_path`)
- **THEN** that pair's rows have verdict `error` and a problem saying the
  column would be compared with itself; other pairs are compared

### Requirement: ISO 8601 date-time time column

A time column whose non-empty cells all parse as ISO 8601 date-times
(`YYYY-MM-DD`, optionally `T` or a space and `hh:mm`, optional seconds and
fraction, optional `Z` or offset; ASCII digits only) SHALL be read as seconds
since the Unix epoch, so x tolerances and numeric x-range bounds are in
seconds. A file and its copy with epoch-second times SHALL give identical
results.

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

#### Scenario: Non-ASCII digits
- **WHEN** a time cell is written with fullwidth (`２０２６-11-20T00:00`) or
  Arabic-Indic (`١٩٧٠-01-01T00:00Z`) digits, or such an x-range bound is given
- **THEN** the cell is not a date-time (the time column problem is
  reported) and the bound is a validation error

#### Scenario: Three hours in x
- **WHEN** an agent compares two date-time files with `atolx = 10800` and
  `atoly = 2`
- **THEN** a test curve shifted by up to three hours stays inside the tube in x

### Requirement: Preamble hint

When reading a file fails, or its header has a different field count than a
later line that looks like a header, or its time column has non-numeric,
empty or non-finite cells or mixed time zones, and the top of the file looks
like a preamble (a blank line followed by a non-data line whose next line
looks like data with the same field count; lines split at CR LF, CR or LF),
the error or problem text SHALL say so and suggest that line as the header
line. The hint SHALL NOT change what is read.

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

#### Scenario: Lone CR line breaks
- **WHEN** the same failing file uses lone CR line breaks
- **THEN** the same preamble hint suggesting `header_line=4` is given

### Requirement: Opt-in download in the snippet

When `SIMTEST_FUNNEL_DOWNLOAD=1` is set and a URL input's local copy is
missing (and only then), the snippet SHALL download the URL the server
finally read over `https` only, uncompressed, following no redirect, within
an overall deadline, read at most the recorded size, and save it only when
its SHA-256 equals the recorded one, by an exclusive link or create, so an
existing copy is never replaced.

#### Scenario: Opt-in download of a missing copy
- **WHEN** the snippet runs with `SIMTEST_FUNNEL_DOWNLOAD=1`, the copy is
  missing and the URL still serves the data that was compared
- **THEN** the URL is downloaded once, saved under the stated name, and
  every test case passes

#### Scenario: Opt-in download of changed data
- **WHEN** the snippet runs with `SIMTEST_FUNNEL_DOWNLOAD=1`, the copy is
  missing and the URL now serves different data
- **THEN** the tests fail with a message saying the data behind the URL
  differs from what was compared, giving both SHA-256 values, and no file is
  left under the data root

#### Scenario: Opt-in with an existing copy
- **WHEN** the snippet runs with `SIMTEST_FUNNEL_DOWNLOAD=1` and a copy
  already exists
- **THEN** no request is made and the copy is checked as without the
  variable

#### Scenario: Redirect at download time
- **WHEN** the URL now answers with a redirect
- **THEN** the tests fail saying redirects are not followed and nothing is
  saved

#### Scenario: Server followed a redirect
- **WHEN** the server reached the data through a redirect
- **THEN** the snippet downloads from the final URL with
  `Accept-Encoding: identity`

#### Scenario: Slow download
- **WHEN** the download takes longer than the deadline
- **THEN** the tests fail saying so and nothing is saved
