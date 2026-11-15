# violation-summary Specification

## Purpose
Describes, for the tolerances actually used, how much and where a funnel
comparison violated its tube, as a compact deterministic summary derived
from an existing comparison and identical in Rust, Python and TypeScript.

## Requirements

### Requirement: Summary is derived from an existing comparison

The library SHALL provide a violation summary computed from a completed
comparison (its reference x-values, its options and its result). Producing a
summary MUST NOT change the comparison algorithm, the comparison result, or
the meaning of any existing result field.

#### Scenario: Comparison result is unchanged
- **WHEN** a caller runs a comparison and then requests its violation summary
- **THEN** the comparison status, bounds and errors are identical to those of
  the same comparison run without requesting a summary

#### Scenario: Summary is deterministic
- **WHEN** a summary is requested twice for the same comparison inputs, options
  and result
- **THEN** both summaries are equal field by field

### Requirement: Verdict and echoed settings

The summary SHALL report the comparison status unchanged, the tolerance
coefficients and the requested x-range from the options it was given, and the
compared range: the x-interval from the first to the last test point that the
comparison judged (test points inside the requested x-range intersected with
the reference x-extent).

#### Scenario: Settings are echoed back
- **WHEN** a summary is requested for a comparison run with `atoly = 0.1` and
  x-range `[0, 2]`
- **THEN** the summary reports `atoly = 0.1`, the other coefficients as given,
  and the x-range `[0, 2]`

#### Scenario: Compared range reflects the judged test points
- **WHEN** the reference spans `[0, 4]`, the test points are `0, 1, 2, 3, 4, 5`
  and the x-range is unbounded
- **THEN** the compared range is `[0, 4]`

### Requirement: Violation intervals

The summary SHALL list violation intervals in increasing x order. An interval
is a maximal run of consecutive judged test points whose signed deviation is
non-zero with the same sign. Each interval MUST report its start x and end x
(first and last test point of the run), its direction (above the upper bound
or below the lower bound), its number of test points, its worst signed
deviation and the x where that occurs.

#### Scenario: One excursion above the tube
- **WHEN** the judged test points at x = 1, 2, 3 lie above the tube with
  deviations 0.2, 0.5, 0.1 and all other judged points are inside
- **THEN** the summary contains exactly one interval with start x 1, end x 3,
  direction above, 3 points, worst deviation 0.5 at x 2

#### Scenario: Direction change splits intervals
- **WHEN** a judged test point lies above the tube and the next judged test
  point lies below it
- **THEN** they belong to two separate intervals with directions above and
  below

#### Scenario: Single-point violation at the boundary
- **WHEN** only the first judged test point lies outside the tube
- **THEN** the summary contains one interval whose start x and end x both equal
  that point's x and whose point count is 1

#### Scenario: Deviations outside the compared range are ignored
- **WHEN** test points beyond the reference x-extent have non-zero deviations
- **THEN** those points do not contribute to any interval, to the worst
  deviation, or to the shares outside

### Requirement: Overall worst deviation

When at least one judged test point is outside the tube, the summary SHALL
report the overall worst deviation: the signed deviation with the largest
magnitude (first occurrence in x on ties), its x, and the tube half-width in y
at that x, defined as half the vertical distance between the upper and lower
bound evaluated at that x. Otherwise the worst deviation MUST be absent.

#### Scenario: Worst deviation with tube half-width
- **WHEN** the worst judged deviation is -0.3 at x = 5 and the bounds at x = 5
  are 1.2 (upper) and 0.8 (lower)
- **THEN** the summary reports worst deviation -0.3 at x 5 with tube half-width
  0.2

#### Scenario: Passing comparison has no worst deviation
- **WHEN** the comparison status is pass
- **THEN** the worst deviation is absent and the interval list is empty

### Requirement: Shares outside the tube

The summary SHALL report the number of judged test points, the number outside
the tube, the share of judged test points outside the tube, and the share of
the compared range outside the tube. For the span share each judged test point
represents the x-length halfway to its neighbouring judged points; the share is
the represented length of points outside divided by the compared range length.

#### Scenario: All points outside
- **WHEN** every judged test point is outside the tube
- **THEN** both shares equal 1

#### Scenario: Span share weights by point spacing
- **WHEN** the judged test points are at x = 0, 1, 2, 4 and only the point at
  x = 4 is outside
- **THEN** the share of points outside is 0.25 and the share of the compared
  range outside is 0.25 (length 1 of 4)

#### Scenario: Zero-length compared range
- **WHEN** the compared range has zero length (all judged points share one x)
- **THEN** the span share equals the point share

### Requirement: Summary for comparisons that did not run

When the comparison returned a validation status (non-monotonic x, length
mismatch, empty range, buffer too small, or insufficient data), or judged no
test point, the summary SHALL still be produced with the status and echoed
settings, an empty interval list, no worst deviation, no compared range, zero
point counts, and absent shares.

#### Scenario: Non-monotonic input
- **WHEN** the comparison status is non-monotonic
- **THEN** the summary reports that status, the echoed tolerances and x-range,
  no intervals, no worst deviation, no compared range and absent shares

### Requirement: Identical summary in every binding

The summary SHALL be available from the Rust core, the Python package
`simtest.funnel` and the TypeScript SDK `@simtest-js/funnel` with the same
fields and identical numeric values for the same comparison. Absent values MUST
be `None` in Rust and Python and `null` in TypeScript. The Python API MUST be
fully typed and the TypeScript API MUST not use `any` in its public types.

#### Scenario: Cross-language parity on a corpus case
- **WHEN** the same failing corpus comparison is summarized in Rust, Python and
  TypeScript
- **THEN** status, interval count, interval bounds, worst deviation, tube
  half-width and both shares are equal across the three

### Requirement: JSON serialisation in the core

With the core's optional `json` feature enabled, the summary SHALL serialise to
JSON with snake_case field names, the status as its variant name, directions as
`"above"` / `"below"`, and absent values as `null`. Non-finite numbers (such as
an unbounded x-range) MUST serialise as `null`.

#### Scenario: Serialised failing summary
- **WHEN** a failing summary with one interval above the tube is serialised
- **THEN** the JSON contains `"status":"Fail"` and an interval with
  `"direction":"above"`

#### Scenario: Unbounded x-range
- **WHEN** a summary for the default unbounded x-range is serialised
- **THEN** the x-range bounds appear as `null`
