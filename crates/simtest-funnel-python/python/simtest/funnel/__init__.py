"""High-level Python API for the simtest-funnel trajectory comparison library.

Re-exports the PyO3 extension module `_simtest_funnel` through a
typed dataclass-based interface. See the project README for usage.
"""

from __future__ import annotations

import math
import operator
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Literal, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from simtest.funnel import _simtest_funnel as _ext

CancelToken = _ext.CancelToken
"""Thread-safe cancellation token for :func:`compare` / :func:`compare_dataframes`.

``CancelToken()`` creates an uncancelled token; ``token.cancel()`` (from any
thread) stops every comparison using it at its next checkpoint (within
milliseconds), which then
raises :class:`ComparisonCancelled`; ``token.cancelled`` tells whether
``cancel()`` was called. A cancelled token stays cancelled."""

ComparisonCancelled = _ext.ComparisonCancelled
"""Raised when a comparison is stopped by its :class:`CancelToken` (base
class of :class:`ComparisonTimeout`)."""

ComparisonTimeout = _ext.ComparisonTimeout
"""Raised when a comparison exceeds its ``timeout`` (subclass of
:class:`ComparisonCancelled`)."""


class Status(IntEnum):
    """Mirrors the Rust ``Status`` enum."""

    PASS = 0
    FAIL = -1
    MISSING_REFERENCE = 1
    MISSING_TEST = 2
    NON_MONOTONIC = 10
    LENGTH_MISMATCH = 11
    EMPTY_RANGE = 12
    BUFFER_TOO_SMALL = 13
    INSUFFICIENT_DATA = 14


@dataclass(frozen=True)
class Tolerances:
    """Tolerance coefficients; ``None`` means "not given".

    The x axis is ``atolx``/``ltolx``/``rtolx`` and the y axis is
    ``atoly``/``ltoly``/``rtoly``. Coefficients are resolved per axis by
    the Rust core, identically in every simtest-funnel API:

    - an axis with no coefficient given gets the default
      ``rtol = 2e-3`` (other coefficients ``0.0``);
    - an axis with at least one coefficient given uses the given values
      and ``0.0`` for its other coefficients;
    - an explicit ``0.0`` counts as given.

    So ``Tolerances()`` is the default (``rtolx = rtoly = 2e-3``) and
    ``Tolerances(atoly=0.05)`` means ``atoly = 0.05`` with ``rtoly = 0``
    and ``rtolx = 2e-3``; use ``Tolerances(atolx=0.0, atoly=0.05)`` for
    zero x tolerance. Values returned by the library
    (:func:`default_options`, :attr:`ViolationSummary.tolerances`) are
    always the six resolved floats.
    """

    atolx: float | None = None
    atoly: float | None = None
    ltolx: float | None = None
    ltoly: float | None = None
    rtolx: float | None = None
    rtoly: float | None = None


@dataclass(frozen=True)
class Range:
    lo: float = float("-inf")
    hi: float = float("+inf")


@dataclass(frozen=True)
class Options:
    """Compare options. ``Options()`` is equivalent to passing no options."""

    tolerances: Tolerances = field(default_factory=Tolerances)
    x_range: Range = field(default_factory=Range)


@dataclass(frozen=True)
class CompareResult:
    status: int
    lower: tuple[np.ndarray, np.ndarray]
    upper: tuple[np.ndarray, np.ndarray]
    errors: tuple[np.ndarray, np.ndarray]


def default_options() -> Options:
    """Return the default options with all six tolerances explicit
    (``rtolx = rtoly = 2e-3``, others ``0.0``)."""
    d = _ext.default_options()
    t = d["tolerances"]
    r = d["x_range"]
    return Options(
        tolerances=Tolerances(
            atolx=float(t["atolx"]),
            atoly=float(t["atoly"]),
            ltolx=float(t["ltolx"]),
            ltoly=float(t["ltoly"]),
            rtolx=float(t["rtolx"]),
            rtoly=float(t["rtoly"]),
        ),
        x_range=Range(lo=float(r["lo"]), hi=float(r["hi"])),
    )


def _options_to_dict(opts: Options | None) -> dict[str, Any] | None:
    if opts is None:
        return None
    t = opts.tolerances
    r = opts.x_range
    return {
        "tolerances": {
            "atolx": t.atolx,
            "atoly": t.atoly,
            "ltolx": t.ltolx,
            "ltoly": t.ltoly,
            "rtolx": t.rtolx,
            "rtoly": t.rtoly,
        },
        "x_range": {"lo": r.lo, "hi": r.hi},
    }


