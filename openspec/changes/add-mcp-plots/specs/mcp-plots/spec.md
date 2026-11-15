# Spec Delta

## Purpose

A plot tool on the local MCP server that draws one funnel comparison (one
signal column, one tolerance set) as an inline PNG preview the agent can look
at and, on request, as an SVG or PNG file for documents, never contradicting
the comparison's verdict.

## ADDED Requirements

### Requirement: Plot tool on the local server

The local MCP server SHALL offer a tool `plot_signals` in addition to its
existing tools, which stay unchanged. It SHALL take a reference path, a test
path, exactly one signal column name, at most one tolerance set, an optional
x-range, an optional output path, an `overwrite` flag and a cap on listed
intervals, with the names and shapes `compare_signals` uses for the same
meaning.

#### Scenario: Client lists the tools
- **WHEN** an MCP client lists the server's tools
- **THEN** the list contains `describe_signals`, `compare_signals` and
  `plot_signals`, and the arguments of the first two are unchanged

#### Scenario: Glob pattern instead of a column name
- **WHEN** an agent calls `plot_signals` with column `"*"` and no column has
  that name
- **THEN** the call fails with an error saying one exact column name is needed

### Requirement: Comparison semantics equal compare_signals

The comparison behind a plot SHALL run on the full-resolution data with the
same tolerance resolution, x-range meaning and coverage rule as
`compare_signals`, and the result SHALL carry the same row fields that
`compare_signals` returns for that column and tolerance set.

#### Scenario: Same arguments, same row
- **WHEN** an agent calls `compare_signals` and `plot_signals` with the same
  files, column, tolerance set and x-range
- **THEN** the verdict, status, counts, worst deviation and intervals of the
  plot result equal those of the `compare_signals` row

### Requirement: Plot content

A plot SHALL show the reference, the test, the tube's lower and upper bounds
and every violating region, with the reference and the test distinguishable
by line style as well as colour, a legend, the time column and the signal
column as axis labels, and a title stating the column, the verdict and the
resolved tolerances.

#### Scenario: Failing comparison
- **WHEN** a failing comparison is plotted
- **THEN** the plot shows reference, test, both tube bounds, a shaded region
  and markers on the violating test points, and the title says FAIL with the
  number of points outside and the non-zero resolved coefficients

#### Scenario: Passing comparison
- **WHEN** a passing comparison is plotted
- **THEN** the title says PASS and the plot contains no violation shading or
  markers

### Requirement: A plot never contradicts the verdict

Wherever the full-resolution comparison finds test points outside the tube,
the plot SHALL show a violation: every violation interval SHALL be shaded,
also when it is a single sample, and SHALL contain at least one drawn test
point marked as outside the tube. A passing plot SHALL show no violation.

#### Scenario: Single-sample spike in a long signal
- **WHEN** a 200 000-sample test signal differs from the reference only by one
  sample outside the tube and is plotted
- **THEN** the drawn test data contains that violating sample, it is marked,
  and its region is shaded wide enough to be visible

#### Scenario: Steep edge
- **WHEN** a step in the test is delayed beyond the x tolerance, producing a
  narrow violation at the edge
- **THEN** every violation interval contains a marked drawn test point

### Requirement: Drawing is bounded independently of the input length

Reference and test SHALL be reduced for drawing to the minimum and maximum
of a fixed number of equal-width time buckets, keeping the worst point of
every violation interval; tube bounds SHALL be drawn with all their points.
The result SHALL state how many points of each series were drawn.

#### Scenario: Large input
- **WHEN** two files of 200 000 samples are plotted
- **THEN** at most about two points per bucket are drawn for reference and
  test, the result states the drawn counts, and the structured result stays
  a few kilobytes

### Requirement: Inline PNG preview

Every successful call SHALL return a PNG preview of the plot, at most 800
pixels wide, inline as image content, next to a short text rendering and
structured content. SVG SHALL never be returned inline.

#### Scenario: Preview over stdio
- **WHEN** an MCP client calls `plot_signals` over stdio
- **THEN** the result contains a text block and an image block of MIME type
  `image/png`, 800 by 450 pixels

