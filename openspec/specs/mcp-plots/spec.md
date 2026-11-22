# mcp-plots Specification

## Purpose
A plot tool on the local MCP server that draws one funnel comparison (one
signal column, one tolerance set) as an inline PNG preview the agent can look
at and, on request, as an SVG or PNG file for documents, never contradicting
the comparison's verdict.

## Requirements

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

### Requirement: Drawn tube agrees with the comparison

At every drawn test point the comparison judges, the point SHALL lie outside
the drawn tube if and only if the comparison found it outside the tube, and
then on the same side and at least as far outside as the comparison's
deviation. The drawn tube at an x is the range from the lowest drawn
lower-bound value to the highest drawn upper-bound value at that x, with
linear interpolation between drawn bound points.

#### Scenario: Violation markers lie outside the drawn tube
- **WHEN** a failing comparison is plotted (a single-sample spike in a long
  signal, a steep edge, a noisy signal, or the demo files)
- **THEN** every violation marker lies outside the drawn tube at the marker's
  x

#### Scenario: Passing plot stays inside the drawn tube
- **WHEN** a passing comparison is plotted
- **THEN** no drawn test point lies outside the drawn tube at its x

### Requirement: Drawing is bounded independently of the input length

Reference, test and both tube bounds SHALL be reduced for drawing to the
minimum and maximum of a fixed number of equal-width time buckets, keeping
the worst point of every violation interval in the test; a tube bound MAY
additionally contain the exact bound value at the x of a drawn test point, at
most one per drawn test point. The comparison and the summary SHALL use the
full-resolution data. The result SHALL state how many points of each series,
including each tube bound, were drawn.

#### Scenario: Large input
- **WHEN** two files of 200 000 samples are plotted
- **THEN** at most about two points per bucket are drawn for reference and
  test, each tube bound has at most two points per bucket plus one per drawn
  test point, the result states the drawn counts, and the structured result
  stays a few kilobytes

### Requirement: SVG output is fully vector

SVG output SHALL contain no embedded raster image, whatever the input length.

#### Scenario: SVG of a long smooth signal
- **WHEN** a 200 000-sample smooth signal, whose tube bounds have about one
  point per sample, is plotted to SVG
- **THEN** the file contains no raster image and stays below 250 kB

### Requirement: Inline PNG preview

Every successful call SHALL return a PNG preview of the plot, at most 800
pixels wide, inline as image content, next to a short text rendering and
structured content. SVG SHALL never be returned inline.

#### Scenario: Preview over stdio
- **WHEN** an MCP client calls `plot_signals` over stdio
- **THEN** the result contains a text block and an image block of MIME type
  `image/png`, 800 by 450 pixels

### Requirement: Plot file output

When an output path is given and writing is permitted (see output path
safety), the server SHALL write the plot to it: SVG when
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

### Requirement: Plot files only in roots or a configured output directory

A plot file SHALL be written only inside a workspace root declared by the
client or inside an output directory the user configured explicitly when
starting the server (command-line option or environment variable); a path
inside either SHALL be allowed. With neither, every output path SHALL be
refused with an error that explains both ways to enable writing, while calls
without an output path SHALL still return the inline preview.

