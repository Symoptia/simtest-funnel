"""Short plain-text renderings of tool results (for text-only clients)."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from simtest_funnel_mcp.models import (
    COEFFICIENTS,
    Coefficients,
    CompareResult,
    DescribeResult,
    PlotResult,
    Row,
)


def g(value: float | None) -> str:
    """Format a number with 4 significant digits (``-`` when absent)."""
    if value is None:
        return "-"
    return f"{value:.4g}"


#: Significant digits used for times when no finer resolution is needed.
MIN_TIME_DIGITS = 4


def time_digits(*times: NDArray[np.float64]) -> int:
    """Significant digits that keep adjacent samples of ``times`` distinct.

    Derived from the largest finite ``|t|`` and the smallest positive time
    step over all arrays: enough digits to resolve a tenth of that step.
    """
    mag = 0.0
    step = math.inf
    for t in times:
        finite = t[np.isfinite(t)]
        if finite.shape[0] == 0:
            continue
        mag = max(mag, float(np.max(np.abs(finite))))
        if finite.shape[0] >= 2:
            d = np.diff(np.sort(finite))
            d = d[d > 0]
            if d.shape[0]:
                step = min(step, float(np.min(d)))
    if mag == 0.0 or not math.isfinite(step):
        return MIN_TIME_DIGITS
    digits = math.floor(math.log10(mag)) - math.floor(math.log10(step)) + 2
    return max(MIN_TIME_DIGITS, min(17, digits))


def tg(value: float | None, digits: int) -> str:
    """Format a time value with ``digits`` significant digits."""
    if value is None:
        return "-"
    return f"{value:.{digits}g}"


def _coefficients(c: Coefficients) -> str:
    return " ".join(f"{k}={g(getattr(c, k))}" for k in COEFFICIENTS)


def render_describe(d: DescribeResult, digits: int = MIN_TIME_DIGITS) -> str:
    lines = [
        f"{d.path}: {d.row_count} rows, time column {d.time_column!r} ({d.time_column_rule})",
    ]
    t = d.time
    s = t.sampling
    if t.start is not None:
        sampling = (
            f"uniform, step {g(s.median_step)}"
            if s.uniform
            else f"non-uniform, step min {g(s.min_step)} / median {g(s.median_step)} "
            f"/ max {g(s.max_step)}"
        )
        lines.append(
            f"time {tg(t.start, digits)} .. {tg(t.end, digits)} (span {g(t.span)}), {sampling}"
        )
    selected = (
        f", {d.columns_selected} selected" if d.columns_selected != d.columns_total else ""
    )
    lines.append(
        f"{d.columns_total} signal column(s){selected}; listed: name min max range"
    )
    for c in d.columns:
        bad = f" bad_values={c.bad_values}" if c.bad_values else ""
        lines.append(f"  {c.name} {g(c.min)} {g(c.max)} {g(c.range)}{bad}")
    if d.columns_omitted:
        lines.append(
            f"  ... {d.columns_omitted} more column(s) omitted (raise max_columns or filter "
            "with columns)"
        )
    for p in d.problems:
        lines.append(f"problem: {p}")
    if d.problems_omitted:
        lines.append(f"... {d.problems_omitted} more problem(s) omitted")
    for n in d.notes:
        lines.append(f"note: {n}")
    return "\n".join(lines)


def _pct(f: float | None) -> str:
    return "-" if f is None else f"{100 * f:.3g}%"


def _row_line(r: Row, digits: int) -> str:
    head = f"{r.verdict.upper()} {r.column} [{r.tolerance_set}]"
    if r.verdict == "error":
        status = f" status {r.status} {r.status_name}" if r.status is not None else ""
        counts = (
            f" ({r.points_outside}/{r.points_compared} points outside)"
            if r.points_compared is not None
            else ""
        )
        return f"{head}:{status}{counts} - {r.problem}"
    parts = [
        f"{r.points_outside}/{r.points_compared} points outside "
        f"({_pct(r.fraction_of_span_outside)} of span)"
    ]
    if r.worst is not None:
        parts.append(
            f"worst {r.worst.deviation:+.4g} at t={tg(r.worst.x, digits)} "
            f"(tube half-width {g(r.worst.tube_half_width_y)})"
        )
    parts.append(f"{r.interval_count} interval(s)")
    line = f"{head}: " + ", ".join(parts)
    if r.tolerances is not None:
        line += f"\n    tolerances (column override): {_coefficients(r.tolerances)}"
    for iv in r.intervals or []:
        line += (
            f"\n    {iv.direction} t={tg(iv.start_x, digits)}..{tg(iv.end_x, digits)} "
            f"({iv.point_count} pts, worst {iv.worst_deviation:+.4g} "
            f"at t={tg(iv.worst_x, digits)})"
        )
    if r.intervals is not None and r.interval_count and r.interval_count > len(r.intervals):
        line += f"\n    ... {r.interval_count - len(r.intervals)} more interval(s)"
    return line


def render_compare(c: CompareResult, digits: int = MIN_TIME_DIGITS) -> str:
    lines = [
        f"reference {c.reference.path} (time column {c.reference.time_column!r}, "
        f"{c.reference.row_count} rows)",
        f"test {c.test.path} (time column {c.test.time_column!r}, {c.test.row_count} rows)",
    ]
    if c.x_range.lo is not None or c.x_range.hi is not None:
        lines.append(f"x_range {tg(c.x_range.lo, digits)} .. {tg(c.x_range.hi, digits)}")
    for s in c.tolerance_sets:
        lines.append(f"tolerance set {s.label}: {_coefficients(s.resolved)}")
    t = c.totals
    lines.append(f"result: {t.failed} fail, {t.errors} error, {t.passed} pass ({t.rows} rows)")
    passing: dict[str, list[str]] = {}
    for r in c.rows:
        if r.verdict == "pass":
            passing.setdefault(r.tolerance_set, []).append(
                r.column + (" (override)" if r.tolerances is not None else "")
            )
        else:
            lines.append(_row_line(r, digits))
    for label, cols in passing.items():
        lines.append(f"PASS [{label}]: {', '.join(cols)}")
    if c.rows_omitted:
        lines.append(f"{c.rows_omitted} row(s) omitted (raise max_rows to see them)")
    if c.columns_only_in_reference:
        lines.append(
            f"only in reference ({c.columns_only_in_reference_count}): "
            + ", ".join(c.columns_only_in_reference)
        )
    if c.columns_only_in_test:
        lines.append(
            f"only in test ({c.columns_only_in_test_count}): " + ", ".join(c.columns_only_in_test)
        )
    for n in c.notes:
        lines.append(f"note: {n}")
    if c.snippet is not None:
        # The snippet is sent once, in the structured content (see design.md).
        lines.append(
            f"pytest snippet ({len(c.snippet.splitlines())} lines): in the structured "
            "content field 'snippet'"
        )
    return "\n".join(lines)


def _kb(n: int) -> str:
    return f"{n / 1000:.1f} kB"


def render_plot(p: PlotResult, digits: int = MIN_TIME_DIGITS) -> str:
    lines = [
        f"reference {p.reference.path} (time column {p.reference.time_column!r}, "
        f"{p.reference.row_count} rows)",
        f"test {p.test.path} (time column {p.test.time_column!r}, {p.test.row_count} rows)",
    ]
    if p.x_range.lo is not None or p.x_range.hi is not None:
        lines.append(f"x_range {tg(p.x_range.lo, digits)} .. {tg(p.x_range.hi, digits)}")
    s = p.tolerance_set
    lines.append(f"tolerance set {s.label}: {_coefficients(s.resolved)}")
    r = p.row
    if r.verdict == "pass":
        lines.append(f"PASS {r.column} [{r.tolerance_set}]: {r.points_compared} points compared")
    else:
        lines.append(_row_line(r, digits))
    if p.file is not None:
        f = p.file
        dims = f" {f.width_px}x{f.height_px}" if f.width_px is not None else ""
        lines.append(f"plot written: {f.path} ({f.format.upper()}{dims}, {_kb(f.bytes)})")
    else:
        lines.append("no file written (no output_path)")
    v = p.preview
    lines.append(f"preview: inline PNG {v.width_px}x{v.height_px} ({_kb(v.bytes)})")
    d = p.drawn
    lines.append(
        f"drawn: reference {d.reference} / test {d.test} points (min/max of {d.buckets} "
        f"buckets), tube {d.tube_lower}+{d.tube_upper} points, {d.violation_markers} "
        f"violation marker(s), {d.violation_regions} shaded region(s); "
        f"time {tg(p.view.lo, digits)} .. {tg(p.view.hi, digits)}"
    )
    for n in p.notes:
        lines.append(f"note: {n}")
    return "\n".join(lines)
