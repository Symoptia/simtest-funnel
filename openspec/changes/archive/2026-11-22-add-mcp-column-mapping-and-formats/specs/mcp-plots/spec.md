# Spec Delta

## MODIFIED Requirements

### Requirement: Plot tool on the local server

The local MCP server SHALL offer a tool `plot_signals` in addition to its
existing tools. It SHALL take a reference path, an optional test path
(default: the reference file), exactly one signal column name, an optional
test column name (default: the same name), at most one tolerance set, an
optional x-range, header lines, an optional output path, an `overwrite`
flag, a cap on listed intervals and a time limit, with the names and shapes
`compare_signals` uses for the same meaning.

#### Scenario: Client lists the tools
- **WHEN** an MCP client lists the server's tools
- **THEN** the list contains `describe_signals`, `compare_signals` and
  `plot_signals`

#### Scenario: Glob pattern instead of a column name
- **WHEN** an agent calls `plot_signals` with column `"*"` and no column has
  that name
- **THEN** the call fails with an error saying one exact column name is needed

#### Scenario: Glob pattern as test column
- **WHEN** an agent passes the test column `"temperature_2m_previous_day*"` and
  no column has that name
- **THEN** the call fails with an error saying one exact column name is needed

## ADDED Requirements

### Requirement: Plot of a column pair

When the test column differs from the column, `plot_signals` SHALL compare
and draw the reference column of the reference file against the test column
of the test file, exactly as the corresponding pair of `compare_signals`,
and the legend and title SHALL name both columns.

#### Scenario: Day-1 forecast against the latest run in one file
- **WHEN** an agent plots, from one Open-Meteo file with header line 4 and no
  test path, column `temperature_2m (°C)` against test column
  `temperature_2m_previous_day1 (°C)`
- **THEN** the verdict, counts and intervals equal those of the matching
  `compare_signals` pair row, and the legend and title name both columns

#### Scenario: Test column omitted
- **WHEN** an agent plots with a column and no test column
- **THEN** the same column is plotted from both files, as before

### Requirement: Date-time time axis in plots

When the time columns are date-time columns, the plot's x axis SHALL be
labelled with dates and times and state whether times are UTC or carry no
time zone, x-range bounds SHALL accept ISO 8601 strings as in
`compare_signals`, and the result SHALL echo the view and all times as
numbers and ISO 8601 strings.

#### Scenario: Plot of hourly Open-Meteo data
- **WHEN** an agent plots 15 days of zone-less hourly Open-Meteo data
- **THEN** the x tick labels are dates and times, the x axis label says the
  times have no time zone, and the result's view carries epoch seconds and
  ISO 8601 strings

#### Scenario: Zoom with ISO bounds
- **WHEN** an agent plots with the x-range
  `{"lo": "2026-11-10T00:00", "hi": "2026-11-12T00:00"}`
- **THEN** only test points in that window are judged and the x axis spans
  those two days
