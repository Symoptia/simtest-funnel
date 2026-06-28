# simtest-funnel (Python)

Python bindings for the [simtest-funnel](https://github.com/Symoptia/simtest-funnel)
trajectory comparison library, built with PyO3 and maturin.

See the workspace
[`README.md`](../../README.md#differences-from-lbnl-funnel) for how
this library differs from LBNL Funnel.

## Install

```bash
pip install simtest-funnel
```

## Quick start

```python
import numpy as np
from simtest.funnel import Options, Tolerances, compare

t = np.linspace(0.0, 1.0, 101)
y_ref = np.sin(2 * np.pi * t)
y_test = y_ref + 0.01

result = compare(
    t, y_ref, t, y_test,
    Options(tolerances=Tolerances(atoly=0.05)),
)
print(result.status)  # 0 == Pass, -1 == Fail, 1/2 == MissingReference/Test
```

For DataFrame-based comparisons and the package-level API reference
see the package README in
[`python/simtest/funnel/README.md`](python/simtest/funnel/README.md).

## Typing

The wheel ships a `py.typed` marker and a hand-maintained
`_simtest_funnel.pyi` stub, so `mypy --strict` is supported out of
the box.

## Documentation

A `pdoc`-rendered site is published alongside every release. Build
it locally with:

```bash
make docs-python    # → target/doc/python/index.html
```
# simtest-funnel-python

Python bindings for the simtest-funnel trajectory comparison library, built with PyO3 and maturin.
