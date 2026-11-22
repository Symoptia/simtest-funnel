"""The x-range window: the tube is built from the reference extended beyond
the window, so in-window test points are judged as in a full-range
comparison (the same cases as the Rust, TypeScript and MCP tests)."""

from __future__ import annotations

import math

import numpy as np

from simtest.funnel import (
    CompareResult,
    Options,
    Range,
    Status,
    Tolerances,
    compare,
    summarize,
)

HOUR = 3600.0
DAY = 86400.0
TOL = Tolerances(atolx=3 * HOUR, atoly=0.05)


def _daily_cycle() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hourly daily temperature cycle over 6 days; the test is 2 h late."""
    t = np.arange(145) * HOUR

    def temp(s: np.ndarray) -> np.ndarray:
        return np.asarray(10.0 + 5.0 * np.cos(2.0 * math.pi * (s - 14.0 * HOUR) / DAY))

    return t, temp(t), temp(t - 2 * HOUR)


def _run(lo: float = -math.inf, hi: float = math.inf, tol: Tolerances = TOL) -> CompareResult:
    t, y_ref, y_test = _daily_cycle()
    return compare(t, y_ref, t, y_test, Options(tolerances=tol, x_range=Range(lo, hi)))


def test_shift_within_atolx_passes_at_window_edges() -> None:
    t, y_ref, y_test = _daily_cycle()
    full = _run()
    # Only the first hours of the data fail: no earlier reference there.
    assert full.status == Status.FAIL
    assert np.all(full.errors[0][full.errors[1] != 0.0] < 3 * HOUR)
    opts = Options(tolerances=TOL, x_range=Range(2 * DAY, 4 * DAY))
    win = compare(t, y_ref, t, y_test, opts)
    assert win.status == Status.PASS
    s = summarize(win, t, opts)
    assert (s.points_compared, s.points_outside) == (49, 0)
    # The bounds reach beyond the window; deviations outside it are 0.
    assert win.lower[0][0] < 2 * DAY - 3 * HOUR
    assert win.upper[0][-1] > 4 * DAY + 3 * HOUR
    outside = (t < 2 * DAY) | (t > 4 * DAY)
    assert np.all(win.errors[1][outside] == 0.0)
    np.testing.assert_array_equal(win.errors[0], t)


def test_window_narrower_than_x_tolerance() -> None:
    t, _, _ = _daily_cycle()
    lo, hi = 2.5 * DAY, 2.5 * DAY + HOUR
    win = _run(lo, hi)
    assert win.status == Status.PASS
    inside = (t >= lo) & (t <= hi)
    np.testing.assert_array_equal(win.errors[1][inside], _run().errors[1][inside])
    tight = Tolerances(atolx=0.5 * HOUR, atoly=0.05)
    assert _run(lo, hi, tight).status == Status.FAIL


def test_data_start_and_end_unchanged() -> None:
    t, _, _ = _daily_cycle()
    full = _run()
    for lo, hi, status in (
        (0.0, DAY, Status.FAIL),
        (-1e6, DAY, Status.FAIL),
        (5 * DAY, t[-1], Status.PASS),
        (5 * DAY, 1e9, Status.PASS),
    ):
        win = _run(lo, hi)
        assert win.status == status, (lo, hi)
        inside = (t >= lo) & (t <= hi)
        np.testing.assert_array_equal(win.errors[1][inside], full.errors[1][inside])
    assert _run(0.0, DAY).lower[0][0] == full.lower[0][0]
    assert _run(5 * DAY, 1e9).upper[0][-1] == full.upper[0][-1]


def test_window_partly_or_wholly_outside_the_data() -> None:
    t, _, _ = _daily_cycle()
    assert _run(3 * HOUR, DAY).status == Status.PASS
    assert _run(t[-1] - DAY, t[-1] + DAY).status == Status.PASS
    assert _run(t[-1] + 1.0, t[-1] + DAY).status == Status.EMPTY_RANGE
    assert _run(t[-1] + 1.0, t[-1] + HOUR).status == Status.EMPTY_RANGE


def test_range_relative_tolerance_is_relative_to_the_window() -> None:
    t = np.arange(101.0)
    yt = t + 0.5
    tol = Tolerances(rtoly=0.01)
    assert compare(t, t, t, yt, Options(tolerances=tol)).status == Status.PASS
    windowed = Options(tolerances=tol, x_range=Range(0.0, 10.0))
    assert compare(t, t, t, yt, windowed).status == Status.FAIL


def test_in_window_verdicts_match_full_range() -> None:
    """Random noisy signals, shifted tests on another grid, tolerances
    without rtol, random windows: each judged point's deviation equals the
    full-range one (verdict and, in practice, value)."""
    rng = np.random.default_rng(20261122)
    windows = 0
    for _ in range(300):
        n = int(rng.integers(20, 200))
        t = np.cumsum(rng.uniform(0.2, 1.2, n))
        y = np.cumsum(rng.uniform(-0.5, 0.5, n))
        tt = np.cumsum(rng.uniform(0.2, 1.2, int(rng.integers(20, 200)))) + rng.uniform(-1, 1)
        yt = np.interp(tt - rng.uniform(-1, 1), t, y) + rng.uniform(-0.1, 0.1, tt.shape[0])
        tol = Tolerances(
            atolx=float(rng.uniform(0, 5)),
            atoly=float(rng.uniform(0, 0.5)),
            ltolx=float(rng.choice([0.0, rng.uniform(0, 0.05)])),
            ltoly=float(rng.choice([0.0, rng.uniform(0, 0.2)])),
        )
        span = t[-1] - t[0]
        lo = t[0] + rng.uniform(-0.1, 1.1) * span
        hi = lo + rng.uniform(0, 0.5) * span
        full = compare(t, y, tt, yt, Options(tolerances=tol))
        win = compare(t, y, tt, yt, Options(tolerances=tol, x_range=Range(lo, hi)))
        if win.status not in (Status.PASS, Status.FAIL, Status.MISSING_REFERENCE,
                              Status.MISSING_TEST):
            continue
        windows += 1
        judged = (tt >= max(lo, t[0])) & (tt <= min(hi, t[-1]))
        np.testing.assert_array_equal(win.errors[1][judged], full.errors[1][judged])
        assert (win.status == Status.FAIL) == bool(np.any(full.errors[1][judged] != 0.0))
    assert windows > 150
