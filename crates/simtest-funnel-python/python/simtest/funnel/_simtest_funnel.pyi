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
    with all six tolerance values present as floats, matching
    ``simtest_funnel_core::Options::default_options()``
    (``rtolx = rtoly = 2e-3``, others ``0.0``).
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

    ``options`` is ``{"tolerances": {...}, "x_range": {...}}`` or ``None``.
    A tolerance key that is missing or ``None`` is "not given"; the given
    coefficients are resolved per axis in the Rust core (an axis with no
    coefficient given gets ``rtol = 2e-3``, an axis with at least one
    given uses zero for the rest; ``0.0`` counts as given). ``None``
    options or ``tolerances`` mean the defaults.

    Returns a dict with keys:

    - ``status``: int (see ``STATUS_*`` constants).
    - ``lower``: ``(NDArray[f64], NDArray[f64])`` — lower bound `(x, y)`.
    - ``upper``: ``(NDArray[f64], NDArray[f64])`` — upper bound `(x, y)`.
    - ``errors``: ``(NDArray[f64], NDArray[f64])`` — signed deviations
      on the test x-grid.
    """
    ...


def summarize(
    t_reference: NDArray[np.float64],
    status: int,
    lower_x: NDArray[np.float64],
    lower_y: NDArray[np.float64],
    upper_x: NDArray[np.float64],
    upper_y: NDArray[np.float64],
    errors_x: NDArray[np.float64],
    errors_y: NDArray[np.float64],
    options: dict[str, Any] | None = ...,
) -> dict[str, Any]:
    """Violation summary of an existing comparison.

    Takes the reference x-values, the comparison status and its bound /
    error arrays (contiguous ``float64`` 1-D), plus the options used for
    the comparison (resolved exactly as in :func:`compare`). Returns a
    dict with keys ``status``, ``tolerances`` (the six resolved values),
    ``x_range``, ``compared_range`` (dict or ``None``), ``intervals``
    (list of dicts with ``start_x``, ``end_x``, ``direction``,
    ``point_count``, ``worst_deviation``, ``worst_x``), ``worst`` (dict
    with ``x``, ``deviation``, ``tube_half_width_y``, or ``None``),
    ``points_compared``, ``points_outside``,
    ``fraction_of_points_outside`` and ``fraction_of_span_outside``
    (float or ``None``). Raises ``ValueError`` for unknown status codes.
    """
    ...
