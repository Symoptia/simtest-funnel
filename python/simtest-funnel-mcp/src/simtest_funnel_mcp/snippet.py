"""Reproducible pytest snippet for a ``compare_signals`` result."""

from __future__ import annotations

import inspect
import math
from pathlib import Path

from simtest_funnel_mcp import reader
from simtest_funnel_mcp.compare import CompareOutcome
from simtest_funnel_mcp.models import COEFFICIENTS
from simtest_funnel_mcp.timeaxis import format_iso

#: Hard cap on the snippet size (characters). Cases that do not fit are
#: replaced by a comment stating how many were left out.
MAX_SNIPPET_CHARS = 64_000

_HEADER = '''\
"""Funnel comparison reproduced from simtest-funnel-mcp {version}.

Requires: pip install "simtest-funnel>={funnel_version}" pandas pytest
Each case asserts the status the server observed. To use this as a CI gate,
set every expected status to funnel.Status.PASS.
"""

import functools
import os
from pathlib import Path

import pytest

import simtest.funnel as funnel

# Data files are resolved against SIMTEST_FUNNEL_DATA_ROOT, defaulting to the
# current working directory. Paths below are relative to {base!r}, the
# directory the server resolved them against; run pytest from there (or from
# the same place in a CI checkout), or set SIMTEST_FUNNEL_DATA_ROOT.
DATA_ROOT = Path(os.environ.get("SIMTEST_FUNNEL_DATA_ROOT", Path.cwd()))
{reference_line}
{test_line}
REFERENCE_HEADER_LINE = {reference_header_line!r}
TEST_HEADER_LINE = {test_header_line!r}
REFERENCE_TIME = {reference_time!r}
TEST_TIME = {test_time!r}
{x_range_comment}X_RANGE = funnel.Range(lo={lo}, hi={hi})

'''

_CASES_HEAD = '''
# (row key, reference column, test column, tolerance set, tolerances as given,
#  expected status)
CASES = [
'''

_FOOTER = '''\
]


@functools.lru_cache(maxsize=None)
def _columns(path: Path, header_line: int) -> dict:
    return read_signal_columns(str(path), header_line).values


@pytest.mark.parametrize(
    ("key", "reference_column", "test_column", "label", "tolerances", "expected"),
    CASES,
    ids=[f"{c[0]}-{c[3]}" for c in CASES],
)
def test_funnel(
    key: str,
    reference_column: str,
    test_column: str,
    label: str,
    tolerances: funnel.Tolerances,
    expected: int,
) -> None:
    ref = _columns(REFERENCE, REFERENCE_HEADER_LINE)
    tst = _columns(TEST, TEST_HEADER_LINE)
    result = funnel.compare(
        ref[REFERENCE_TIME],
        ref[reference_column],
        tst[TEST_TIME],
        tst[test_column],
        funnel.Options(tolerances=tolerances, x_range=X_RANGE),
    )
    assert result.status == expected, funnel.status_message(result.status)
'''


def _bound(value: float | None, unbounded: str) -> str:
    if value is None:
        return unbounded
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"x_range bound must be finite, got {v}")
    return repr(v)


def _path_line(name: str, path: Path, base: Path) -> str:
    try:
        rel = path.relative_to(base)
    except ValueError:
        return (
            f"# {name} lies outside {str(base)!r}; this absolute path will not "
            f"resolve on another machine.\n{name} = Path({str(path)!r})"
        )
    return f"{name} = DATA_ROOT / {rel.as_posix()!r}"


def _tolerance_args(given: dict[str, float]) -> str:
    parts = []
    for k in COEFFICIENTS:
        if k in given:
            v = float(given[k])
            if not math.isfinite(v):
                raise ValueError(f"tolerance {k} must be finite, got {v}")
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def make_snippet(
    outcome: CompareOutcome, version: str, funnel_version: str, base: Path
) -> str:
    """Return a self-contained pytest module reproducing the returned rows.

    Only the rows returned in the result (``max_rows``) become cases; paths
    under ``base`` are written relative to it.
    """
    res = outcome.result
    lo, hi = outcome.x_range
    same_path = res.reference.path == res.test.path
    comment = ""
    if outcome.datetime_axis and (lo is not None or hi is not None):
        iso = [format_iso(v, outcome.time_zone) or "unbounded" for v in (lo, hi)]
        comment = f"# x_range in seconds since 1970-01-01 UTC: lo = {iso[0]}, hi = {iso[1]}\n"
    out = _HEADER.format(
        version=version,
        funnel_version=funnel_version,
        base=str(base),
        reference_line=_path_line("REFERENCE", Path(res.reference.path), base),
        test_line=(
            "TEST = REFERENCE" if same_path else _path_line("TEST", Path(res.test.path), base)
        ),
        reference_header_line=res.reference.header_line or 1,
        test_header_line=res.test.header_line or 1,
        reference_time=res.reference.time_column,
        test_time=res.test.time_column,
        x_range_comment=comment,
        lo=_bound(lo, 'float("-inf")'),
        hi=_bound(hi, 'float("inf")'),
    )
    out += inspect.getsource(reader) + _CASES_HEAD
    shown = outcome.records[: len(res.rows)]
    budget = MAX_SNIPPET_CHARS - len(out) - len(_FOOTER) - 400
    cases: list[str] = []
    skipped: list[str] = []
    dropped = 0
    for rec in shown:
        row = rec.row
        if not rec.from_library or row.status is None or row.status_name is None:
            line = f"    #   {row.column} [{row.tolerance_set}]: {row.problem}\n"
            target = skipped
        else:
            ref_col, test_col = rec.columns
            line = (
                f"    ({row.column!r}, {ref_col!r}, {test_col!r}, {row.tolerance_set!r}, "
                f"funnel.Tolerances({_tolerance_args(rec.given)}), "
                f"funnel.Status.{row.status_name}),\n"
            )
            target = cases
        if len(line) > budget:
            dropped += 1
            continue
        budget -= len(line)
        target.append(line)
    out += "".join(cases)
    if skipped:
        out += "    # Not reproduced (not decided by the library):\n" + "".join(skipped)
    if res.rows_omitted:
        out += (
            f"    # {res.rows_omitted} row(s) not returned by the server (max_rows) "
            "are not included.\n"
        )
    if res.totals.not_completed:
        out += (
            f"    # {res.totals.not_completed} comparison(s) not completed within the "
            "server's time limit are not included.\n"
        )
    if dropped:
        out += f"    # {dropped} row(s) left out to keep this snippet under the size cap.\n"
    return out + _FOOTER
