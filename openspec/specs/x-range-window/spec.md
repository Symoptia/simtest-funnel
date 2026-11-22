# x-range-window Specification

## Purpose
Defines what a funnel comparison restricted to an x-range window judges,
which part of the reference its tube is built from, what stays relative to
the window and what the result arrays contain, identically in the Rust,
Python, TypeScript and MCP APIs.

## Requirements

### Requirement: Only test points inside the window are judged

A comparison with an x-range `[lo, hi]` SHALL judge only the test points
whose x lies in the window intersected with the reference x-extent; only
they decide `Fail` and enter the violation summary. Without an x-range the
window is unbounded and every result SHALL be bit-identical to the
comparison before this change.

#### Scenario: Points outside the window are not judged
- **WHEN** a test point at x = 0.1 lies far outside the tube and the
  comparison uses the x-range `[0.5, 1]`
- **THEN** that point does not make the status `Fail`

#### Scenario: Unbounded window
- **WHEN** a comparison of an LBNL corpus case is run without an x-range
- **THEN** status, bounds and deviations equal the stored reference output
  bit for bit, as before this change

### Requirement: Tube built from the reference beyond the window

The tube for a window SHALL be built from the reference points inside the
window plus, on each side, every reference point whose x half-width, taken
twice, reaches the window, and at least three further samples. Where the
window reaches the first or last reference point there is nothing to
extend with on that side.

#### Scenario: Time shift within the x tolerance at a window edge
- **WHEN** an hourly daily cycle is compared with the same cycle 2 h late,
  `atolx = 10800` (3 h), `atoly = 0.05`, x-range 2 days in the middle of 6
- **THEN** all 49 test points in the window pass, including those at the
  left edge that failed when the reference was clipped to the window

#### Scenario: Window at the data start
- **WHEN** the same comparison uses a window that starts at or before the
  first reference sample
- **THEN** the test points in the first hours fail exactly as in the
  comparison over the full range

#### Scenario: Window narrower than the x tolerance
- **WHEN** the window is 1 h wide (two samples) and `atolx` is 3 h
- **THEN** both points are judged as in the full-range comparison

### Requirement: In-window equivalence with the full-range comparison

When `rtolx` and `rtoly` are zero, every test point inside the window
SHALL get the same verdict (inside or outside the tube) as in the same
comparison without an x-range. Its deviation and the bounds at its x SHALL
equal the full-range values up to floating-point rounding.

#### Scenario: Random signals and windows
- **WHEN** random references, shifted noisy tests on another grid, random
  `atolx`, `ltolx`, `atoly`, `ltoly` and random windows (also partly
  outside the data and narrower than the x tolerance) are compared with
  and without the window
- **THEN** every judged point has the same verdict in both comparisons and
  the windowed status is `Fail` exactly when one of them is outside

### Requirement: Range-relative bases and coverage stay within the window

The bases of the range-relative tolerances (x and y range of the
reference, and the magnitudes of the constant-reference fallback) SHALL be
computed from the reference points inside the window. Coverage
(`MissingReference` / `MissingTest`) SHALL compare both x-extents clipped
to the window, and fewer than two reference or test points inside the
window SHALL give `InsufficientData`.

#### Scenario: rtoly relative to the window
- **WHEN** a ramp from 0 to 100 is compared with a test 0.5 above it,
  `rtoly = 0.01`, without an x-range and with the x-range `[0, 10]`
- **THEN** the full comparison passes (half-width 1.0) and the windowed one
  fails (half-width 0.1)

#### Scenario: Window wholly outside the data
- **WHEN** the window starts after the last reference sample, even by less
  than the x tolerance
- **THEN** the status is `EmptyRange`

### Requirement: Result arrays of a windowed comparison

With an x-range, the lower and upper bounds SHALL be those of the tube
built from the extended reference, reaching beyond the window. The
deviations SHALL keep one entry per test point at the test x-values and
SHALL be `0` for test points outside the x-range.

#### Scenario: Bounds reach beyond the window
- **WHEN** the daily-cycle comparison uses the 2-day window
- **THEN** the lower bound starts more than 3 h before the window and the
  upper bound ends more than 3 h after it

#### Scenario: Deviations outside the window
- **WHEN** a windowed comparison has test points before and after the
  window
- **THEN** their deviations are `0` and their x-values are the test
  x-values

### Requirement: Window cost does not grow with the record

The extension SHALL be found without scanning the reference, and its size
SHALL depend on the x tolerance and the sampling near the window, not on
the length of the reference, except when the local x tolerance `ltolx` is
0.5 or more, where the reference up to the data end on that side MAY be
used.

#### Scenario: Small window on a long record
- **WHEN** the window `[1000000, 1000010]` (11 samples) lies in a reference
  of 2 million samples spaced 1 apart and `atolx = 5`
- **THEN** the tube is built from 13 samples more on each side of the
  window
