## MODIFIED Requirements

### Requirement: Description explains the x-range window

The `x_range` argument description of `compare_signals` SHALL state that
only test points inside the x-range are judged, against the tube of the
whole reference there, built from the reference extended beyond the
window as far as needed, that the bases of `rtolx` / `rtoly` are the
reference inside it, and the unit of its bounds (seconds since 1970 or
ISO 8601 strings on a date-time axis).

#### Scenario: Agent learns the window semantics
- **WHEN** an agent lists the tools
- **THEN** the `x_range` description of `compare_signals` says that only
  test points inside it are judged, against the tube of the whole
  reference there, built from the reference extended beyond the window as
  far as needed

## ADDED Requirements

### Requirement: Unknown arguments refused

`describe_signals`, `compare_signals` and `plot_signals` SHALL refuse a
call whose arguments contain a name the tool does not define, at the top
level or inside a tolerance set, pair, x-range or per-column override,
with an error naming the unknown name and its location and, when a close
match exists, suggesting it. Each published input schema SHALL declare
`additionalProperties: false` for every object.

#### Scenario: Misspelt header line
- **WHEN** an agent calls `describe_signals` with `header_lin: 4`
- **THEN** the call fails with `unknown argument 'header_lin'; did you
  mean 'header_line'?` instead of reading the file with header line 1

#### Scenario: Misspelt coefficient in a tolerance set
- **WHEN** an agent calls `compare_signals` with the tolerance sets
  `[{"atoly_": 1}]`
- **THEN** the call fails naming `tolerances[0]`, the unknown name `atoly_`
  and the suggestion `atoly`

#### Scenario: No close match
- **WHEN** an agent passes an argument `roots` to `plot_signals`
- **THEN** the call fails naming `roots` and listing the accepted names

#### Scenario: Schemas agree
- **WHEN** an agent lists the tools
- **THEN** every object in each input schema, including tolerance sets,
  pairs and the x-range, has `additionalProperties: false`

### Requirement: Argument errors stated per argument

An argument validation error SHALL be stated as one line per argument at
fault, naming its path (for example `tolerances[1].atolx`), the reason and
the value given, without repeating the other arguments.

#### Scenario: Two faults in one call
- **WHEN** an agent calls `compare_signals` with `header_line: 0` and a
  second tolerance set with `atolx: -1`
- **THEN** the error lists `header_line` and `tolerances[1].atolx`, each
  with its reason and the value given

### Requirement: Non-UTF-8 files refused with an actionable message

A file that is not valid UTF-8 (a UTF-8 byte-order mark is allowed) SHALL
fail the call with an error that names the file or URL, says it is not
valid UTF-8 (or which UTF-16 / UTF-32 byte-order mark it starts with),
gives the line and the offending bytes in context, names the likely cause
(a legacy code page such as Windows-1252, e.g. Excel's plain "CSV") and
says to save it as "CSV UTF-8" or convert it. No other encoding is read.

#### Scenario: Excel CSV in Windows-1252
- **WHEN** an agent describes a file whose header `time,value (°C)` is
  encoded in Windows-1252
- **THEN** the call fails saying the file is not valid UTF-8, that line 1
  has the byte 0xB0 (`'°'` in Windows-1252), and to re-save it as "CSV
  UTF-8" or convert it, without a codec message

#### Scenario: UTF-16 file
- **WHEN** a file starts with a UTF-16 LE byte-order mark
- **THEN** the call fails saying the file is UTF-16 LE, not UTF-8, and how
  to convert it

#### Scenario: URL input
- **WHEN** a fetched URL's content is Windows-1252
- **THEN** the error names the URL, never the local cache path, with the
  same explanation

#### Scenario: Snippet reader
- **WHEN** a generated pytest snippet reads a file that has since been
  saved in Windows-1252 or UTF-16
- **THEN** the test fails with the same explanation, naming the file

#### Scenario: UTF-8 with byte-order mark and CRLF
- **WHEN** a UTF-8 file starts with a byte-order mark and uses CRLF line
  ends
- **THEN** it is read as before

### Requirement: Difference at the worst points

Each failing row's worst point SHALL carry `difference`, and each listed
interval `worst_difference`: the test value minus the reference value at
the same x, the reference interpolated linearly as the library
interpolates (at a repeated reference time, its first value). The text
rendering SHALL show the difference beside the deviation.

#### Scenario: Day-3 forecast against the latest run
- **WHEN** an agent compares the bundled Open-Meteo file's day-3 forecast
  with the latest run (header line 4, `atoly 2`, `atolx 10800`)
- **THEN** the worst point is 2026-11-19T04:00 with deviation -0.9,
  half-width 2.15 and difference -3.0, the value of the forecast cell
  minus the latest-run cell of that hour

#### Scenario: Test on a different grid
- **WHEN** the test is sampled half a step after the reference
- **THEN** the difference uses the reference interpolated at the test
  point's time

### Requirement: Result fields explained where they are read

The output schema SHALL describe `deviation` and `worst_deviation` as the
signed distance of the test point outside the tube (positive above the
upper edge, negative below the lower edge), not test minus reference,
`tube_half_width_y` as the tube's vertical half-width at that x (wider
than the y tolerance where an x tolerance widens the tube), and
`difference`. The `compare_signals` description SHALL say the same briefly.

