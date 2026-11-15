# Design

## Context

See proposal.md for motivation. Today `compare()` in
`crates/simtest-funnel-core/src/compare.rs` returns `CompareResult { status,
lower, upper, errors }`. `errors.1[j]` is the signed deviation at test point
`errors.0[j] = t_test[j]` (positive above the upper bound, negative below the
lower bound, zero inside). Errors are computed for *every* test point, using
bounds clamped at their ends, but `classify_status` only lets points with
`x ∈ [eff_lo, eff_hi]` decide `Fail`, where
`eff_lo = max(x_range.lo, t_ref[0])` and `eff_hi = min(x_range.hi, t_ref[last])`.
Validation statuses (`NonMonotonic`, `LengthMismatch`, `EmptyRange`,
`InsufficientData`; `BufferTooSmall` only from `compare_into`) return empty
arrays.

The Python binding marshals results into a dict and wraps them in frozen
dataclasses; the WASM binding serialises camelCase structs through
`serde-wasm-bindgen`. The core has an optional `json` feature (serde) used by
`io.rs`. MSRV is 1.85.

## Goals / Non-Goals

**Goals:**
- One implementation in the core; bindings only marshal.
- Summary consistent with the verdict: a point counts as a violation exactly
  when it would contribute to `Fail`.

**Non-Goals:**
- No change to `compare`, `compare_into`, `CompareResult` or status logic.
- No re-computation of the tube or of deviations (no access to `y_test`
  needed); no estimation of exact tube-crossing x-locations.
- No convenience "compare and summarize" entry points beyond what is needed.

## Decisions

### D1. Core API: free function over existing comparison

`pub fn summarize(t_ref: &[f64], opts: &Options, result: &CompareResult) ->
ViolationSummary` in a new public module `summary.rs`, re-exported from the
crate root together with `ViolationSummary`, `ViolationInterval`,
`WorstDeviation` and `Direction`.
- Only `t_ref` (its first/last value) and `opts` are needed besides the
  result: the effective range needs the reference extent and `x_range`; test
  x-values are `result.errors.0`. Taking all four input arrays was rejected
  because two would be unused and invite mismatches.
- A new field on `CompareResult` was rejected: all fields are public, so adding
  one breaks struct-literal construction (not additive).

### D2. Judged points = points inside the effective range

A test point is *judged* iff `eff_lo <= x <= eff_hi` — the same predicate as
`classify_status`. Non-zero deviations outside (e.g. test data beyond the
reference for `MissingReference`) are ignored, so a `Pass` /
`MissingReference` / `MissingTest` summary always has zero violations, and a
`Fail` summary always has at least one.

### D3. Compared range = first..last judged test point

`compared_range = [x_first_judged, x_last_judged]`. Rationale: that is the
x-span the verdict is actually based on; using `[eff_lo, eff_hi]` would include
parts not covered by any test point. `None` when no point is judged.

### D4. Intervals = maximal same-sign runs of consecutive judged points

Start/end x are the x of the first/last violating test point in the run; a
single-point violation (including at the first/last judged point) has
`start_x == end_x` and `point_count == 1`. A direct sign flip between adjacent
points starts a new interval. Reported x-values are observed sample positions,
not interpolated crossings: deviations are zero inside the tube, so a crossing
cannot be located from the result alone, and interpolating would invent data.
`point_count` is included because it is cheap and makes single-sample
intervals recognisable.

### D5. Worst deviation: largest |deviation|, first occurrence on ties

Applies per interval and overall. Tube half-width in y at the worst x is
`(upper(x) - lower(x)) / 2`, with `upper`/`lower` linearly interpolated from
the result bounds using the same clamped interpolation as `errors.rs`
(promoted to `pub(crate)` and reused, so the evaluation location agrees with
the deviation's). Using the tolerance formula's `half_y` was rejected: it is
defined at reference points only and ignores the x-tolerance widening of the
tube, so it would not match the bounds the deviation was measured against.

### D6. Shares

- `fraction_of_points_outside = points_outside / points_compared`.
- `fraction_of_span_outside`: each judged point `j` represents
  `(x_{j+1} - x_{j-1}) / 2`, with the outer neighbours clamped to the first /
  last judged point (so the weights sum exactly to the compared range length).
  Sum of weights of violating points divided by the range length. This gives
  single-point violations a non-zero, spacing-aware share, unlike summing
  `end_x - start_x`. If the range length is zero the span share falls back to
  the point share (avoids 0/0 while staying meaningful).
- Both are `None` when no point is judged.

### D7. Non-comparison statuses

For validation statuses (and any result with no judged points) the summary
still returns status + echoed tolerances/x-range, with empty intervals,
`worst = None`, `compared_range = None`, counts 0, shares `None`. Returning an
error instead was rejected: the summary must be usable uniformly (pytest
messages, MCP) and the status already says why.

### D8. Echoed settings

`tolerances` and `x_range` come from the `opts` passed to `summarize` (callers
must pass the same options as to `compare`). The requested `x_range` is echoed
verbatim (may be infinite); the effective judged span is `compared_range`.

### D9. JSON (core `json` feature)

`#[cfg_attr(feature = "json", derive(Serialize))]` on the summary types and on
`Status`, `Tolerances`, `Range` (additive). Status serialises as its variant
name (`"Fail"`), `Direction` as `"above"`/`"below"`. Non-finite floats become
`null` (serde_json's behaviour for `f64`); Serialize only — no Deserialize, as
`null` bounds would not round-trip into `f64`.

### D10. Python binding

Native `summarize(t_reference, status, lower, upper, errors, options)` rebuilds
a `CompareResult` from the arrays and returns a dict; `simtest.funnel`
exposes `summarize(result: CompareResult, t_reference, options=None) ->
ViolationSummary` with frozen dataclasses `ViolationSummary`,
`ViolationInterval`, `WorstDeviation`; `direction` is
`Literal["above", "below"]`; absent values are `None`. `options=None` means
the same defaults `compare` uses. Stub `_simtest_funnel.pyi` updated.

### D11. WASM / TypeScript binding

`summarize(referenceX, status, lowerX, lowerY, upperX, upperY, errorsX,
errorsY, options)` in the wasm crate (typed arrays, because deserialising
`Float64Array` fields through serde is not supported reliably); returns a
camelCase object. The SDK exposes `summarize(result: CompareResult,
referenceX, options?) : ViolationSummary` with interfaces
`ViolationSummary`, `ViolationInterval`, `WorstDeviation` and
`direction: 'above' | 'below'`; absent values are `null`. Undefined options map
to the same defaults the wasm `compare` uses for undefined options.

## Risks / Trade-offs

- [Caller passes different options/reference to `summarize` than to `compare`]
  → documented contract; the summary only echoes and uses `t_ref` extents and
  `x_range`, so mismatch can mis-delimit the compared range but cannot change
  deviations.
- [Interval end-points are sample positions, under-estimating true extent by
  up to one sample spacing] → documented; the span share uses midpoint weights
  to compensate.
- [Unbounded x-range serialises as `null` in JSON] → documented in the spec.
- [Hand-built results with mismatched array lengths] → iterate over the common
  length of `errors.0`/`errors.1`; no panic.
