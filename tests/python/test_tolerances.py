"""Tolerance resolution (default + per-axis rule) through the Python API.

The step-edge case below is shared with
``crates/simtest-funnel-core/src/options.rs`` (Rust),
``crates/simtest-funnel-cli/src/main.rs`` (CLI) and
``packages/sdk/tests/tolerances.test.ts`` (TypeScript): the test signal
is the reference step delayed by ``0.001`` in x, so it passes only when
an x tolerance is given (there is none by default).
"""

from __future__ import annotations

import numpy as np

from simtest.funnel import (
    Options,
    Range,
    Status,
    Tolerances,
    compare,
    default_options,
    summarize,
)

# The default: no tolerance in x, rtoly = 2e-3 in y.
DEFAULT = Tolerances(
    atolx=0.0, atoly=0.0, ltolx=0.0, ltoly=0.0, rtolx=0.0, rtoly=2e-3
)


def _step_edge() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    t = np.arange(101, dtype=np.float64) / 100.0
    y_ref = np.clip((t - 0.49) / 0.01, 0.0, 1.0)
    y_test = np.clip((t - 0.491) / 0.01, 0.0, 1.0)
    return t, y_ref, y_test


def _resolved(options: Options | None) -> tuple[int, Tolerances]:
    t, y_ref, y_test = _step_edge()
    r = compare(t, y_ref, t, y_test, options)
    return r.status, summarize(r, t, options).tolerances


def test_no_options_uses_default() -> None:
    status, tol = _resolved(None)
    assert tol == DEFAULT
    # No x tolerance by default: the delayed steep edge fails.
    assert status == Status.FAIL


def test_empty_options_and_tolerances_equal_no_options() -> None:
    assert _resolved(Options()) == _resolved(None)
    assert _resolved(Options(tolerances=Tolerances())) == _resolved(None)
    assert _resolved(Options(x_range=Range())) == _resolved(None)


def test_only_atoly_keeps_x_default() -> None:
    status, tol = _resolved(Options(tolerances=Tolerances(atoly=0.05)))
    assert tol == Tolerances(
        atolx=0.0, atoly=0.05, ltolx=0.0, ltoly=0.0, rtolx=0.0, rtoly=0.0
    )
    assert status == Status.FAIL


def test_explicit_x_tolerance_absorbs_time_shift() -> None:
    status, tol = _resolved(Options(tolerances=Tolerances(atolx=0.002, atoly=0.05)))
    assert tol == Tolerances(
        atolx=0.002, atoly=0.05, ltolx=0.0, ltoly=0.0, rtolx=0.0, rtoly=0.0
    )
    assert status == Status.PASS
    # Only an x coefficient: y keeps its default rtoly = 2e-3.
    status, tol = _resolved(Options(tolerances=Tolerances(rtolx=2e-3)))
    assert tol == Tolerances(
        atolx=0.0, atoly=0.0, ltolx=0.0, ltoly=0.0, rtolx=2e-3, rtoly=2e-3
    )
    assert status == Status.PASS


def test_explicit_zero_counts_as_given() -> None:
    status, tol = _resolved(Options(tolerances=Tolerances(atolx=0.0, atoly=0.05)))
    assert tol == Tolerances(
        atolx=0.0, atoly=0.05, ltolx=0.0, ltoly=0.0, rtolx=0.0, rtoly=0.0
    )
    assert status == Status.FAIL


def test_only_ltolx_keeps_y_default() -> None:
    _, tol = _resolved(Options(tolerances=Tolerances(ltolx=0.01)))
    assert tol == Tolerances(
        atolx=0.0, atoly=0.0, ltolx=0.01, ltoly=0.0, rtolx=0.0, rtoly=2e-3
    )


def test_one_coefficient_per_axis_zeroes_the_rest() -> None:
    _, tol = _resolved(Options(tolerances=Tolerances(atolx=0.1, atoly=0.1)))
    assert tol == Tolerances(
        atolx=0.1, atoly=0.1, ltolx=0.0, ltoly=0.0, rtolx=0.0, rtoly=0.0
    )


def test_fully_explicit_is_used_verbatim() -> None:
    explicit = Tolerances(
        atolx=0.1, atoly=0.2, ltolx=0.3, ltoly=0.4, rtolx=0.5, rtoly=0.6
    )
    _, tol = _resolved(Options(tolerances=explicit))
    assert tol == explicit


def test_default_options_round_trip() -> None:
    d = default_options()
    assert d.tolerances == DEFAULT
    t, y_ref, y_test = _step_edge()
    a = compare(t, y_ref, t, y_test, d)
    b = compare(t, y_ref, t, y_test)
    assert a.status == b.status
    for x, y in zip(a.lower + a.upper + a.errors, b.lower + b.upper + b.errors):
        assert np.array_equal(x, y)
