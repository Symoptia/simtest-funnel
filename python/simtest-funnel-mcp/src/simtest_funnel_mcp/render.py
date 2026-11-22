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
    FileInfo,
    PlotResult,
    Row,
    SourceInfo,
    TimeTolerance,
)

#: URLs longer than this are shortened in the text (never in structured content).
MAX_URL_CHARS = 200


def short_url(url: str) -> str:
    """``url``, with its middle elided when longer than :data:`MAX_URL_CHARS`."""
    if len(url) <= MAX_URL_CHARS:
        return url
    keep = (MAX_URL_CHARS - 1) // 2
    return url[:keep] + "…" + url[-keep:]


def source_line(src: SourceInfo) -> str:
    """``fetched <time>, <size> bytes, sha256 <12 hex>…`` for a URL input."""
    line = f"fetched {src.fetched_at}, {src.size} bytes, sha256 {src.sha256[:12]}…"
    if src.reused:
        line += ", cached copy of this server process"
    if src.final_url is not None:
        line += f", redirected to {short_url(src.final_url)}"
    return line


def _file_line(role: str, f: FileInfo) -> str:
    name = short_url(f.path) if f.source is not None else f.path
    line = f"{role} {name} (time column {f.time_column!r}, {f.row_count} rows)"
    if f.source is not None:
        line += f"\n    {source_line(f.source)}"
    return line


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


def tg(value: float | None, digits: int, iso: str | None = None) -> str:
    """Format a time value with ``digits`` significant digits, or as its ISO
    8601 form when given (date-time axes)."""
    if iso is not None:
        return iso
    if value is None:
        return "-"
    return f"{value:.{digits}g}"


def _tol_line(label: str, c: Coefficients, tt: TimeTolerance | None) -> str:
    line = f"tolerance set {label}: {_coefficients(c)}"
    if tt is not None:
        line += f"; time tolerance {tt.seconds:g} s ({tt.duration})"
    return line


def _coefficients(c: Coefficients) -> str:
    return " ".join(f"{k}={g(getattr(c, k))}" for k in COEFFICIENTS)


def render_describe(d: DescribeResult, digits: int = MIN_TIME_DIGITS) -> str:
    t = d.time
    s = t.sampling
    header = f", header line {d.header_line}" if d.header_line != 1 else ""
    kind = ""
    if t.kind == "datetime":
        zone = {"offset": "UTC (offsets)", "none": "no time zone, read as UTC"}.get(
            t.time_zone or "", "mixed time zones"
        )
        kind = f", ISO 8601 date-times ({zone})"
    name = short_url(d.path) if d.source is not None else d.path
    lines = [
        f"{name}: {d.row_count} rows, time column {d.time_column!r} ({d.time_column_rule})"
        f"{kind}{header}",
    ]
    if d.source is not None:
        lines.append(source_line(d.source))
    if t.start is not None:
        if t.kind == "datetime":
            sampling = (
                f"uniform, step {s.median_step_duration}"
                if s.uniform
                else f"non-uniform, step min {g(s.min_step)} s / median "
                f"{s.median_step_duration} / max {g(s.max_step)} s"
            )
            span = t.span_duration
        else:
            sampling = (
                f"uniform, step {g(s.median_step)}"
                if s.uniform
                else f"non-uniform, step min {g(s.min_step)} / median {g(s.median_step)} "
                f"/ max {g(s.max_step)}"
            )
            span = g(t.span)
        lines.append(
            f"time {tg(t.start, digits, t.start_iso)} .. {tg(t.end, digits, t.end_iso)} "
            f"(span {span}), {sampling}"
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


def _row_name(r: Row) -> str:
    """The row key, plus ``(reference -> test)`` for a pair of different names."""
    if r.reference_column is not None and r.reference_column != r.test_column:
        return f"{r.column} ({r.reference_column} -> {r.test_column})"
    return r.column


def _row_line(r: Row, digits: int) -> str:
    name = _row_name(r)
    head = f"{r.verdict.upper()} {name} [{r.tolerance_set}]"
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
            f"worst {r.worst.deviation:+.4g} at t={tg(r.worst.x, digits, r.worst.x_iso)} "
            f"(tube half-width {g(r.worst.tube_half_width_y)})"
        )
    parts.append(f"{r.interval_count} interval(s)")
    line = f"{head}: " + ", ".join(parts)
    if r.tolerances is not None:
        line += f"\n    tolerances (column override): {_coefficients(r.tolerances)}"
        if r.time_tolerance is not None:
            tt = r.time_tolerance
            line += f"; time tolerance {tt.seconds:g} s ({tt.duration})"
    for iv in r.intervals or []:
        line += (
            f"\n    {iv.direction} t={tg(iv.start_x, digits, iv.start_x_iso)}.."
            f"{tg(iv.end_x, digits, iv.end_x_iso)} "
            f"({iv.point_count} pts, worst {iv.worst_deviation:+.4g} "
            f"at t={tg(iv.worst_x, digits, iv.worst_x_iso)})"
        )
    if r.intervals is not None and r.interval_count and r.interval_count > len(r.intervals):
        line += f"\n    ... {r.interval_count - len(r.intervals)} more interval(s)"
    return line