### Requirement: Plot file output

When an output path is given, the server SHALL write the plot to it: SVG when
the path ends in `.svg`, PNG when it ends in `.png` (case-insensitive); any
other extension SHALL fail the call. Without an output path nothing SHALL be
written. The server SHALL write no file other than the requested one.

#### Scenario: SVG for a document
- **WHEN** an agent passes the output path `report/z.svg` and `report` exists
- **THEN** a well-formed SVG file is written there and the result names the
  resolved path and the file size

#### Scenario: PNG file
- **WHEN** the output path ends in `.png`
- **THEN** a PNG file is written and the result states its pixel size

#### Scenario: Wrong extension
- **WHEN** the output path ends in `.pdf`
- **THEN** the call fails and nothing is written

#### Scenario: Preview only
- **WHEN** no output path is given
- **THEN** only the inline preview is returned and no file is created

### Requirement: Output path safety

The output path SHALL be resolved like input paths (relative paths against
the first workspace root, else the working directory) and SHALL be refused
when its resolved location is outside the workspace roots or, without
roots, outside the server's working directory; when its directory does not
exist (no directory is created); or when it exists and is not a regular
file.

#### Scenario: Outside the roots
- **WHEN** the client declares the root `/work/project` and the output path is
  `/tmp/z.svg`
- **THEN** the call fails with an error naming the path and the roots, and
  nothing is written

#### Scenario: Missing directory
- **WHEN** the output path's directory does not exist
- **THEN** the call fails with an error naming the directory and no directory
  is created

### Requirement: Existing files are kept unless overwrite is requested

An existing output file SHALL be refused unless `overwrite` is true, in
which case it SHALL be replaced. A refused or failed call SHALL leave the
file system unchanged.

#### Scenario: Existing file without overwrite
- **WHEN** the output path names an existing file and `overwrite` is false
- **THEN** the call fails with an error suggesting `overwrite=true` and the
  file is unchanged

#### Scenario: Existing file with overwrite
- **WHEN** the same call is made with `overwrite` true
- **THEN** the file is replaced by the new plot

### Requirement: Error statuses produce no plot

A comparison whose verdict is `error` (column missing, bad data, time ranges
that differ within the x-range, non-monotonic time or any other library
error status) SHALL fail the call with the problem text `compare_signals`
would report for that row, and SHALL write no file.

#### Scenario: Column missing from the test file
- **WHEN** an agent plots a column that exists only in the reference
- **THEN** the call fails with an error saying the column is absent from the
  test file, and no file is written

#### Scenario: Test covers a longer time range
- **WHEN** the test covers more time than the reference and no x-range is given
- **THEN** the call fails with an error naming both time spans and the
  x-range that compares the overlap

### Requirement: x-range restricts and zooms

The optional x-range SHALL restrict the comparison exactly as in
`compare_signals` and SHALL also be the time window shown, clipped to the
data of both files.

#### Scenario: Zoom on a window
- **WHEN** an agent plots with the x-range `{"lo": 0.4, "hi": 0.6}`
- **THEN** only test points in that window are judged and the x axis spans
  0.4 to 0.6

### Requirement: Deterministic files

Plotting the same input with the same arguments twice SHALL produce
byte-identical SVG and PNG output, so plot files can be kept in a repository
and diffed.

#### Scenario: Re-render
- **WHEN** the same comparison is plotted twice to SVG
- **THEN** both files are byte-identical

### Requirement: Compact result

The text and structured results SHALL contain the verdict headline, the
summary row, the resolved tolerances, the path and size of the file written,
the preview's size and the drawn point counts, and SHALL NOT contain sample
values.

#### Scenario: Text headline
- **WHEN** a failing comparison is plotted to a file
- **THEN** the text names the verdict and points outside, the file path, its
  format and size, and the preview size

### Requirement: Tool annotations

`plot_signals` SHALL be annotated as not read-only, destructive (it can
replace a file when asked), idempotent and closed-world.

#### Scenario: Client inspects annotations
- **WHEN** a client lists the tools
- **THEN** `plot_signals` is marked not read-only and destructive, while the
  other two tools stay read-only
