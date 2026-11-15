# @simtest-js/funnel

TypeScript / JavaScript SDK for the
[simtest-funnel](https://github.com/Symoptia/simtest-funnel) trajectory
comparison library. Thin wrapper around the Rust core compiled to
WebAssembly via `wasm-bindgen`.

See the workspace
[`README.md`](https://github.com/Symoptia/simtest-funnel#differences-from-lbnl-funnel)
for how this library differs from LBNL Funnel (signed errors,
`MissingReference` / `MissingTest` statuses, default tolerances).

## Install

```bash
pnpm add @simtest-js/funnel
# or: npm install @simtest-js/funnel
```

## Quick start

```ts
import { compare, Status } from '@simtest-js/funnel';

const tRef = Float64Array.from({ length: 101 }, (_, i) => i / 100);
const yRef = tRef.map((t) => Math.sin(2 * Math.PI * t));
const yTest = yRef.map((y) => y + 0.01);

const result = compare(tRef, yRef, tRef, yTest, {
  tolerances: { atoly: 0.05 },
});

if (result.status === Status.Pass) {
  console.log('inside funnel');
} else {
  console.log('status:', result.status, 'signed errors:', result.errorsY);
}
```

`compare()` accepts `ArrayLike<number>` or `Float64Array` inputs and
returns a `CompareResult` whose `errorsY` array is **signed** — positive
above the upper bound, negative below the lower bound.

## Tolerances

A tolerance field that is omitted, `undefined` or `null` is "not
given". The given coefficients are resolved **per axis** by the Rust
core — the same rule as the Rust, Python and CLI front ends, so
identical inputs give identical verdicts everywhere:

- x axis: `atolx`, `ltolx`, `rtolx`; y axis: `atoly`, `ltoly`, `rtoly`.
- An axis with **no** coefficient given gets the default `rtol = 2e-3`
  (other coefficients `0`).
- An axis with **at least one** coefficient given uses the given values
  and `0` for the rest of that axis.
- An explicit `0` counts as given.

| You pass                                    | Effective tolerances                     |
| ------------------------------------------- | ---------------------------------------- |
| no `options`, `{}`, `{ tolerances: {} }`    | `rtolx = rtoly = 2e-3`, rest `0`         |
| `{ tolerances: { atoly: 0.05 } }`           | `atoly = 0.05`, `rtolx = 2e-3`, rest `0` |
| `{ tolerances: { atolx: 0, atoly: 0.05 } }` | `atoly = 0.05`, rest `0`                 |

`xRange` restricts the comparison to an x-window; each bound is optional
(omitted, `undefined` or `null` = unbounded), so `{ xRange: { lo: 0.5 } }`
compares `x >= 0.5`. Results report ranges as `ResolvedXRange` with both
bounds present (`-Infinity` / `Infinity` when unbounded).

`defaultOptions()` returns the six default values explicitly (passing
them is identical to omitting `options`), and `summarize()` echoes the
six resolved values (`ResolvedTolerances`).

## Violation summary

`summarize()` condenses an existing comparison into how much the given
tolerances were violated: violation intervals, the worst deviation with
the tube half-width at that x, and the share of test points and of the
compared x-span outside the tube. It is computed by the Rust core, so
the numbers match the Rust and Python APIs exactly.

```ts
import { compare, summarize } from '@simtest-js/funnel';

const options = { tolerances: { atoly: 0.005 } };
const result = compare(tRef, yRef, tRef, yTest, options);
const s = summarize(result, tRef, options); // same reference x and options
for (const iv of s.intervals) {
  console.log(iv.startX, iv.endX, iv.direction, iv.worstDeviation);
}
console.log(s.worst, s.fractionOfPointsOutside, s.fractionOfSpanOutside);
```

Only test points inside the compared range (`xRange` intersected with
the reference x-extent) count. For validation statuses (e.g.
`NonMonotonic`) `worst`, `comparedRange` and both fractions are `null`.

## Downsampling for plots

`downsampleMinMax(x, y, buckets, pinnedX?)` reduces a long signal for
plotting or reporting. It is post-processing only: `compare()` and
`summarize()` always use the full signal. `createFunnelPlot()` does not
downsample; pass downsampled traces yourself if needed.

```ts
import { downsampleMinMax } from '@simtest-js/funnel';

const s = summarize(result, tRef, options);
const pins = s.intervals.map((iv) => iv.worstX); // keep every violation visible
const d = downsampleMinMax(tTest, yTest, 500, pins);
// d.x, d.y: Float64Array; d.indices: Uint32Array into the input
const errorsKept = Array.from(d.indices, (i) => result.errorsY[i]);
```

The x-extent is split into `buckets` buckets of equal x-width; the
lowest and highest sample of each bucket are kept (first occurrence on
ties, `NaN` y never selected), plus the first and last sample. Each
finite pin keeps the sample with the nearest x (ties go to the lower x)
and every sample sharing that x; `NaN` pins are ignored. At most
`min(n, 2 * buckets + 2 + M)` samples are returned (`M` = samples
selected by pins); signals with `n <= 2 * buckets` are returned
unchanged. An `Error` is thrown for a length mismatch, a non-finite or
decreasing x, a non-integer `buckets` or `buckets < 1`. Results are
identical to the Rust and Python APIs.

## Status codes

Mirror `simtest_funnel_core::Status`:

| Name               | Code |
| ------------------ | ---: |
| `Pass`             |    0 |
| `Fail`             |   -1 |
| `MissingReference` |    1 |
| `MissingTest`      |    2 |
| `NonMonotonic`     |   10 |
| `LengthMismatch`   |   11 |
| `EmptyRange`       |   12 |
| `BufferTooSmall`   |   13 |
| `InsufficientData` |   14 |

`MissingReference` / `MissingTest` are judged within `xRange`: both
x-extents are clipped to it first, so a window inside the overlap of the
two trajectories yields `Pass` or `Fail`.

## Reference documentation

A full `typedoc`-generated API reference is published alongside every
release. To build it locally:

```bash
make docs-js    # writes target/doc/js/index.html
```
