"""Demo signal formulas for the WASM funnel landing-page demo.

Single source of truth for the reference and test trajectories that the
`examples/web` browser demo loads. Used both to (re)generate the committed
CSV fixtures and to verify them in `tests/python/test_demo_fixtures.py`.

Signals over ``t = linspace(0, 1, 1001)`` (comparison uses ``atolx = atoly =
0.1``):

* ``x``: ``sin(2 pi t)`` vs ``sin(2 pi t) + 0.05 sin(30 pi t)`` -> PASS
* ``y``: ``cos(2 pi t) sin(100 t)`` vs ``cos(2 pi t) sin(150 t)`` -> PASS
  (frequency-insensitive; fails when ``atolx = 0``)
* ``z``: ``sin(4 pi t)`` vs ``sin(5 pi t)`` -> FAIL
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

#: Number of samples in the demo signals.
N_SAMPLES = 1001

#: CSV column header shared by both fixtures.
COLUMNS = ("time", "x", "y", "z")


def time_grid() -> NDArray[np.float64]:
    """Return the shared time grid ``linspace(0, 1, N_SAMPLES)``."""
    return np.linspace(0.0, 1.0, N_SAMPLES)


def reference_signals(
    t: NDArray[np.float64],
) -> dict[str, NDArray[np.float64]]:
    """Return the reference ``x``, ``y``, ``z`` signals for time grid ``t``."""
    return {
        "x": np.sin(2 * np.pi * t),
        "y": np.cos(2 * np.pi * t) * np.sin(100 * t),
        "z": np.sin(4 * np.pi * t),
    }


def test_signals(
    t: NDArray[np.float64],
) -> dict[str, NDArray[np.float64]]:
    """Return the (noisy) test ``x``, ``y``, ``z`` signals for time grid ``t``."""
    return {
        "x": np.sin(2 * np.pi * t) + 0.05 * np.sin(30 * np.pi * t),
        "y": np.cos(2 * np.pi * t) * np.sin(150 * t),
        "z": np.sin(5 * np.pi * t),
    }


def _table(
    t: NDArray[np.float64], signals: dict[str, NDArray[np.float64]]
) -> NDArray[np.float64]:
    return np.column_stack([t, signals["x"], signals["y"], signals["z"]])


def reference_table() -> NDArray[np.float64]:
    """Return the reference fixture as a ``(N_SAMPLES, 4)`` array."""
    t = time_grid()
    return _table(t, reference_signals(t))


def test_table() -> NDArray[np.float64]:
    """Return the test fixture as a ``(N_SAMPLES, 4)`` array."""
    t = time_grid()
    return _table(t, test_signals(t))


def write_csv(path: str, table: NDArray[np.float64]) -> None:
    """Write ``table`` to ``path`` with header ``time,x,y,z``."""
    header = ",".join(COLUMNS)
    np.savetxt(path, table, delimiter=",", header=header, comments="", fmt="%.12g")
