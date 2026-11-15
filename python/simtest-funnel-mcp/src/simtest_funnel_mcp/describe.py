"""``describe_signals``: what an agent needs to choose columns and tolerances."""

from __future__ import annotations

import math

import numpy as np

from simtest_funnel_mcp.csvio import SignalFile
from simtest_funnel_mcp.models import ColumnInfo, DescribeResult, Sampling, TimeInfo

#: Relative step spread below which sampling counts as uniform.
UNIFORM_RTOL = 1e-6


def finite_or_none(value: float | None) -> float | None:
    """``value`` as float, or ``None`` if absent or not finite."""
    if value is None:
        return None
    v = float(value)
    return v if math.isfinite(v) else None


def _sampling(t: np.ndarray) -> Sampling:
    finite = t[np.isfinite(t)]
    if finite.shape[0] < 2:
        return Sampling(uniform=False)
    steps = np.diff(finite)
    lo = float(np.min(steps))
    med = float(np.median(steps))
    hi = float(np.max(steps))
    scale = abs(med) if med != 0 else 1.0
    uniform = lo >= 0 and (hi - lo) <= UNIFORM_RTOL * scale
    return Sampling(uniform=uniform, min_step=lo, median_step=med, max_step=hi)


def describe(sf: SignalFile) -> DescribeResult:
    """Describe a loaded file (no sample values are returned)."""
    t = sf.time
    finite_t = t[np.isfinite(t)]
    if finite_t.shape[0]:
        start = float(finite_t[0])
        end = float(finite_t[-1])
        time = TimeInfo(start=start, end=end, span=end - start, sampling=_sampling(t))
    else:
        time = TimeInfo(sampling=Sampling(uniform=False))
    problems = sf.time_problems()
    if sf.row_count == 0:
        problems.append("file has a header but no data rows")
    columns: list[ColumnInfo] = []
    for name in sf.signal_columns:
        y = sf.values[name]
        finite = y[np.isfinite(y)]
        bad = sf.bad_cells[name]
        if finite.shape[0]:
            lo = float(np.min(finite))
            hi = float(np.max(finite))
            info = ColumnInfo(name=name, min=lo, max=hi, range=hi - lo)
        else:
            info = ColumnInfo(name=name)
        if bad:
            info.bad_values = bad
            problems.append(f"column {name!r} has {bad} non-numeric, empty or non-finite value(s)")
        columns.append(info)
    return DescribeResult(
        path=str(sf.path),
        time_column=sf.time_column,
        time_column_rule="named time" if sf.time_column_rule == "named time" else "first column",
        row_count=sf.row_count,
        time=time,
        columns=columns,
        problems=problems,
    )