#### Scenario: Agent reads the output schema
- **WHEN** an agent lists the tools
- **THEN** the descriptions of `deviation`, `tube_half_width_y` and
  `difference` in the `compare_signals` output schema state these
  definitions, and the tool description has a short part on reading a row

### Requirement: Note on failures at the record edges

When a failing row has an x tolerance in effect and a violation interval
that starts within one x half-width after the first reference sample or
ends within one before the last, the result SHALL contain one note giving
the number of such rows, naming some, explaining that the tube cannot be
widened in time there, and suggesting an x-range excluding the edge or
accepting it. Otherwise no such note SHALL appear.

#### Scenario: Delayed test fails only at the first sample
- **WHEN** the reference is sin(t) sampled every 0.05 from 0 to 10, the
  test is the same delayed by 0.1, and the set is `atoly 0.06, atolx 0.15`
- **THEN** the row fails only at t = 0 and the notes contain the edge note
  suggesting the x-range `{"lo": 0.15}`, with which the row passes

#### Scenario: Failures elsewhere only
- **WHEN** the test has a bump between t = 6 and 6.5 and no delay, with
  `atoly 0.05, atolx 0.1`
- **THEN** the row fails and no edge note appears

### Requirement: Note on differing time spans when the overlap fails

When the reference and test cover different time spans within the x-range
and at least one row fails, so that the library reports `FAIL` instead of
a coverage status, the result SHALL contain a note giving both spans,
which file extends beyond the other, the failing rows, and the x-range of
the overlap.

#### Scenario: Shorter test with a failing overlap
- **WHEN** the reference covers 0 to 10, the test 0 to 8, and the test
  leaves the tube inside 0 to 8
- **THEN** the row's verdict is `fail` and a note says the reference
  extends beyond the test and that x-range `{"lo": 0.0, "hi": 8.0}`
  compares the overlap

#### Scenario: Comparing the overlap
- **WHEN** the same files are compared with that x-range
- **THEN** no note about time ranges appears

### Requirement: Concise tool descriptions

With network access off, the server instructions SHALL stay within 1200
characters and the descriptions of `describe_signals`, `compare_signals`
and `plot_signals` within 2000, 4100 and 2000 characters. The CSV dialect
SHALL be described once, in `describe_signals`. The instructions SHALL keep
the header-line hint, `pairs` / `test_column`, and "3 hours" = `atolx
10800`; `plot_signals` SHALL keep where plot files may be written.

#### Scenario: Agent lists the tools
- **WHEN** an MCP client lists the tools of a server started without
  network access
- **THEN** the description sizes are within these bounds and the
  descriptions still contain the worked examples named above
