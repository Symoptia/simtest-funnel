"""Short plain-text renderings of tool results (for text-only clients)."""

from __future__ import annotations

from simtest_funnel_mcp.models import (
    COEFFICIENTS,
    Coefficients,
    CompareResult,
    DescribeResult,
    Row,
)


def g(value: float | None) -> str:
    """Format a number with 4 significant digits (``-`` when absent)."""
    if value is None:
        return "-"
    return f"{value:.4g}"


def _coefficients(c: Coefficients) -> str:
    return " ".join(f"{k}={g(getattr(c, k))}" for k in COEFFICIENTS)


def render_describe(d: DescribeResult) -> str:
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
        lines.append(f"time {g(t.start)} .. {g(t.end)} (span {g(t.span)}), {sampling}")
    lines.append(f"{len(d.columns)} signal column(s): name min max range")
    for c in d.columns:
        bad = f" bad_values={c.bad_values}" if c.bad_values else ""
        lines.append(f"  {c.name} {g(c.min)} {g(c.max)} {g(c.range)}{bad}")
    for p in d.problems:
        lines.append(f"problem: {p}")
    return "\n".join(lines)


def _pct(f: float | None) -> str:
    return "-" if f is None else f"{100 * f:.3g}%"


def _row_line(r: Row) -> str:
    head = f"{r.verdict.upper()} {r.column} [{r.tolerance_set}]"
    if r.verdict == "error":
        status = f" status {r.status} {r.status_name}" if r.status is not None else ""
        return f"{head}:{status} - {r.problem}"
    parts = [
        f"{r.points_outside}/{r.points_compared} points outside "
        f"({_pct(r.fraction_of_span_outside)} of span)"
    ]
    if r.worst is not None:
        parts.append(
            f"worst {r.worst.deviation:+.4g} at t={g(r.worst.x)} "
            f"(tube half-width {g(r.worst.tube_half_width_y)})"
        )
    parts.append(f"{r.interval_count} interval(s)")
    line = f"{head}: " + ", ".join(parts)
    if r.tolerances is not None:
        line += f"\n    tolerances (column override): {_coefficients(r.tolerances)}"
    for iv in r.intervals or []:
        line += (
            f"\n    {iv.direction} t={g(iv.start_x)}..{g(iv.end_x)} "
            f"({iv.point_count} pts, worst {iv.worst_deviation:+.4g} at t={g(iv.worst_x)})"
        )
    if r.intervals is not None and r.interval_count and r.interval_count > len(r.intervals):
        line += f"\n    ... {r.interval_count - len(r.intervals)} more interval(s)"
    return line


def render_compare(c: CompareResult) -> str:
    lines = [
        f"reference {c.reference.path} (time column {c.reference.time_column!r}, "
        f"{c.reference.row_count} rows)",
        f"test {c.test.path} (time column {c.test.time_column!r}, {c.test.row_count} rows)",
    ]
    if c.x_range.lo is not None or c.x_range.hi is not None:
        lines.append(f"x_range {g(c.x_range.lo)} .. {g(c.x_range.hi)}")
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
            lines.append(_row_line(r))
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
        lines.append("pytest snippet:\n```python\n" + c.snippet + "```")
    return "\n".join(lines)
