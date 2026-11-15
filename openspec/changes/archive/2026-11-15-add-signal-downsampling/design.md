# Design

## Context

See proposal.md for motivation and specs/signal-downsampling/spec.md for
the behaviour contract. The core (`crates/simtest-funnel-core`) already
hosts `compare` and `summarize`; the Python binding marshals numpy arrays
through PyO3 into dicts that `simtest.funnel` wraps in frozen dataclasses,
and the WASM binding takes `Float64Array`s and returns camelCase objects
that `packages/sdk` types. `compare` treats invalid input by returning a
validation `Status`; there is no error type in the core yet. `summarize`
reports `worst_x` per violation interval as an observed test x-value
(`errors.0[j] = t_test[j]`). MSRV is 1.85; the core has no dependencies
outside the optional `json` feature.

## Goals / Non-Goals

**Goals:**
- One implementation in the core; bindings only marshal and map errors.
- O(n + p log n) time for n samples and p pins, single pass over the
  samples, no allocation proportional to `B`.
- Fully deterministic output that depends only on the inputs (no floating
  summation order differences across languages, since only the core
  computes).

**Non-Goals:**
- No streaming / chunked API, no in-place variant.
- No convenience that runs `compare` + `summarize` + downsampling in one
  call; callers compose them (keeps the post-processing boundary explicit).
- No downsampling of tube bounds (already compact).

## Decisions

### D1. API: `downsample_min_max(x, y, buckets, pinned_x)`

Core: new public module `downsample.rs` with

```rust
pub fn downsample_min_max(
    x: &[f64], y: &[f64], buckets: usize, pinned_x: &[f64],
) -> Result<Downsampled, DownsampleError>;
pub struct Downsampled { pub indices: Vec<usize>, pub x: Vec<f64>, pub y: Vec<f64> }
pub enum DownsampleError { LengthMismatch { x_len, y_len }, NonFiniteX { index },
                           NonMonotonic { index }, ZeroBuckets }
```

re-exported from the crate root. The method name is in the function name so
a later LTTB variant can sit beside it without a mode flag. Pins are a plain
slice (empty for none) rather than `Option`, which is simpler and has the
same meaning. `DownsampleError` implements `Display` and
`std::error::Error`.
- Returning a `Status` like `compare` was rejected: `Status` describes
  comparison outcomes, and adding variants to it would be a breaking change
  for exhaustive matches.

Python: `downsample_min_max(x, y, buckets, pinned_x=None) -> Downsampled`
(frozen dataclass with `indices: NDArray[np.intp]`, `x`, `y:
NDArray[np.float64]`); errors raise `ValueError`.
TypeScript: `downsampleMinMax(x, y, buckets, pinnedX?) : Downsampled`
(`{ indices: Uint32Array; x: Float64Array; y: Float64Array }`); errors
throw `Error`.

### D2. Size parameter is a bucket count

