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

## API

- `compare(t_ref, y_ref, t_test, y_test, options=None) -> CompareResult`
- `compare_dataframes(reference, test, *, time_column="time", default_options=None, option_overrides=None) -> dict[str, CompareResult]`
- `default_options() -> Options`
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