#### Scenario: No roots and no output directory
- **WHEN** the client declares no workspace roots, the server was started
  without an output directory, and an agent passes an output path (even one
  inside the server's working directory)
- **THEN** the call fails with an error explaining that a client with
  workspace roots or `--output-dir` / `SIMTEST_FUNNEL_MCP_OUTPUT_DIR` enables
  writing, and nothing is written

#### Scenario: Preview without a write location
- **WHEN** the client declares no workspace roots, no output directory is
  configured, and no output path is given
- **THEN** the call succeeds with the inline preview

#### Scenario: Configured output directory
- **WHEN** the server was started with `--output-dir /home/me/plots`, the
  client declares no roots, and the output path is `z.svg`
- **THEN** the plot is written to `/home/me/plots/z.svg`, and an output path
  outside `/home/me/plots` is refused

#### Scenario: Roots and an output directory
- **WHEN** the client declares a root and an output directory is configured
- **THEN** an output path inside either is written and one outside both is
  refused with an error naming both

#### Scenario: Missing output directory at start-up
- **WHEN** the server is started with an output directory (option or
  environment variable) that does not exist or is not a directory
- **THEN** the server exits with an error naming the directory instead of
  serving

### Requirement: Output path safety

A relative output path SHALL be resolved against the first workspace root,
else the first configured output directory. The output path SHALL be refused
when its resolved location (directory and any symbolic link resolved) is
outside the allowed directories; when its directory does not exist (no
directory is created); or when it exists and is not a regular file. All
output path checks SHALL happen before any CSV file is read.

#### Scenario: Outside the roots
- **WHEN** the client declares the root `/work/project` and the output path is
  `/tmp/z.svg`
- **THEN** the call fails with an error naming the path and the roots, and
  nothing is written

#### Scenario: Missing directory
- **WHEN** the output path's directory does not exist
- **THEN** the call fails with an error naming the directory and no directory
  is created

#### Scenario: Directory replaced by a symbolic link during the call
- **WHEN** the output directory inside a root (or a directory above it) is
  replaced by a symbolic link to a directory outside the roots after the
  output path was checked and before the file is written
- **THEN** the call fails and nothing is written outside the roots

#### Scenario: Existing file replaced by a symbolic link during the call
- **WHEN** with `overwrite` true the existing output file is replaced by a
  symbolic link to a file outside the roots during the call
- **THEN** the link is replaced by the new plot inside the root and the file
  it pointed to is unchanged

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

#### Scenario: File created during the call
- **WHEN** `overwrite` is false and another process creates the output file
  after the output path was checked
- **THEN** the call fails with an error suggesting `overwrite=true`, that
  file is unchanged and no temporary file is left behind

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

#### Scenario: Window edges within the x tolerance
- **WHEN** an agent plots an hourly daily cycle against the same cycle 2 h
  late with `atolx = 10800`, `atoly = 0.05` and a 2-day x-range
- **THEN** the plot reports PASS with all 49 points inside the tube, the
  same row as `compare_signals`, and the drawn tube reaches both edges of
  the view

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
replace a file when asked) and idempotent, and as closed-world unless network
access was enabled at start-up (`mcp-url-sources`), in which case it is
open-world.

#### Scenario: Client inspects annotations
- **WHEN** a client lists the tools
- **THEN** `plot_signals` is marked not read-only and destructive, while the
  other two tools stay read-only

#### Scenario: Network access enabled
- **WHEN** the server was started with `--allow-network` and a client lists
  the tools
- **THEN** `plot_signals` is marked open-world, not read-only and destructive

### Requirement: Plot time limit

`plot_signals` SHALL accept the same time limit as `compare_signals` (seconds,
60 by default, positive and finite), counted from the start of the call.
A plot is one comparison, so when the limit stops it the call SHALL fail
with an error saying the comparison did not finish within the limit and
suggesting a larger limit or a narrower x-range, and SHALL write no file.

#### Scenario: Comparison exceeds the limit
- **WHEN** an agent plots a column whose comparison takes seconds with a time
  limit of 0.2 s and an output path
- **THEN** the call fails with an error naming the time limit, and no file is
  written

#### Scenario: Comparison within the limit
- **WHEN** the comparison finishes within the time limit
- **THEN** the plot is produced exactly as without a time limit

### Requirement: Plot time limit covers rendering

The plot time limit SHALL cover reading the files, the comparison and
rendering. Reading and rendering are not interrupted, but the limit SHALL
be checked before rendering and again immediately before the file is put
in place; when it has passed, the call SHALL fail with an error naming the
limit and write no file.

#### Scenario: Limit passes while rendering
- **WHEN** the time limit passes while the plot file is being rendered
- **THEN** the call fails with an error naming the time limit, and neither
  the file nor a temporary file is left in the target directory

### Requirement: A cancelled plot writes nothing

