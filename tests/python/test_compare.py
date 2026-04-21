"""Integration tests for the simtest.funnel Python API."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from simtest.funnel import (
    Options,
    Range,
    Status,
    Tolerances,
    compare,
    compare_dataframes,
    default_options,
    status_message,
    version,
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


def test_version_is_nonempty() -> None:
    assert isinstance(version(), str) and len(version()) > 0


def test_default_options_matches_2e_minus_3() -> None:
    o = default_options()
    assert o.tolerances.rtolx == pytest.approx(2e-3)
    assert o.tolerances.rtoly == pytest.approx(2e-3)


def test_status_message_roundtrips() -> None:
    for s in Status:
        assert status_message(int(s))


def test_fail1_corpus_is_fail() -> None:
    xr, yr = _read_xy(CORPUS / "fail1" / "trended.csv")
    xt, yt = _read_xy(CORPUS / "fail1" / "simulated.csv")
    r = compare(
        xr, yr, xt, yt,
        Options(tolerances=Tolerances(rtolx=2e-3, rtoly=2e-3)),
    )
    assert r.status == Status.FAIL
    assert np.any(r.errors[1] != 0.0)


def test_success1_corpus_is_pass() -> None:
    xr, yr = _read_xy(CORPUS / "success1" / "trended.csv")
    xt, yt = _read_xy(CORPUS / "success1" / "simulated.csv")
    r = compare(
        xr, yr, xt, yt,
        Options(tolerances=Tolerances(rtolx=2e-3, rtoly=2e-3)),
    )
    assert r.status == Status.PASS


def test_missing_reference_status() -> None:
    xr = np.linspace(0.0, 1.0, 11)
    yr = np.sin(2 * np.pi * xr)
    xt = np.linspace(-0.5, 1.5, 21)
    yt = np.sin(2 * np.pi * xt)
    opts = Options(
        tolerances=Tolerances(atoly=1.0, rtolx=0.0, rtoly=0.0),
        x_range=Range(),
    )
    r = compare(xr, yr, xt, yt, opts)
    assert r.status in (Status.MISSING_REFERENCE, Status.PASS)


def test_missing_test_status() -> None:
    xt = np.linspace(0.0, 1.0, 11)
    yt = np.sin(2 * np.pi * xt)
    xr = np.linspace(-0.5, 1.5, 21)
    yr = np.sin(2 * np.pi * xr)
    opts = Options(
        tolerances=Tolerances(atoly=1.0, rtolx=0.0, rtoly=0.0),
        x_range=Range(),
    )
    r = compare(xr, yr, xt, yt, opts)
    assert r.status in (Status.MISSING_TEST, Status.PASS)


def test_compare_dataframes_two_signals_with_overrides() -> None:
    t = np.linspace(0.0, 1.0, 51)
    ref = pd.DataFrame(
        {"time": t, "a": np.sin(2 * np.pi * t), "b": np.cos(2 * np.pi * t)}
    )
    tst = pd.DataFrame(
        {
            "time": t,
            "a": np.sin(2 * np.pi * t) + 0.01,
            "b": np.cos(2 * np.pi * t) + 0.01,
        }
    )
    loose = Options(tolerances=Tolerances(atoly=0.1))
    tight = Options(tolerances=Tolerances(atoly=1e-6))
    out = compare_dataframes(
        ref, tst,
        default_options=loose,
        option_overrides={"b": tight},
    )
    assert set(out.keys()) == {"a", "b"}
    assert out["a"].status == Status.PASS
    assert out["b"].status == Status.FAIL


def test_compare_dataframes_requires_time_first_column() -> None:
    ref = pd.DataFrame({"x": [0.0, 1.0], "a": [0.0, 1.0]})
    tst = pd.DataFrame({"time": [0.0, 1.0], "a": [0.0, 1.0]})
    with pytest.raises(ValueError):
        compare_dataframes(ref, tst)
