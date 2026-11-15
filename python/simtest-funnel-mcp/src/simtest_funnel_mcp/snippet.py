"""Reproducible pytest snippet for a ``compare_signals`` result."""

from __future__ import annotations

from simtest_funnel_mcp.compare import CompareOutcome
from simtest_funnel_mcp.models import COEFFICIENTS

_HEADER = '''\
"""Funnel comparison reproduced from simtest-funnel-mcp {version}.

Requires: pip install "simtest-funnel>={funnel_version}" pandas pytest
Each case asserts the status the server observed. To use this as a CI gate,
set every expected status to funnel.Status.PASS.
"""

import numpy as np
import pandas as pd
import pytest

import simtest.funnel as funnel

REFERENCE = {reference!r}
TEST = {test!r}
REFERENCE_TIME = {reference_time!r}
TEST_TIME = {test_time!r}
X_RANGE = funnel.Range(lo={lo}, hi={hi})

# (column, tolerance set, tolerances as given, expected status)
CASES = [
'''

_FOOTER = '''\
]


def _column(path: str, name: str) -> np.ndarray:
    # Same dialect as the server: comma-separated, header row, '#' comments.
    frame = pd.read_csv(path, comment="#", skipinitialspace=True, dtype=str, keep_default_na=False)
    frame.columns = [str(c).strip() for c in frame.columns]
    values = pd.to_numeric(frame[name].str.strip(), errors="coerce")
    return values.to_numpy(dtype=np.float64, na_value=np.nan)


@pytest.mark.parametrize(
    ("column", "label", "tolerances", "expected"),
    CASES,
    ids=[f"{{c[0]}}-{{c[1]}}" for c in CASES],
)
def test_funnel(column: str, label: str, tolerances: funnel.Tolerances, expected: int) -> None:
    result = funnel.compare(
        _column(REFERENCE, REFERENCE_TIME),
        _column(REFERENCE, column),
        _column(TEST, TEST_TIME),
        _column(TEST, column),
        funnel.Options(tolerances=tolerances, x_range=X_RANGE),
    )
    assert result.status == expected, funnel.status_message(result.status)
'''


def _bound(value: float | None, default: str) -> str:
    return default if value is None else repr(float(value))


def make_snippet(outcome: CompareOutcome, version: str, funnel_version: str) -> str:
    """Return a self-contained pytest module reproducing ``outcome``."""
    res = outcome.result
    lo, hi = outcome.x_range
    out = _HEADER.format(
        version=version,
        funnel_version=funnel_version,
        reference=res.reference.path,
        test=res.test.path,
        reference_time=res.reference.time_column,
        test_time=res.test.time_column,
        lo=_bound(lo, 'float("-inf")'),
        hi=_bound(hi, 'float("inf")'),
    )
    skipped: list[str] = []
    for rec in outcome.records:
        row = rec.row
        if not rec.from_library or row.status is None or row.status_name is None:
            skipped.append(f"#   {row.column} [{row.tolerance_set}]: {row.problem}\n")
            continue
        args = ", ".join(f"{k}={rec.given[k]!r}" for k in COEFFICIENTS if k in rec.given)
        out += (
            f"    ({row.column!r}, {row.tolerance_set!r}, funnel.Tolerances({args}), "
            f"funnel.Status.{row.status_name}),\n"
        )
    if skipped:
        out += "    # Not reproduced (not decided by the library):\n"
        out += "".join("    " + s for s in skipped)
    return out + _FOOTER.format()
