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
import { compare, Status } from "@simtest-js/funnel";

const tRef = Float64Array.from({ length: 101 }, (_, i) => i / 100);
const yRef = tRef.map((t) => Math.sin(2 * Math.PI * t));
const yTest = yRef.map((y) => y + 0.01);

const result = compare(tRef, yRef, tRef, yTest, {
  tolerances: { atoly: 0.05 },
});

if (result.status === Status.Pass) {
  console.log("inside funnel");
} else {
  console.log("status:", result.status, "signed errors:", result.errorsY);
}
```

`compare()` accepts `ArrayLike<number>` or `Float64Array` inputs and
returns a `CompareResult` whose `errorsY` array is **signed** — positive
above the upper bound, negative below the lower bound.

## Status codes

Mirror `simtest_funnel_core::Status`:

| Name                | Code |
|---------------------|-----:|
| `Pass`              |   0  |
| `Fail`              |  -1  |
| `MissingReference`  |   1  |
| `MissingTest`       |   2  |
| `NonMonotonic`      |  10  |
| `LengthMismatch`    |  11  |
| `EmptyRange`        |  12  |
| `BufferTooSmall`    |  13  |
| `InsufficientData`  |  14  |

## Reference documentation

A full `typedoc`-generated API reference is published alongside every
release. To build it locally:

```bash
make docs-js    # writes target/doc/js/index.html
```
