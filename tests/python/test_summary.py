"""Tests for the violation summary exposed as ``simtest.funnel.summarize``."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from simtest.funnel import (
    Options,
    Range,
    Status,
    Tolerances,
    ViolationInterval,
    compare,
    default_options,
    summarize,
)

CORPUS = (
    Path(__file__).resolve().parents[2]
    / "crates"
    / "simtest-funnel-core"
    / "tests"
    / "corpus"
)


def _read_xy(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    return data[:, 0].astype(np.float64), data[:, 1].astype(np.float64)


def test_single_excursion_above() -> None:
    t = np.arange(5.0)
    y = np.ones(5)
    yt = np.array([1.0, 1.0, 1.5, 1.0, 1.0])
    opts = Options(tolerances=Tolerances(atoly=0.2))
    r = compare(t, y, t, yt, opts)
    s = summarize(r, t, opts)
    assert s.status == Status.FAIL
    # Echo is the six resolved values: y given, x keeps the default (zero).
    assert s.tolerances == Tolerances(
        atolx=0.0, atoly=0.2, ltolx=0.0, ltoly=0.0, rtolx=0.0, rtoly=0.0
    )
    assert s.x_range == Range()
    assert s.compared_range == Range(lo=0.0, hi=4.0)
    assert len(s.intervals) == 1
    iv = s.intervals[0]
    assert isinstance(iv, ViolationInterval)
    assert (iv.start_x, iv.end_x, iv.direction, iv.point_count) == (
        2.0,
        2.0,
        "above",
        1,
    )
    assert s.worst is not None
    assert s.worst.x == 2.0
    assert abs(s.worst.deviation - 0.3) < 1e-12
    assert abs(s.worst.tube_half_width_y - 0.2) < 1e-12
    assert (s.points_compared, s.points_outside) == (5, 1)
    assert s.fraction_of_points_outside == 0.2
    assert s.fraction_of_span_outside == 0.25


def test_pass_has_no_violations() -> None:
    t = np.arange(4.0)
    opts = Options(tolerances=Tolerances(atoly=0.5))
    r = compare(t, t, t, t, opts)
    s = summarize(r, t, opts)
    assert s.status == Status.PASS
    assert s.intervals == ()
    assert s.worst is None
    assert s.fraction_of_points_outside == 0.0
    assert s.fraction_of_span_outside == 0.0


def test_validation_status_summary() -> None:
    t = np.array([0.0, 2.0, 1.0])
    y = np.array([0.0, 1.0, 2.0])
    opts = Options(tolerances=Tolerances(atoly=0.5), x_range=Range(lo=0.0, hi=1.5))
    r = compare(t, y, np.array([0.0, 1.0, 2.0]), y, opts)
    s = summarize(r, t, opts)
    assert s.status == Status.NON_MONOTONIC
    assert s.tolerances == Tolerances(
        atolx=0.0, atoly=0.5, ltolx=0.0, ltoly=0.0, rtolx=0.0, rtoly=0.0
    )
    assert s.x_range == opts.x_range
    assert s.intervals == ()
    assert s.worst is None
    assert s.compared_range is None
    assert (s.points_compared, s.points_outside) == (0, 0)
    assert s.fraction_of_points_outside is None
    assert s.fraction_of_span_outside is None


def test_default_options_are_echoed() -> None:
    t = np.arange(4.0)
    r = compare(t, t, t, t)
    s = summarize(r, t)
    assert s.tolerances == default_options().tolerances
    assert s.tolerances == Tolerances(
        atolx=0.0, atoly=0.0, ltolx=0.0, ltoly=0.0, rtolx=0.0, rtoly=2e-3
    )
    # Options() and Options(tolerances=Tolerances()) mean the same.
    assert summarize(r, t, Options()).tolerances == s.tolerances


def test_fail1_matches_rust_pinned_values() -> None:
    # Same pinned values as crates/simtest-funnel-core/tests/summary_corpus.rs
    # and packages/sdk/tests/summary.test.ts.
    xr, yr = _read_xy(CORPUS / "fail1" / "trended.csv")
    xt, yt = _read_xy(CORPUS / "fail1" / "simulated.csv")
    opts = Options(tolerances=Tolerances(rtolx=2e-3, rtoly=2e-3))
    r = compare(xr, yr, xt, yt, opts)
    s = summarize(r, xr, opts)
    assert s.status == Status.FAIL
    assert s.compared_range == Range(lo=54000.0, hi=79200.0)
    assert len(s.intervals) == 35
    first = s.intervals[0]
    assert (first.start_x, first.end_x) == (62435.0, 62530.0)
    assert first.direction == "above"
    assert first.point_count == 20
    assert first.worst_deviation == 0.0023400000000000087
    assert first.worst_x == 62490.0
    assert s.worst is not None
    assert s.worst.x == 66925.0
    assert s.worst.deviation == 0.019127999999996537
    assert s.worst.tube_half_width_y == 0.003080000000001748
    assert (s.points_compared, s.points_outside) == (5041, 498)
    assert s.fraction_of_points_outside == 0.09878992263439794
    assert s.fraction_of_span_outside == 0.0988095238095238


def test_coverage_is_judged_within_x_range() -> None:
    """Test covering 0..1.1 against a 0..1 reference is MISSING_REFERENCE
    unbounded, but a window inside the overlap compares normally and the
    summary judges exactly the points in that window."""
    t = np.array([0.0, 0.5, 1.0])
    y = np.zeros(3)
    tt = np.array([0.0, 0.25, 0.5, 0.75, 1.0, 1.1])
    yt = np.zeros(6)
    tol = Tolerances(atolx=0.0, atoly=0.1)
    assert compare(t, y, tt, yt, Options(tolerances=tol)).status == Status.MISSING_REFERENCE
    opts = Options(tolerances=tol, x_range=Range(0.0, 1.0))
    r = compare(t, y, tt, yt, opts)
    assert r.status == Status.PASS
    s = summarize(r, t, opts)
    assert (s.points_compared, s.points_outside) == (5, 0)
    one_sided = Options(tolerances=tol, x_range=Range(hi=1.0))
    assert compare(t, y, tt, yt, one_sided).status == Status.PASS
