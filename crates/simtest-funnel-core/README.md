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
// x keeps the default rtolx = 2e-3.
let opts = Options {
    tolerances: PartialTolerances { atoly: Some(0.1), ..Default::default() }.resolve(),
    ..Default::default()
};
let r = compare(&t_ref, &y_ref, &t_tst, &y_tst, &opts);
assert_eq!(r.status, Status::Pass);
```

## Tolerances

`Options::default()` uses `Tolerances::DEFAULT`: `rtolx = rtoly = 2e-3`,
all other coefficients zero. Partially specified tolerances
(`PartialTolerances`, each coefficient `Option<f64>`) are resolved per
axis — the same rule the Python, TypeScript and CLI front ends use:

- An axis with **no** coefficient given (`atol*`, `ltol*`, `rtol*` all
  `None`) gets the default for that axis.
- An axis with **at least one** coefficient given uses the given values
  and zero for the rest of that axis.
- An explicit `Some(0.0)` counts as given.

A plain `Tolerances` value is fully explicit and used verbatim. It has
no `Default` impl; spell explicit all-zero as `Tolerances::ZERO`.

## `Status` codes

| Variant             | Code | Meaning                                             |
|---------------------|-----:|-----------------------------------------------------|
| `Pass`              |   0  | All test points inside the funnel                   |
| `Fail`              |  -1  | At least one test point outside the funnel          |
| `MissingReference`  |   1  | Test x-range extends past reference                 |
| `MissingTest`       |   2  | Reference x-range extends past test                 |
| `NonMonotonic`      |  10  | x-array not non-decreasing                          |
| `LengthMismatch`    |  11  | x and y arrays differ in length                     |
| `EmptyRange`        |  12  | `x_range` does not intersect reference or test data |
| `BufferTooSmall`    |  13  | Caller-provided output buffer undersized            |
| `InsufficientData`  |  14  | Fewer than two points after `x_range` filter        |

See the rustdoc for `simtest_funnel_core::Status` for full details.

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
