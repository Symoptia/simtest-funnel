"""Tests for ``simtest.funnel.downsample_min_max``."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from simtest.funnel import (
    Downsampled,
    Options,
    Status,
    Tolerances,
    compare,
    downsample_min_max,
    summarize,
)

CORPUS = (
    Path(__file__).resolve().parents[2]
    / "crates"
    / "simtest-funnel-core"
    / "tests"
    / "corpus"
)

X = np.arange(10.0)
Y = np.array([0.0, 5.0, 1.0, 2.0, 9.0, 3.0, 4.0, 8.0, 6.0, 7.0])


def _read_xy(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.loadtxt(path, delimiter=",", skiprows=1)
    return data[:, 0].astype(np.float64), data[:, 1].astype(np.float64)


def test_two_buckets_keep_extremes() -> None:
    d = downsample_min_max(X, Y, 2)
    assert isinstance(d, Downsampled)
    assert d.indices.tolist() == [0, 4, 5, 7, 9]
    assert d.indices.dtype == np.intp
    np.testing.assert_array_equal(d.x, X[d.indices])
    np.testing.assert_array_equal(d.y, Y[d.indices])


def test_pins() -> None:
    assert downsample_min_max(X, Y, 2, [2.2]).indices.tolist() == [0, 2, 4, 5, 7, 9]
    assert downsample_min_max(X, Y, 2, [2.5]).indices.tolist() == [0, 2, 4, 5, 7, 9]
    no_effect = downsample_min_max(X, Y, 2, [-5.0, 100.0, float("nan")])
    assert no_effect.indices.tolist() == [0, 4, 5, 7, 9]


def test_small_and_empty_input_unchanged() -> None:
    x = np.arange(8.0)
    y = np.array([3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0])
    d = downsample_min_max(x, y, 4)
    assert d.indices.tolist() == list(range(8))
    np.testing.assert_array_equal(d.y, y)
    assert downsample_min_max([], [], 1).indices.tolist() == []
    assert downsample_min_max(x, y, 10**30).indices.tolist() == list(range(8))


@pytest.mark.parametrize(
    ("x", "y", "buckets", "message"),
    [
        ([0.0, 1.0, 2.0], [0.0, 1.0], 1, "length mismatch: x has 3 values but y has 2"),
        ([0.0, 2.0, 1.0], [0.0, 0.0, 0.0], 1, r"non-monotonic x: x\[2\] < x\[1\]"),
        ([0.0, float("nan")], [0.0, 0.0], 1, "non-finite x-value at index 1"),
        ([0.0], [0.0], 0, "buckets must be at least 1"),
        ([0.0], [0.0], -3, "buckets must be at least 1"),
    ],
)
def test_validation_errors(
    x: list[float], y: list[float], buckets: int, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        downsample_min_max(x, y, buckets)


def test_fail1_hard_downsampling_keeps_every_violation() -> None:
    tr, yr = _read_xy(CORPUS / "fail1" / "trended.csv")
    tt, yt = _read_xy(CORPUS / "fail1" / "simulated.csv")
    # The corpus case's tolerances (param.json), given explicitly so the
    # check does not depend on the library default.
    opts = Options(tolerances=Tolerances(rtolx=2e-3, rtoly=2e-3))
    r = compare(tr, yr, tt, yt, opts)
    s = summarize(r, tr, opts)
    assert r.status == Status.FAIL
    pins = [iv.worst_x for iv in s.intervals]
    d = downsample_min_max(tt, yt, 50, pins)

    errors = r.errors[1]
    for iv in s.intervals:
        xs = tt[d.indices]
        inside = (xs >= iv.start_x) & (xs <= iv.end_x) & (errors[d.indices] != 0.0)
        assert inside.any(), (iv.start_x, iv.end_x)

    # Pinned values shared with the Rust and TypeScript tests.
    assert (len(tt), len(pins)) == (5041, 35)
    assert len(d.indices) == 117
    assert int(d.indices.sum()) == 311003
    assert d.indices[:8].tolist() == [0, 101, 202, 303, 404, 504, 605, 706]
    assert d.indices[-4:].tolist() == [4939, 4940, 5029, 5040]
