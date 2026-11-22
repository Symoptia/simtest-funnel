## MODIFIED Requirements

### Requirement: x-range restricts and zooms

The optional x-range SHALL restrict the comparison exactly as in
`compare_signals` and SHALL also be the time window shown, clipped to the
data of both files. Its argument description SHALL match that of
`compare_signals`: bounds in seconds since 1970 on a date-time axis, and the
tube of the whole reference over the window, built from the reference
extended beyond it as far as needed.

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

#### Scenario: Argument descriptions agree
- **WHEN** an agent lists the tools
- **THEN** the `x_range` descriptions of `plot_signals` and
  `compare_signals` both state the seconds-since-1970 unit and the tube
  beyond the window

## ADDED Requirements

### Requirement: Plot of a column with itself refused

`plot_signals` SHALL refuse, without writing anything, a plot whose test
column is the same column of the same loaded file as the reference column
(no test path or the reference file again, and no or the same test column),
since it would pass trivially.

#### Scenario: No test file and no test column
- **WHEN** an agent plots a column of one file without `test_path` and
  without `test_column`
- **THEN** the call fails saying the column would be compared with itself,
  and no file is written
