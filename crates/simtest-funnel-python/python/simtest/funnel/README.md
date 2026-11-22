# `simtest.funnel` — Python API

Python bindings for the [simtest-funnel](https://github.com/Symoptia/simtest-funnel)
trajectory comparison library. The underlying algorithm is implemented in
Rust and re-exported through a typed dataclass-based interface.

See the workspace
[`README.md`](https://github.com/Symoptia/simtest-funnel#differences-from-lbnl-funnel)
for how this library differs from LBNL Funnel (signed errors,
`MissingReference` / `MissingTest` statuses, default tolerances).

## Typing

The wheel ships a `py.typed` marker and a hand-maintained stub for
the native extension (`_simtest_funnel.pyi`), so `mypy --strict`
works without further configuration.

## Install

```
pip install simtest-funnel
```

## Quick start

```python
import numpy as np
from simtest.funnel import Options, Tolerances, compare

t_ref = np.linspace(0.0, 1.0, 101)
y_ref = np.sin(2 * np.pi * t_ref)
t_test = t_ref
y_test = y_ref + 0.01

result = compare(
    t_ref, y_ref, t_test, y_test,
    Options(tolerances=Tolerances(atoly=0.05)),
)
print(result.status)  # 0 == Pass, -1 == Fail
```

## Tolerances

`Tolerances` fields default to `None` ("not given"). The coefficients
you give are resolved **per axis** by the Rust core — the same rule as
the Rust, TypeScript and CLI front ends, so identical inputs give
identical verdicts everywhere:

- x axis: `atolx`, `ltolx`, `rtolx`; y axis: `atoly`, `ltoly`, `rtoly`.
- An axis with **no** coefficient given gets its default: the x axis
  all `0.0` (no time tolerance), the y axis `rtoly = 2e-3` (other
  coefficients `0.0`).
- An axis with **at least one** coefficient given uses the given values
  and `0.0` for the rest of that axis.
- An explicit `0.0` counts as given.

| You pass | Effective tolerances |
| --- | --- |
| `options=None`, `Options()`, `Tolerances()` | `rtoly = 2e-3`, rest `0` |
| `Tolerances(atoly=0.05)` | `atoly = 0.05`, rest `0` |
| `Tolerances(atolx=0.5)` | `atolx = 0.5`, `rtoly = 2e-3`, rest `0` |
| `Tolerances(atolx=0.5, atoly=0.05)` | `atolx = 0.5`, `atoly = 0.05`, rest `0` |

There is **no tolerance in x (time) unless you give one**. With zero x
tolerance the x half-width is the `1e-10` floor: each test point is
checked only against the y band around the reference at the same x, so a
test curve that is shifted or delayed in time fails at steep edges even
when the shift is tiny. Give `atolx` (time units) when such shifts are
acceptable; a range-relative `rtolx` grows with the length of the record.

`default_options()` and `ViolationSummary.tolerances` always report the
six resolved floats.

## Violation summary

`summarize` condenses an existing comparison into a small description of
how much the given tolerances were violated: violation intervals, the
worst deviation with the tube half-width at that x, and the share of
test points and of the compared x-span outside the tube.

```python
from simtest.funnel import summarize

opts = Options(tolerances=Tolerances(atoly=0.005))
result = compare(t_ref, y_ref, t_test, y_test, opts)
s = summarize(result, t_ref, opts)  # pass the same reference x and options
for iv in s.intervals:
    print(iv.start_x, iv.end_x, iv.direction, iv.worst_deviation)
print(s.worst, s.fraction_of_points_outside, s.fraction_of_span_outside)
```

Only test points inside the compared range (requested `x_range`
intersected with the reference x-extent) count. For validation statuses
(e.g. `NON_MONOTONIC`) the summary carries only the status and the echoed
settings; `worst`, `compared_range` and both fractions are `None`.

`MISSING_REFERENCE` / `MISSING_TEST` are judged within `x_range`: both
x-extents are clipped to it first, so `Range(lo, hi)` inside the overlap
of the two trajectories yields `PASS` or `FAIL`.

## Downsampling for plots

`downsample_min_max` reduces a long signal for plotting or reporting. It
is post-processing only: `compare` and `summarize` always use the full
signal.

```python
from simtest.funnel import downsample_min_max

s = summarize(result, t_ref, opts)
pins = [iv.worst_x for iv in s.intervals]  # keep every violation visible
d = downsample_min_max(t_test, y_test, buckets=500, pinned_x=pins)
plot(d.x, d.y)
errors_kept = result.errors[1][d.indices]  # same samples of a parallel array
```

The x-extent is split into `buckets` buckets of equal x-width; the
lowest and highest sample of each bucket are kept (first occurrence on
ties, NaN y never selected), plus the first and last sample. Each finite
pin keeps the sample with the nearest x (ties go to the lower x) and
every sample sharing that x; NaN pins are ignored. At most
`min(n, 2 * buckets + 2 + M)` samples are returned (`M` = samples
selected by pins); signals with `n <= 2 * buckets` are returned
unchanged. `ValueError` is raised for a length mismatch, a non-finite or
decreasing x, or `buckets < 1`.

## DataFrame API

```python
import pandas as pd
from simtest.funnel import compare_dataframes, Options, Tolerances

ref = pd.DataFrame({"time": t_ref, "a": y_ref, "b": y_ref})
tst = pd.DataFrame({"time": t_ref, "a": y_ref + 0.01, "b": y_ref + 1.0})

results = compare_dataframes(
    ref, tst,
    default_options=Options(tolerances=Tolerances(atoly=0.1)),
    option_overrides={"b": Options(tolerances=Tolerances(atoly=1e-6))},
)
# {"a": CompareResult(status=0, ...), "b": CompareResult(status=-1, ...)}
```

The first column of each DataFrame must be the time column; its name is
matched case-insensitively against `time_column` (default `"time"`).

## Time limits, cancellation and Ctrl-C

`compare` releases the interpreter lock while it runs, so other Python
threads keep running. A running comparison can be stopped; it then stops
within milliseconds (the core checks at least every ~11 ms, measured up
to 10 million samples in a release build). Before the limit or the token
can act, the binding copies the four input arrays (about 50 ms for 10
million samples) and the core validates the time arrays (about 16 ms for
10 million samples); a `timeout` counts from the start of the call, so
that time counts against it:

```python
import threading
from simtest.funnel import CancelToken, ComparisonCancelled, ComparisonTimeout, compare

try:
    result = compare(t_ref, y_ref, t_test, y_test, timeout=10.0)  # seconds
except ComparisonTimeout:
    ...  # took longer than 10 s

token = CancelToken()
threading.Timer(5.0, token.cancel).start()  # cancel from another thread
try:
    result = compare(t_ref, y_ref, t_test, y_test, cancel=token)
except ComparisonCancelled:  # also catches ComparisonTimeout
    ...
```

- `timeout`: seconds from the start of the call; exceeding it raises
  `ComparisonTimeout` (a subclass of `ComparisonCancelled`). Negative or
  non-finite values raise `ValueError`.
- `cancel`: a `CancelToken`; `token.cancel()` (thread-safe) makes every
  comparison using it raise `ComparisonCancelled`. A cancelled token stays
  cancelled.
- Ctrl-C (SIGINT) while a comparison runs in the main thread raises
  `KeyboardInterrupt` as usual.
- `compare_dataframes` takes the same `timeout` (for the whole call) and
  `cancel` arguments.

When none of these fires, results are identical to a call without them.

## API

- `compare(t_ref, y_ref, t_test, y_test, options=None, *, timeout=None, cancel=None) -> CompareResult`
- `summarize(result, t_reference, options=None) -> ViolationSummary` (with `ViolationInterval`, `WorstDeviation`)
- `downsample_min_max(x, y, buckets, pinned_x=None) -> Downsampled` (`indices`, `x`, `y` arrays)
- `compare_dataframes(reference, test, *, time_column="time", default_options=None, option_overrides=None, timeout=None, cancel=None) -> dict[str, CompareResult]`
- `CancelToken` (`cancel()`, `cancelled`), exceptions `ComparisonCancelled` and its subclass `ComparisonTimeout`
- `default_options() -> Options` (all six tolerances explicit)
- `status_message(code: int) -> str`
- `Status` — `IntEnum` with `PASS=0`, `FAIL=-1`, `MISSING_REFERENCE=1`, `MISSING_TEST=2`, and validation codes `10..14`.

See [`examples/compare_dataframes.py`](examples/compare_dataframes.py) for
a runnable example.

## Reference documentation

A full `pdoc`-generated API reference is published alongside every
release. To build it locally:

```bash
make docs-python    # writes target/doc/python/index.html
```
