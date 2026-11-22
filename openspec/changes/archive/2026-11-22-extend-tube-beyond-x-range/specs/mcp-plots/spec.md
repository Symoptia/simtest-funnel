## MODIFIED Requirements

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
