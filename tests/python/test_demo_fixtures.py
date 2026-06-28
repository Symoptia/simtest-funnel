"""Verify the committed demo CSV fixtures match the signal formulas.

Guards against drift between `examples/web/public/{reference,test}.csv` and the
single source of truth in `tests/python/tools/demo_signals.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))

import demo_signals as d  # noqa: E402

PUBLIC = (
    Path(__file__).resolve().parents[2] / "examples" / "web" / "public"
)


def _load(name: str) -> np.ndarray:
    return np.loadtxt(PUBLIC / name, delimiter=",", skiprows=1)


def test_reference_fixture_matches_formula() -> None:
    committed = _load("reference.csv")
    assert committed.shape == (d.N_SAMPLES, len(d.COLUMNS))
    assert np.allclose(committed, d.reference_table(), atol=1e-9, rtol=0.0)


def test_test_fixture_matches_formula() -> None:
    committed = _load("test.csv")
    assert committed.shape == (d.N_SAMPLES, len(d.COLUMNS))
    assert np.allclose(committed, d.test_table(), atol=1e-9, rtol=0.0)


def test_fixture_header() -> None:
    for name in ("reference.csv", "test.csv"):
        header = (PUBLIC / name).read_text().splitlines()[0]
        assert header == ",".join(d.COLUMNS)
