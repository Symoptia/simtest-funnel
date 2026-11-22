# simtest-funnel-core

Core Rust library for trajectory comparison. The algorithm is a
port of [LBNL Funnel](https://github.com/lbl-srg/funnel); see the
workspace [`README.md`](../../README.md#differences-from-lbnl-funnel)
for the behavioural differences.

## Install

```toml
[dependencies]
simtest-funnel-core = "1"
```

## Usage

```rust
use simtest_funnel_core::{compare, Options, PartialTolerances, Status};

let t_ref = [0.0_f64, 1.0, 2.0];
let y_ref = [0.0_f64, 1.0, 2.0];
let t_tst = [0.0_f64, 1.0, 2.0];
let y_tst = [0.0_f64, 1.0, 2.0];

// Only a y tolerance given: y uses atoly = 0.1 (rtoly = ltoly = 0),
// x keeps its default: no tolerance in x.
let opts = Options {
    tolerances: PartialTolerances { atoly: Some(0.1), ..Default::default() }.resolve(),
    ..Default::default()
};
let r = compare(&t_ref, &y_ref, &t_tst, &y_tst, &opts);
assert_eq!(r.status, Status::Pass);
```

## Tolerances

At each reference sample the tube half-widths are
`max(atol, rtol * range, ltol * |value|)` per axis, where `range` is the
extent of the reference samples inside `x_range`. If that is effectively zero
(`< 1e-10`, e.g. only `rtoly` given on a constant reference) it falls
back to `rtol * max|value|` (when `rtol > 0`), then to `1e-10`; give
`atoly` for constant or near-constant signals.

`Options::default()` uses `Tolerances::DEFAULT`: `rtoly = 2e-3`, all
other coefficients zero — **no tolerance in x (time) unless you give
one**. Zero x tolerance means the x half-width is the `1e-10` floor: the
tube has no width along x, so each test point is checked only against
the y band around the reference at the same x, and a test curve shifted
in time fails wherever the shift moves it by more than the y tolerance
(steep edges, switching events). Give `atolx` (time units), `ltolx` or
`rtolx` to allow such shifts. There is no x default because a tolerance
relative to the x range grows with the length of the record, not with
how fast the signal changes (a year of data at `rtolx = 2e-3` would
allow 17.5 h of time shift).

Partially specified tolerances
(`PartialTolerances`, each coefficient `Option<f64>`) are resolved per
axis — the same rule the Python, TypeScript and CLI front ends use:

- An axis with **no** coefficient given (`atol*`, `ltol*`, `rtol*` all
  `None`) gets the default for that axis.
- An axis with **at least one** coefficient given uses the given values
  and zero for the rest of that axis.
- An explicit `Some(0.0)` counts as given.

A plain `Tolerances` value is fully explicit and used verbatim. It has
no `Default` impl; spell explicit all-zero as `Tolerances::ZERO`.

## The x-range window

`Options::x_range` (default unbounded) is the window `[lo, hi]` of x in
which test points are judged. The tube is built from the reference
**extended beyond the window**: by two x half-widths plus three samples
on each side to start with, and further until the corners of the
extended reference provably give the full-range tube over the window.
The corner algorithm adds no corners inside a collinear or constant run
of reference samples, so the extension reaches past the end of such a
run, however long. A test point near a window edge that is shifted in x
by less than the x tolerance is therefore judged exactly as in a
comparison over the full range. Where the window reaches the first or
last reference sample there is nothing to extend with, as in a
full-range comparison.

- Without range-relative tolerances (`rtolx = rtoly = 0`), every test
  point inside the window gets the same deviation, bit for bit, and so
  the same verdict as in the full-range comparison, for any `atolx`,
  `atoly`, `ltolx` and `ltoly`. The argument (in `src/window.rs`) covers
  the corner construction completely; for the loop removal it assumes
  that each loop is cut where the curve crosses itself, which the C
  reference's heuristic does except in degenerate geometry. Randomized
  tests with adversarial references (collinear runs, steps, repeated and
  clustered x, epoch-sized x) find no difference.
- The extension usually stays within a few half-widths of the window.
  It reaches the data end on a side through a collinear run that long,
  or where the reference changes direction more often than the x
  tolerance is wide (e.g. noise with a large `atolx`); the window then
  costs about as much as the full-range comparison.
- `rtolx` / `rtoly` (and the constant-reference fallback) are relative to
  the reference samples **inside the window**, so with them a windowed
  comparison differs from the full-range one by design.
- Coverage (`MissingReference` / `MissingTest`) and the minimum of two
  reference and two test samples are judged inside the window.
- `lower` / `upper` cover the window plus the extension; `errors` has one
  entry per test sample, with deviation `0` outside `x_range`.
- The extension costs a few samples per side (found by binary search), so
  a small window on a long record stays cheap. A local x tolerance
  `ltolx >= 0.5` has no bounded reach and uses the reference up to the
  data start / end.

## Cancellation

`compare` cannot be interrupted. To stop a long comparison, use
`compare_cancellable` with a `CancelToken` (a flag any thread can set via
`cancel()`, clones share it, plus an optional deadline), or
`compare_with_check` with your own check closure. Both return
`Err(Cancelled::Requested | Cancelled::DeadlineExceeded)` when stopped and
otherwise exactly what `compare` returns; invalid input still returns its
status. The signal is checked between phases, every 32 768 elements of the
linear passes and every few tens of thousands of steps inside the corner
clean-up; in a release build checks were at most about 11 ms apart, also
for 10 million samples, so a comparison stops within milliseconds. Only
input validation (about 16 ms for 10 million samples) runs before the
first check, since invalid input reports its status even when the signal
has fired. The checks cost nothing measurable. `Status` is unchanged.

```rust
use simtest_funnel_core::{compare_cancellable, CancelToken, Cancelled, Options};
use std::time::Duration;

let t: Vec<f64> = (0..1000).map(f64::from).collect();
let y: Vec<f64> = t.iter().map(|v| v.sin()).collect();
let token = CancelToken::new().with_timeout(Duration::from_secs(5));
let _remote = token.clone(); // e.g. hand to another thread: _remote.cancel()
match compare_cancellable(&t, &y, &t, &y, &Options::default(), &token) {
    Ok(r) => println!("status {:?}", r.status),
    Err(Cancelled::DeadlineExceeded) => println!("took longer than 5 s"),
    Err(Cancelled::Requested) => println!("cancelled"),
}
```

On `wasm32-unknown-unknown` do not set a deadline (`std::time::Instant`
panics there); the flag works everywhere.

## Downsampling for output

`downsample_min_max(x, y, buckets, pinned_x)` reduces a signal for plots
and reports. It is post-processing only and never used by `compare` or
`summarize`.

- The x-extent is split into `buckets` buckets of **equal x-width**; the
  lowest and highest sample of each bucket are kept (first occurrence on
  ties, NaN y never selected), plus the first and last sample.
- Each finite pin keeps the sample with the **nearest x** (ties go to the
  lower x) and every sample sharing that x; NaN pins are ignored. Pin the
  `worst_x` of every violation interval so a plot never hides a violation.
- At most `min(n, 2·buckets + 2 + M)` samples are returned (`M` = samples
  selected by pins); signals with `n <= 2·buckets` are returned unchanged.
- Returns `Downsampled { indices, x, y }` in input order, or a
  `DownsampleError` for a length mismatch, a non-finite or decreasing x,
  or zero buckets.

```rust
use simtest_funnel_core::{compare, downsample_min_max, summarize, Options};

let t: Vec<f64> = (0..1000).map(f64::from).collect();
let y_ref: Vec<f64> = t.iter().map(|v| v * 0.01).collect();
let mut y_tst = y_ref.clone();
y_tst[500] += 1.0; // a one-sample spike
let opts = Options::default();
let r = compare(&t, &y_ref, &t, &y_tst, &opts);
let s = summarize(&r, &t, &opts);
let pins: Vec<f64> = s.intervals.iter().map(|iv| iv.worst_x).collect();
let d = downsample_min_max(&t, &y_tst, 20, &pins).unwrap();
assert!(d.x.contains(&500.0));
```

## `Status` codes

| Variant             | Code | Meaning                                             |
|---------------------|-----:|-----------------------------------------------------|
| `Pass`              |   0  | All test points inside the funnel                   |
| `Fail`              |  -1  | At least one test point outside the funnel          |
| `MissingReference`  |   1  | Within `x_range`, test x-range extends past reference |
| `MissingTest`       |   2  | Within `x_range`, reference x-range extends past test |
| `NonMonotonic`      |  10  | x-array not non-decreasing                          |
| `LengthMismatch`    |  11  | x and y arrays differ in length                     |
| `EmptyRange`        |  12  | `x_range` does not intersect reference or test data |
| `BufferTooSmall`    |  13  | Caller-provided output buffer undersized            |
| `InsufficientData`  |  14  | Fewer than two points after `x_range` filter        |

Coverage (`MissingReference` / `MissingTest`) is judged on both
x-extents clipped to `x_range`; with the default unbounded range this
compares the full extents. A window inside the overlap of both
trajectories therefore yields `Pass` or `Fail`. See the rustdoc for
`simtest_funnel_core::Status` for full details.

## Documentation

Rendered rustdoc is published to Cloudflare Pages alongside every
release. Build locally with:

```bash
cargo doc --no-deps --open -p simtest-funnel-core
```

## Minimum Supported Rust Version

`1.85`. Declared in `[workspace.package].rust-version` and enforced
by a dedicated CI matrix row.
# simtest-funnel-core

Core Rust library for trajectory comparison. Algorithm based on LBNL Funnel.

## Minimum Supported Rust Version

`1.85`. Declared in `[workspace.package].rust-version` and enforced by
a dedicated CI matrix row.
