## MODIFIED Requirements

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

#### Scenario: Time shift within the x tolerance at the window edges
- **WHEN** an agent compares an hourly daily cycle with the same cycle 2 h
  late, `atolx = 10800` and `atoly = 0.05`, with a 2-day x-range in the
  middle of 6 days of data
- **THEN** the row passes with 49 judged points, as those points do when
  the whole files are compared

## ADDED Requirements

### Requirement: Description explains the x-range window

The `compare_signals` description SHALL state that only test points inside
the x-range are judged, that the tube there is built from the reference
also beyond the x-range so a time shift within the x tolerance passes at
its edges, and that the bases of `rtolx` / `rtoly` are the reference inside
the x-range.

#### Scenario: Agent learns the window semantics
- **WHEN** an agent reads the `compare_signals` description
- **THEN** it finds that only points inside x_range are judged, against a
  tube built from the reference extended beyond x_range
