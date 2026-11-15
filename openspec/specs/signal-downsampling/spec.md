# signal-downsampling Specification

## Purpose
Reduces a signal (x/y samples) to a bounded number of points for output
purposes such as plots and agent responses, keeping each region's extremes
and caller-pinned points so a reduced plot never hides a violation, with
identical results in Rust, Python and TypeScript.

## Requirements

### Requirement: Min/max per equal-width bucket

Given a signal and a bucket count `B >= 1`, the library SHALL divide the
x-extent from the first to the last sample into `B` buckets of equal
x-width (the last bucket includes the last sample) and keep, for each
non-empty bucket, its lowest-y and highest-y sample. Kept samples SHALL be
returned in input order (increasing x), each at most once.

#### Scenario: Two buckets keep each bucket's extremes
- **WHEN** x = 0, 1, …, 9, y = 0, 5, 1, 2, 9, 3, 4, 8, 6, 7 and B = 2 are
  passed with no pinned points
- **THEN** the samples at indices 0, 4, 5, 7, 9 are returned, in that order

#### Scenario: Empty buckets contribute nothing
- **WHEN** a signal has samples only at the two ends of its x-extent and
  in buckets near them, leaving middle buckets without samples
- **THEN** the result contains only samples from non-empty buckets plus the
  first and last sample

### Requirement: Tie and NaN handling for extremes

When several samples of a bucket share the lowest (or highest) y, the
first of them in input order SHALL be kept. A sample whose y is NaN SHALL
never be selected as a bucket extreme; it is kept only if it is the first
or last sample or is pinned.

#### Scenario: Ties keep the first occurrence
- **WHEN** a bucket's samples have y = 2, 1, 1, 3, 3
- **THEN** the first sample with y = 1 and the first sample with y = 3 are
  kept from that bucket

#### Scenario: NaN is not an extreme
- **WHEN** a bucket's samples have y = 1, NaN, 2
- **THEN** the samples with y = 1 and y = 2 are kept from that bucket and
  the NaN sample is not

### Requirement: First and last samples are always kept

The result SHALL always contain the first and the last sample of a
non-empty signal, whether or not they are bucket extremes.

#### Scenario: Endpoints that are not extremes
- **WHEN** a signal is downsampled whose first and last samples are neither
  the lowest nor the highest sample of their buckets
- **THEN** the result still starts with the first sample and ends with the
  last sample

### Requirement: Pinned x-positions are kept

The caller SHALL be able to pass x-positions that must be kept. Each
finite pin selects the sample with the nearest x (on an exact tie between
two neighbours, the lower x); if several samples share that x, all of them
are kept. Pins outside the x-extent select the first or last sample. NaN
pins are ignored; duplicate pins have no further effect.

#### Scenario: Pin keeps the nearest sample
- **WHEN** the two-bucket example signal is downsampled with B = 2 and the
  pinned x-position 2.2
- **THEN** the samples at indices 0, 2, 4, 5, 7, 9 are returned

#### Scenario: Pin midway between samples
- **WHEN** a pin lies exactly midway between the samples at x = 2 and x = 3
- **THEN** the sample at x = 2 is kept

#### Scenario: Duplicate x-values
- **WHEN** a pin's nearest x-value occurs at two consecutive samples (an
  event with a repeated time point)
- **THEN** both samples are kept

#### Scenario: Pins outside the signal and NaN pins
- **WHEN** the pins are a value below the first x, a value above the last x
  and NaN
- **THEN** the result equals the result without pins

### Requirement: Violations stay visible when worst points are pinned

When a failing comparison's test signal is downsampled with the worst
x-position of every violation interval of its violation summary pinned,
every violation interval SHALL still contain at least one retained test
sample, and that sample SHALL lie outside the tube.

#### Scenario: Hard downsampling of a failing corpus case
- **WHEN** a failing corpus comparison's test signal (thousands of samples,
  tens of violation intervals) is downsampled to 50 buckets with each
  interval's worst x pinned
- **THEN** every violation interval contains a retained sample whose
  deviation is non-zero

### Requirement: Bounded output size

For a signal of `n` samples, `B` buckets and `M` samples selected by pins,
the result SHALL contain at most `min(n, 2·B + 2 + M)` samples. `M` is at
most the number of distinct finite pins when x is strictly increasing.

#### Scenario: Output length bound
- **WHEN** a signal of 5041 samples is downsampled with B = 50 and 35 pins
- **THEN** the result contains at most 137 samples

### Requirement: Small signals are returned unchanged

When `n <= 2·B`, the result SHALL contain every sample of the input in
order, regardless of pins.

#### Scenario: Signal already small enough
- **WHEN** a signal of 8 samples is downsampled with B = 4
- **THEN** all 8 samples are returned in their original order

#### Scenario: Empty and single-sample signals
- **WHEN** an empty signal or a signal with one sample is downsampled
- **THEN** the result is equal to the input

### Requirement: Invalid input is rejected

The library SHALL reject, with an error that names the problem and without
producing a result: x and y of different lengths, a non-finite x-value,
x-values that decrease anywhere (equal consecutive x-values are allowed),
and a bucket count below 1. Each binding SHALL raise its language's usual
error for these cases.

#### Scenario: Length mismatch
- **WHEN** x has 3 values and y has 2
- **THEN** an error reporting a length mismatch is raised

#### Scenario: Decreasing x
- **WHEN** x = 0, 2, 1
- **THEN** an error reporting non-monotonic x is raised

#### Scenario: Zero buckets
- **WHEN** the bucket count is 0
- **THEN** an error reporting that at least one bucket is required is
  raised

### Requirement: Output carries indices and values

The result SHALL provide the indices of the kept samples into the input
and the corresponding x and y values, all in the same order, so callers
holding further arrays parallel to the signal can select the same samples.

#### Scenario: Indices select the returned values
- **WHEN** a signal is downsampled
- **THEN** for every position k of the result, its x and y equal the input
  x and y at its k-th index

### Requirement: Identical results in every language

The Rust, Python and TypeScript APIs SHALL return the same indices and
values for the same input, bucket count and pins.

#### Scenario: Cross-language parity on a corpus signal
- **WHEN** the same corpus test signal is downsampled with the same bucket
  count and pins in Rust, Python and TypeScript
- **THEN** all three return identical indices

### Requirement: Post-processing only

Downsampling SHALL NOT be applied by the comparison or the violation
summary, and calling it SHALL NOT change their inputs or results.

#### Scenario: Comparison unaffected
- **WHEN** a comparison and its summary are computed before and after
  downsampling the same test signal
- **THEN** both comparisons and both summaries are identical