When a `plot_signals` call is cancelled, no file SHALL be written for it,
also when the cancellation arrives after the comparison finished: the
cancellation SHALL be checked before rendering and immediately before the
file is put in place, ordered against putting it in place so that the file
either appears before the call is reported cancelled or never.

#### Scenario: Cancelled while rendering
- **WHEN** the client cancels a `plot_signals` call with an output path
  while its plot is being rendered
- **THEN** the call is reported cancelled at once, and after the abandoned
  work has finished no file (and no partial or temporary file) exists in the
  target directory

### Requirement: Plot write does not trust the checked path

Because the file is written only after reading, comparing and rendering, the
write SHALL NOT trust the checked output path. On platforms that support it,
the file SHALL be written relative to a handle of the target directory that is
opened without following a symbolic link and verified to lie inside the
allowed directories immediately before the file is put in place, and a
symbolic link at the file name SHALL be replaced, never followed.

#### Scenario: Directory handle verified before the write
- **WHEN** a plot file is written on a platform that supports directory handles
- **THEN** the target directory is opened without following a symbolic link
  and verified to lie inside the allowed directories immediately before the
  file is put in place

#### Scenario: Symbolic link at the file name
- **WHEN** the output name is a symbolic link when the file is put in place
  and `overwrite` is true
- **THEN** the link itself is replaced by the plot and its target is not
  written

### Requirement: Output directory re-checked on other platforms

On platforms without such directory handles, the output directory SHALL be
resolved and checked against the allowed directories again immediately before
the write.

#### Scenario: Directory moved outside the roots before the write
- **WHEN** on such a platform the output directory resolves outside the
  allowed directories at the time of the write
- **THEN** the call fails and nothing is written

### Requirement: Reported plot path

The path reported in the result SHALL be where the file was written.

#### Scenario: Relative output path
- **WHEN** an agent passes a relative output path that is written inside the
  first workspace root
- **THEN** the result reports the resolved path of the written file

### Requirement: Plot file put in place in one step

The plot SHALL be written to a temporary file in the target directory and put
in place under the output name in one step: with `overwrite` by an atomic
replacement, otherwise by an operation that fails if the name exists. No
partial file SHALL ever appear under the output name, and a file created by
someone else meanwhile SHALL never be replaced without `overwrite`.

#### Scenario: No partial file under the output name
- **WHEN** a plot file is being written
- **THEN** the output name holds either nothing or the previous file until the
  complete plot replaces it in one step

#### Scenario: Temporary file removed on failure
- **WHEN** putting the plot in place fails
- **THEN** no temporary file is left in the target directory

### Requirement: Plot result reports a missing x tolerance

When the comparison behind a plot fails and no x coefficient (`atolx`, `ltolx`,
`rtolx`) was given in its tolerance set, the plot result SHALL carry the same
hint note that `compare_signals` gives for such a row.

#### Scenario: Failing plot without an x coefficient
- **WHEN** an agent plots a column whose test step is slightly delayed with a
  tolerance set that gives only `atoly`, and the comparison fails
- **THEN** the result's notes contain the hint suggesting an x tolerance

#### Scenario: Failing plot with an x coefficient
- **WHEN** the same column is plotted with `atolx` given and still fails
- **THEN** the result contains no such hint

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

### Requirement: Plot inputs from URLs

`plot_signals` SHALL accept URLs for its reference and test inputs as
`mcp-url-sources` defines. The output path SHALL stay a local path: a URL as
output path SHALL be refused, and all output path checks SHALL happen before
any input is fetched.

#### Scenario: Plot a pair from a URL
- **WHEN** network access is enabled and an agent plots the day-1 pair from
  an Open-Meteo URL with header line 4 and an output path inside a root
- **THEN** the URL is fetched (or its cached copy reused), the plot file is
  written locally and the result reports the URL's fetch time, size and
  SHA-256

#### Scenario: URL as output path
- **WHEN** an agent passes `https://example.org/plot.svg` as output path
- **THEN** the call fails with an error saying the output path must be a
  local path, and nothing is fetched or written

#### Scenario: Refused output path
- **WHEN** the output path lies outside the roots and the inputs are URLs
- **THEN** the call fails before any URL is fetched