`buckets` is the number of x-buckets, not a maximum output length. It maps
directly onto the agreed method ("divide the x-axis into a requested number
of buckets") and onto plotting (≈ one bucket per pixel column). A
max-points parameter was rejected because pins and endpoints make an exact
maximum impossible to honour without dropping pins, which would defeat
their purpose.

**Output bound (precise):** `len ≤ min(n, 2·B + 2 + M)`, where `M` is the
number of distinct samples selected by pins that are not already kept.
Each bucket contributes at most 2 samples; the first and last sample add at
most 1 each (when they are not their bucket's extremes); each pin adds the
samples it selects. With strictly increasing x, `M ≤` number of distinct
finite pins; with repeated x-values a pin can select every sample at its
x. Callers wanting at most `N` points without pins use `B = (N − 2) / 2`.

**Unchanged threshold:** if `n ≤ 2·B` all samples are returned (the
reduction could not shrink it meaningfully, and the spec's "already at or
below the target size" is read as target `2·B`). Validation still runs
first, so invalid input is rejected even when small.

### D3. Equal x-width buckets

Bucket `k` of sample `i` is `min(B − 1, floor((x_i − x_0) / (x_{n−1} − x_0) · B))`
(computed in that order in `f64`); if the span is 0 all samples fall in
bucket 0. Because each operation is monotone in `x` under IEEE rounding,
`k` is non-decreasing in `i`, so buckets are contiguous index runs found in
one pass.
- Equal x-width matches how a plot uses the x-axis: each bucket covers the
  same horizontal extent, so the output resolution is uniform on screen.
  With strongly non-uniform sampling (adaptive solvers, events) dense
  regions collapse to their envelope and sparse regions keep all their
  samples (a bucket with one or two samples keeps them all), which is what
  a plot can show anyway.
- Equal sample-count buckets were rejected: they spend output points where
  the solver stepped finely (often a stiff but visually small region) and
  can merge a long sparse stretch into one bucket, flattening visible
  structure.
- Empty buckets simply contribute nothing.

### D4. Extremes: first occurrence, NaN never selected

Within a bucket, min and max use strict comparisons so the first
occurrence wins ties; NaN y-values fail every comparison and are thus
never selected. When min and max are the same sample (one sample, or a
constant bucket) it is kept once. A bucket whose y-values are all NaN
contributes nothing (beyond endpoints/pins). Rejecting NaN y as an error
was rejected: output post-processing should not fail on data a plot can
still show.

### D5. Pin matching: nearest sample, all samples at that x

For each pin (binary search on x): the nearest sample by `|x_i − pin|`,
ties between the two neighbours going to the lower x; then every sample
with exactly that x-value is kept (handles repeated event time points where
the violating sample may be either of the pair). Pins outside the extent
therefore select the first/last sample, which is kept anyway; NaN pins are
skipped; infinite pins behave like out-of-range pins. Duplicate pins
select the same samples, so they have no further effect.
- Exact matching was rejected: it silently drops pins that went through a
  lossy round-trip (JSON, float32, text) — the pinned point would be
  missing, the failure mode the feature exists to prevent. For the intended
  input (`worst_x` from `summarize`, an exact test x) nearest equals exact.
- A tolerance parameter was rejected as unnecessary API surface.

### D6. Validation and edge cases

Checked in order, always (also for small inputs): length mismatch →
`LengthMismatch`; `buckets == 0` → `ZeroBuckets`; any non-finite x →
`NonFiniteX { index }`; any `x[i] < x[i−1]` → `NonMonotonic { index }`.
Equal consecutive x-values are allowed, matching `compare`'s
non-decreasing rule. Empty and one-sample input return themselves.
Bindings accept signed integers / JS numbers for `buckets` and map values
below 1 (and non-integers in JS) to the same "at least one bucket" error
message, so negative numbers do not wrap.

### D7. Output: indices plus gathered values

`Downsampled` carries indices and the gathered x/y. Indices let callers
with parallel arrays (several signals on one time grid, or `errors.1` of a
comparison) select the same samples; x/y make the common plotting case a
one-liner in every language. Returning only indices was considered
(simplest), but in TypeScript gathering from `Float64Array` is boilerplate
every caller would rewrite; the duplication costs at most `2·len` floats.

### D8. Bindings

Python native `downsample_min_max(x, y, buckets, pinned_x)` returns
`(indices, x, y)` numpy arrays (indices as `uintp`, converted to `intp`
by the wrapper) built from the core result; the
package wrapper converts inputs with the existing `_as_f64`. WASM
`downsampleMinMax(x, y, buckets, pinnedX)` returns an object with
`indices: Uint32Array`, `x`, `y: Float64Array` built directly with
`js_sys` typed arrays (no serde round-trip through `number[]`); the SDK
types it and passes an empty array for omitted pins. Core error messages
(`Display`) are passed through unchanged so all languages report the same
text.

## Risks / Trade-offs

- [Equal-width buckets give few points to a dense, visually important
  region] → `B` is chosen by the caller; pins guarantee violations survive.
- [Repeated x-values let one pin add more than one sample] → stated in the
  bound; real signals repeat a time point only at events (pairs).
- [A huge `B` (> n/2) means no reduction] → by design (unchanged
  threshold); `2·B` uses saturating arithmetic so huge values cannot
  overflow.
- [Min/max output is not a faithful line shape between extremes (zig-zag
  order inside a bucket is lost)] → accepted for this method; LTTB is out
  of scope.
- [Callers pin x-values from a different signal than the one downsampled]
  → nearest-sample matching still keeps a sample near each pin; documented
  that pins should come from the same signal's x-grid.