def _as_f64(a: Sequence[float] | np.ndarray) -> np.ndarray:
    arr = np.ascontiguousarray(a, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("expected 1-D array")
    return arr


def compare(
    t_reference: Sequence[float] | np.ndarray,
    y_reference: Sequence[float] | np.ndarray,
    t_test: Sequence[float] | np.ndarray,
    y_test: Sequence[float] | np.ndarray,
    options: Options | None = None,
    *,
    timeout: float | None = None,
    cancel: CancelToken | None = None,
) -> CompareResult:
    """Compare a test trajectory against a reference trajectory.

    ``options=None`` (or ``Options()``) uses the default tolerances;
    partially specified :class:`Tolerances` are resolved per axis (see
    :class:`Tolerances`).

    The interpreter lock is released while the comparison runs, so other
    Python threads keep running. The comparison can be stopped:

    - ``timeout``: seconds from the start of the call; when exceeded,
      :class:`ComparisonTimeout` is raised (``ValueError`` for a negative or
      non-finite value);
    - ``cancel``: a :class:`CancelToken`; ``cancel.cancel()`` from another
      thread makes this call raise :class:`ComparisonCancelled`;
    - Ctrl-C (SIGINT) while running in the main thread raises
      ``KeyboardInterrupt`` (or whatever the SIGINT handler raises).

    Each of these stops the comparison within milliseconds: the core
    checks at least every ~11 ms (measured up to 10 million samples in a
    release build). Not covered are the copy of the four input arrays
    made before the comparison starts (about 50 ms for 10 million
    samples) and the core's validation of the time arrays (about 16 ms);
    ``timeout`` counts from the start of the call, so they count against
    it. When none fires, the result is identical to a call without them.
    """
    tref = _as_f64(t_reference)
    yref = _as_f64(y_reference)
    ttst = _as_f64(t_test)
    ytst = _as_f64(y_test)
    d = _ext.compare(
        tref, yref, ttst, ytst, _options_to_dict(options), timeout=timeout, cancel=cancel
    )
    return CompareResult(
        status=int(d["status"]),
        lower=(np.asarray(d["lower"][0]), np.asarray(d["lower"][1])),
        upper=(np.asarray(d["upper"][0]), np.asarray(d["upper"][1])),
        errors=(np.asarray(d["errors"][0]), np.asarray(d["errors"][1])),
    )


def status_message(code: int) -> str:
    """Return a human-readable description of a status code."""
    return str(_ext.status_message_py(int(code)))


def _ensure_numeric(frame: Any, frame_name: str, column: str) -> None:
    """Raise ``ValueError`` if ``frame[column]`` is not a numeric dtype.

    `compare_dataframes` feeds every column through
    ``np.asarray(..., dtype=np.float64)``; object / string / categorical
    columns therefore fail with an opaque numpy coercion error. We
    surface a clear message instead.
    """
    import pandas as pd  # local import to avoid a hard dep at module load

    if not pd.api.types.is_numeric_dtype(frame[column]):
        dtype = frame[column].dtype
        raise ValueError(
            f"column {column!r} in {frame_name} must be numeric, got dtype={dtype}"
        )


def compare_dataframes(
    reference: Any,
    test: Any,
    *,
    time_column: str = "time",
    default_options: Options | None = None,
    option_overrides: Mapping[str, Options] | None = None,
    timeout: float | None = None,
    cancel: CancelToken | None = None,
) -> dict[str, CompareResult]:
    """Compare every common signal of two pandas DataFrames.

    The first column of each DataFrame MUST be the time column; its
    name is matched case-insensitively against ``time_column``.

    ``timeout`` (seconds) limits the whole call, all columns together, and
    ``cancel`` is passed to every :func:`compare`; when either fires,
    :class:`ComparisonTimeout` / :class:`ComparisonCancelled` is raised and
    no results are returned.
    """
    if timeout is not None and not (math.isfinite(timeout) and timeout >= 0):
        raise ValueError(f"timeout must be a finite number of seconds >= 0, got {timeout}")
    deadline = None if timeout is None else time.monotonic() + timeout
    overrides = dict(option_overrides or {})
    ref_cols = list(reference.columns)
    tst_cols = list(test.columns)
    if not ref_cols or not tst_cols:
        raise ValueError("both DataFrames must have at least a time column")
    if ref_cols[0].lower() != time_column.lower():
        raise ValueError(
            f"first column of reference must be '{time_column}', got {ref_cols[0]!r}"
        )
    if tst_cols[0].lower() != time_column.lower():
        raise ValueError(
            f"first column of test must be '{time_column}', got {tst_cols[0]!r}"
        )
    _ensure_numeric(reference, "reference", ref_cols[0])
    _ensure_numeric(test, "test", tst_cols[0])
    t_ref = np.asarray(reference[ref_cols[0]].to_numpy(), dtype=np.float64)
    t_tst = np.asarray(test[tst_cols[0]].to_numpy(), dtype=np.float64)
    out: dict[str, CompareResult] = {}
    common = [c for c in ref_cols[1:] if c in tst_cols[1:]]
    for name in common:
        _ensure_numeric(reference, "reference", name)
        _ensure_numeric(test, "test", name)
        opts = overrides.get(name, default_options)
        y_ref = np.asarray(reference[name].to_numpy(), dtype=np.float64)
        y_tst = np.asarray(test[name].to_numpy(), dtype=np.float64)
        remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
        try:
            out[name] = compare(
                t_ref, y_ref, t_tst, y_tst, opts, timeout=remaining, cancel=cancel
            )
        except ComparisonTimeout:
            # compare() names the time it was given (what was left of the
            # call's limit); report the caller's limit instead.
            raise ComparisonTimeout(
                f"comparison of column {name!r} exceeded the time limit of {timeout} s "
                "of compare_dataframes"
            ) from None
    return out


@dataclass(frozen=True)
class ViolationInterval:
    """A maximal run of consecutive judged test points outside the tube on
    the same side. ``start_x`` / ``end_x`` are the x of the first / last
    test point of the run (equal for a single-point violation)."""

    start_x: float
    end_x: float
    direction: Literal["above", "below"]
    point_count: int
    worst_deviation: float
    worst_x: float


@dataclass(frozen=True)
class WorstDeviation:
    """Overall worst signed deviation, its x, and the tube half-width in y
    at that x (half the distance between upper and lower bound)."""

    x: float
    deviation: float
    tube_half_width_y: float


@dataclass(frozen=True)
class ViolationSummary:
    """How much a comparison violated the tolerances it was run with.

    Only *judged* test points (x inside the requested ``x_range``
    intersected with the reference x-extent) contribute. ``compared_range``
    spans the first to the last judged test point. For validation statuses,
    or when no test point is judged, ``compared_range``, ``worst`` and both
    fractions are ``None`` and ``intervals`` is empty.
    """

    status: int
    tolerances: Tolerances
    """The six resolved tolerance values used (never ``None``)."""
    x_range: Range
    compared_range: Range | None
    intervals: tuple[ViolationInterval, ...]
    worst: WorstDeviation | None
    points_compared: int
    points_outside: int
    fraction_of_points_outside: float | None
    fraction_of_span_outside: float | None


def _range_from_dict(d: Mapping[str, Any]) -> Range:
    return Range(lo=float(d["lo"]), hi=float(d["hi"]))


def _opt_float(v: Any) -> float | None:
    return None if v is None else float(v)


def _direction(v: Any) -> Literal["above", "below"]:
    if v == "above":
        return "above"
    if v == "below":
        return "below"
    raise ValueError(f"unexpected direction {v!r}")


def summarize(
    result: CompareResult,
    t_reference: Sequence[float] | np.ndarray,
    options: Options | None = None,
) -> ViolationSummary:
    """Summarize how much ``result`` violated its tolerances.

    ``t_reference`` and ``options`` must be the reference x-values and the
    options that were passed to :func:`compare` to produce ``result``
    (``None`` means the same defaults :func:`compare` uses). The summary is
    computed by the Rust core, so its numbers are identical to the Rust and
    TypeScript APIs.
    """
    d = _ext.summarize(
        _as_f64(t_reference),
        int(result.status),
        _as_f64(result.lower[0]),
        _as_f64(result.lower[1]),
        _as_f64(result.upper[0]),
        _as_f64(result.upper[1]),
        _as_f64(result.errors[0]),
        _as_f64(result.errors[1]),
        _options_to_dict(options),
    )
    t = d["tolerances"]
    cr = d["compared_range"]
    w = d["worst"]
    return ViolationSummary(
        status=int(d["status"]),
        tolerances=Tolerances(
            atolx=float(t["atolx"]),
            atoly=float(t["atoly"]),
            ltolx=float(t["ltolx"]),
            ltoly=float(t["ltoly"]),
            rtolx=float(t["rtolx"]),
            rtoly=float(t["rtoly"]),
        ),
        x_range=_range_from_dict(d["x_range"]),
        compared_range=None if cr is None else _range_from_dict(cr),
        intervals=tuple(
            ViolationInterval(
                start_x=float(iv["start_x"]),
                end_x=float(iv["end_x"]),
                direction=_direction(iv["direction"]),
                point_count=int(iv["point_count"]),
                worst_deviation=float(iv["worst_deviation"]),
                worst_x=float(iv["worst_x"]),
            )
            for iv in d["intervals"]
        ),
        worst=None
        if w is None
        else WorstDeviation(
            x=float(w["x"]),
            deviation=float(w["deviation"]),
            tube_half_width_y=float(w["tube_half_width_y"]),
        ),
        points_compared=int(d["points_compared"]),
        points_outside=int(d["points_outside"]),
        fraction_of_points_outside=_opt_float(d["fraction_of_points_outside"]),
        fraction_of_span_outside=_opt_float(d["fraction_of_span_outside"]),
    )


_I64_MAX = 2**63 - 1


@dataclass(frozen=True)
class Downsampled:
    """Samples kept by :func:`downsample_min_max`, in input order.

    ``x[k] == input_x[indices[k]]`` and ``y[k] == input_y[indices[k]]``;
    use ``indices`` to select the same samples from further arrays on the
    same x-grid (e.g. ``result.errors[1]`` of a comparison).
    """

    indices: NDArray[np.intp]
    x: NDArray[np.float64]
    y: NDArray[np.float64]


def downsample_min_max(
    x: Sequence[float] | np.ndarray,
    y: Sequence[float] | np.ndarray,
    buckets: int,
    pinned_x: Sequence[float] | np.ndarray | None = None,
) -> Downsampled:
    """Reduce a signal to the extremes of ``buckets`` equal-width x-buckets.

    For output only (plots, reports); never feed the result back into
    :func:`compare`. The x-extent is split into ``buckets`` buckets of
    equal width; the lowest and highest sample of each bucket are kept
    (first occurrence on ties, NaN y never selected), plus the first and
    last sample. Each finite value of ``pinned_x`` keeps the sample with
    the nearest x (ties go to the lower x) and every sample sharing that
    x; NaN pins are ignored. Pin the ``worst_x`` of every interval of
    :func:`summarize` so a plot never hides a violation.

    At most ``min(n, 2 * buckets + 2 + M)`` samples are returned, ``M``
    being the samples selected by pins; if ``n <= 2 * buckets`` every
    sample is returned. Computed by the Rust core, so results are
    identical to the Rust and TypeScript APIs.

    Raises ``ValueError`` for a length mismatch, a non-finite or
    decreasing x, or ``buckets < 1``.
    """
    pins = np.empty(0, dtype=np.float64) if pinned_x is None else _as_f64(pinned_x)
    # Clamp to the native i64 range: negatives get the "at least 1 bucket"
    # error, huge counts mean "no reduction" instead of an OverflowError.
    n_buckets = max(-1, min(operator.index(buckets), _I64_MAX))
    idx, xs, ys = _ext.downsample_min_max(_as_f64(x), _as_f64(y), n_buckets, pins)
    return Downsampled(
        indices=np.asarray(idx, dtype=np.intp),
        x=np.asarray(xs, dtype=np.float64),
        y=np.asarray(ys, dtype=np.float64),
    )


def version() -> str:
    return str(_ext.version())


__all__ = [
    "CancelToken",
    "CompareResult",
    "ComparisonCancelled",
    "ComparisonTimeout",
    "Downsampled",
    "Options",
    "Range",
    "Status",
    "Tolerances",
    "ViolationInterval",
    "ViolationSummary",
    "WorstDeviation",
    "compare",
    "compare_dataframes",
    "default_options",
    "downsample_min_max",
    "status_message",
    "summarize",
    "version",
]
