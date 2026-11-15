"""``describe_signals``: what an agent needs to choose columns and tolerances."""

from __future__ import annotations

import math

import numpy as np

from simtest_funnel_mcp.csvio import SignalFile
from simtest_funnel_mcp.models import ColumnInfo, DescribeResult, Sampling, TimeInfo
from simtest_funnel_mcp.selection import expand

#: Default cap on columns (and problems) listed by describe_signals.
DEFAULT_MAX_COLUMNS = 100
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


def describe(
    sf: SignalFile,
    *,
    columns: list[str] | None = None,
    max_columns: int = DEFAULT_MAX_COLUMNS,
) -> DescribeResult:
    """Describe a loaded file (no sample values are returned).

    ``columns`` filters the signal columns by exact name or glob pattern;
    at most ``max_columns`` columns and ``max_columns`` problems are listed,
    with totals and omitted counts reported.
    """
    if max_columns < 1:
        raise ValueError("max_columns must be >= 1")
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
    if columns is None:
        selected = list(sf.signal_columns)
    else:
        if not columns:
            raise ValueError("columns is empty; omit it to describe all columns")
        expanded, unmatched = expand(columns, sf.signal_columns)
        wanted = set(expanded)
        selected = [c for c in sf.signal_columns if c in wanted]
        for entry in unmatched:
            problems.append(f"columns filter: no signal column matches {entry!r}")
    infos: list[ColumnInfo] = []
    for name in selected:
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
        infos.append(info)
    return DescribeResult(
        path=str(sf.path),
        time_column=sf.time_column,
        time_column_rule="named time" if sf.time_column_rule == "named time" else "first column",
        row_count=sf.row_count,
        time=time,
        columns=infos[:max_columns],
        columns_total=len(sf.signal_columns),
        columns_selected=len(selected),
        columns_omitted=max(0, len(infos) - max_columns),
        problems=problems[:max_columns],
        problems_omitted=max(0, len(problems) - max_columns),
    )
