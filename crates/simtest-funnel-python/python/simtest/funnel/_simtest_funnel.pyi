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


class CancelToken:
    """Thread-safe cancellation token (see ``simtest.funnel.CancelToken``)."""

    def __init__(self) -> None: ...
    def cancel(self) -> None:
        """Request cancellation (thread-safe, idempotent)."""
        ...
    @property
    def cancelled(self) -> bool:
        """Whether ``cancel()`` has been called."""
        ...


class ComparisonCancelled(Exception):
    """A comparison was stopped by its ``CancelToken``."""


class ComparisonTimeout(ComparisonCancelled):
    """A comparison exceeded its time limit."""


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
    (``rtoly = 2e-3``, others ``0.0``: no tolerance in x).
    """
    ...


def compare(
    t_reference: NDArray[np.float64],
    y_reference: NDArray[np.float64],
    t_test: NDArray[np.float64],
    y_test: NDArray[np.float64],
    options: dict[str, Any] | None = ...,
    *,
    timeout: float | None = ...,
    cancel: CancelToken | None = ...,
) -> dict[str, Any]:
    """Core compare. Takes four contiguous ``float64`` 1-D arrays.

    Runs with the GIL released. ``timeout`` (seconds, finite, ``>= 0``)
    raises ``ComparisonTimeout`` when exceeded; a cancelled ``cancel``
    token raises ``ComparisonCancelled``; in the main thread a signal
    handler's exception (Ctrl-C: ``KeyboardInterrupt``) propagates. A
    negative or non-finite ``timeout`` raises ``ValueError``.

    ``options`` is ``{"tolerances": {...}, "x_range": {...}}`` or ``None``.
    A tolerance key that is missing or ``None`` is "not given"; the given
    coefficients are resolved per axis in the Rust core (an axis with no
    coefficient given gets its default, all zero for x and
    ``rtoly = 2e-3`` for y; an axis with at least one given uses zero for
    the rest; ``0.0`` counts as given). ``None``
    options or ``tolerances`` mean the defaults.

    Returns a dict with keys:

    - ``status``: int (see ``STATUS_*`` constants).
    - ``lower``: ``(NDArray[f64], NDArray[f64])`` — lower bound `(x, y)`.
    - ``upper``: ``(NDArray[f64], NDArray[f64])`` — upper bound `(x, y)`.
    - ``errors``: ``(NDArray[f64], NDArray[f64])`` — signed deviations
      on the test x-grid (``0`` outside ``x_range``).

    With an ``x_range`` only test points inside it are judged, against the
    tube built from the reference extended beyond it by the x tolerance;
    ``lower`` / ``upper`` then reach beyond the window.
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


def downsample_min_max(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    buckets: int,
    pinned_x: NDArray[np.float64],
) -> tuple[NDArray[np.uintp], NDArray[np.float64], NDArray[np.float64]]:
    """Min/max-per-bucket downsampling of a signal (computed by the core).

    Takes contiguous ``float64`` 1-D arrays ``x``, ``y`` and ``pinned_x``
    (empty for no pins) and the bucket count. Returns ``(indices, x, y)``
    of the kept samples in input order. Raises ``ValueError`` for a length
    mismatch, a non-finite or decreasing x, or ``buckets < 1``.
    """
    ...