def render_compare(c: CompareResult, digits: int = MIN_TIME_DIGITS) -> str:
    lines = [_file_line("reference", c.reference), _file_line("test", c.test)]
    if c.x_range.lo is not None or c.x_range.hi is not None:
        x = c.x_range
        lines.append(f"x_range {tg(x.lo, digits, x.lo_iso)} .. {tg(x.hi, digits, x.hi_iso)}")
    for s in c.tolerance_sets:
        lines.append(_tol_line(s.label, s.resolved, s.time_tolerance))
    t = c.totals
    pending = f", {t.not_completed} not completed (time limit)" if t.not_completed else ""
    lines.append(
        f"result: {t.failed} fail, {t.errors} error, {t.passed} pass ({t.rows} rows){pending}"
    )
    passing: dict[str, list[str]] = {}
    for r in c.rows:
        if r.verdict == "pass":
            passing.setdefault(r.tolerance_set, []).append(
                _row_name(r) + (" (override)" if r.tolerances is not None else "")
            )
        else:
            lines.append(_row_line(r, digits))
    for label, cols in passing.items():
        lines.append(f"PASS [{label}]: {', '.join(cols)}")
    if c.rows_omitted:
        lines.append(f"{c.rows_omitted} row(s) omitted (raise max_rows to see them)")
    if c.not_completed:
        more = f" (+{c.not_completed_omitted} more)" if c.not_completed_omitted else ""
        lines.append(
            "NOT COMPLETED (time limit): "
            + ", ".join(f"{p.column} [{p.tolerance_set}]" for p in c.not_completed)
            + more
        )
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
    lines = [_file_line("reference", p.reference), _file_line("test", p.test)]
    if p.x_range.lo is not None or p.x_range.hi is not None:
        x = p.x_range
        lines.append(f"x_range {tg(x.lo, digits, x.lo_iso)} .. {tg(x.hi, digits, x.hi_iso)}")
    s = p.tolerance_set
    lines.append(_tol_line(s.label, s.resolved, s.time_tolerance))
    r = p.row
    if r.verdict == "pass":
        name = _row_name(r)
        lines.append(f"PASS {name} [{r.tolerance_set}]: {r.points_compared} points compared")
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
        f"drawn: reference {d.reference} / test {d.test} / tube {d.tube_lower}+{d.tube_upper} "
        f"points (min/max of {d.buckets} buckets), {d.violation_markers} "
        f"violation marker(s), {d.violation_regions} shaded region(s); "
        f"time {tg(p.view.lo, digits, p.view.lo_iso)} .. {tg(p.view.hi, digits, p.view.hi_iso)}"
    )
    for n in p.notes:
        lines.append(f"note: {n}")
    return "\n".join(lines)
