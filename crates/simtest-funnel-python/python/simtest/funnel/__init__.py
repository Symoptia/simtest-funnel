"""High-level Python API for the simtest-funnel trajectory comparison library.

Re-exports the PyO3 extension module `_simtest_funnel` through a
typed dataclass-based interface. See the project README for usage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Mapping, Sequence

import numpy as np

from simtest.funnel import _simtest_funnel as _ext  # type: ignore[import-untyped]


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
    atolx: float = 0.0
    atoly: float = 0.0
    ltolx: float = 0.0
    ltoly: float = 0.0
    rtolx: float = 0.0
    rtoly: float = 0.0


@dataclass(frozen=True)
class Range:
    lo: float = float("-inf")
    hi: float = float("+inf")


@dataclass(frozen=True)
class Options:
    tolerances: Tolerances = field(default_factory=Tolerances)
    x_range: Range = field(default_factory=Range)


@dataclass(frozen=True)
class CompareResult:
    status: int
    lower: tuple[np.ndarray, np.ndarray]
    upper: tuple[np.ndarray, np.ndarray]
    errors: tuple[np.ndarray, np.ndarray]


def default_options() -> Options:
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
) -> CompareResult:
    """Compare a test trajectory against a reference trajectory."""
    tref = _as_f64(t_reference)
    yref = _as_f64(y_reference)
    ttst = _as_f64(t_test)
    ytst = _as_f64(y_test)
    d = _ext.compare(tref, yref, ttst, ytst, _options_to_dict(options))
    return CompareResult(
        status=int(d["status"]),
        lower=(np.asarray(d["lower"][0]), np.asarray(d["lower"][1])),
        upper=(np.asarray(d["upper"][0]), np.asarray(d["upper"][1])),
        errors=(np.asarray(d["errors"][0]), np.asarray(d["errors"][1])),
    )


def status_message(code: int) -> str:
    """Return a human-readable description of a status code."""
    return str(_ext.status_message_py(int(code)))


def compare_dataframes(
    reference: Any,
    test: Any,
    *,
    time_column: str = "time",
    default_options: Options | None = None,
    option_overrides: Mapping[str, Options] | None = None,
) -> dict[str, CompareResult]:
    """Compare every common signal of two pandas DataFrames.

    The first column of each DataFrame MUST be the time column; its
    name is matched case-insensitively against ``time_column``.
    """
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
    t_ref = np.asarray(reference[ref_cols[0]].to_numpy(), dtype=np.float64)
    t_tst = np.asarray(test[tst_cols[0]].to_numpy(), dtype=np.float64)
    out: dict[str, CompareResult] = {}
    common = [c for c in ref_cols[1:] if c in tst_cols[1:]]
    for name in common:
        opts = overrides.get(name, default_options)
        y_ref = np.asarray(reference[name].to_numpy(), dtype=np.float64)
        y_tst = np.asarray(test[name].to_numpy(), dtype=np.float64)
        out[name] = compare(t_ref, y_ref, t_tst, y_tst, opts)
    return out


def version() -> str:
    return str(_ext.version())


__all__ = [
    "CompareResult",
    "Options",
    "Range",
    "Status",
    "Tolerances",
    "compare",
    "compare_dataframes",
    "default_options",
    "status_message",
    "version",
]
