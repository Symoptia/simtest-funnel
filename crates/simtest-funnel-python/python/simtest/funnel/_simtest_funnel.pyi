"""Type stubs for the `simtest.funnel._simtest_funnel` PyO3 module.

Mirrors the public surface declared in
`crates/simtest-funnel-python/src/lib.rs`. The high-level
`simtest.funnel` Python package re-exports these through typed
dataclasses; downstream code should prefer the package-level API.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

# Integer status constants (mirrors `Status` in the Rust core).
STATUS_PASS: int
STATUS_FAIL: int
STATUS_MISSING_REFERENCE: int
STATUS_MISSING_TEST: int
STATUS_NON_MONOTONIC: int
STATUS_LENGTH_MISMATCH: int
STATUS_EMPTY_RANGE: int
STATUS_BUFFER_TOO_SMALL: int
STATUS_INSUFFICIENT_DATA: int


def version() -> str:
    """Return the crate version string."""
    ...


def status_message_py(code: int) -> str:
    """Return the human-readable message for a status code.

    Raises ``ValueError`` for unknown codes.
    """
    ...


def default_options() -> dict[str, Any]:
    """Return the default options as a nested dict.

    The returned shape is ``{"tolerances": {...}, "x_range": {...}}``
    with float values matching
    ``simtest_funnel_core::Options::default_options()``.
    """
    ...


def compare(
    t_reference: NDArray[np.float64],
    y_reference: NDArray[np.float64],
    t_test: NDArray[np.float64],
    y_test: NDArray[np.float64],
    options: dict[str, Any] | None = ...,
) -> dict[str, Any]:
    """Core compare. Takes four contiguous ``float64`` 1-D arrays.

    Returns a dict with keys:

    - ``status``: int (see ``STATUS_*`` constants).
    - ``lower``: ``(NDArray[f64], NDArray[f64])`` — lower bound `(x, y)`.
    - ``upper``: ``(NDArray[f64], NDArray[f64])`` — upper bound `(x, y)`.
    - ``errors``: ``(NDArray[f64], NDArray[f64])`` — signed deviations
      on the test x-grid.
    """
    ...
