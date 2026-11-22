"""``compare_signals``: funnel comparison of CSV columns via ``simtest.funnel``.

All numerics (comparison, tolerance resolution, violation intervals) come
from the library; this module only selects columns, shapes options and
results, and bounds the output size.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

import simtest.funnel as funnel
from simtest_funnel_mcp.csvio import SignalFile
from simtest_funnel_mcp.describe import finite_or_none
from simtest_funnel_mcp.models import (
    COEFFICIENTS,
    X_COEFFICIENTS,
    Y_COEFFICIENTS,
    Coefficients,
    CompareResult,
    FileInfo,
    Interval,
    NotCompleted,
    RangeOut,
    Row,
    ToleranceSet,
    ToleranceSetOut,
    ToleranceSpec,
    Totals,
    Worst,
    XRange,
)
from simtest_funnel_mcp.selection import expand, is_pattern

#: Default cap on intervals listed per failing row.
DEFAULT_MAX_INTERVALS = 5
#: Default cap on rows in a result.
DEFAULT_MAX_ROWS = 100
#: Cap on column names listed as present in only one file.
MAX_LISTED_COLUMNS = 50
#: Label of the single set used when no tolerance set is given.
DEFAULT_SET_LABEL = "default"

_LIBRARY_MISSING = {int(funnel.Status.MISSING_REFERENCE), int(funnel.Status.MISSING_TEST)}
_VERDICT_ORDER = {"error": 0, "fail": 1, "pass": 2}


#: Default time limit of a tool call, in seconds.
DEFAULT_TIME_LIMIT = 60.0


class CompareArgumentError(ValueError):
    """Invalid ``compare_signals`` arguments (reported as a tool error)."""


@dataclass(frozen=True)
class TimeLimit:
    """Time limit of one tool call: a deadline plus the call's cancel token.

    Comparisons are started only while time remains and get the remaining
    time as their ``timeout``; a comparison that times out raises
    ``funnel.ComparisonTimeout``. Cancelling ``cancel`` (the call was
    cancelled by the client) makes the running comparison raise
    ``funnel.ComparisonCancelled``.
    """

    seconds: float
    #: ``time.monotonic()`` value at which the limit is reached.
    deadline: float
    cancel: funnel.CancelToken = field(default_factory=funnel.CancelToken)

    @classmethod
    def start(cls, seconds: float, cancel: funnel.CancelToken | None = None) -> TimeLimit:
        """A limit of ``seconds`` from now (positive and finite)."""
        if not (math.isfinite(seconds) and seconds > 0):
            raise CompareArgumentError(
                f"time_limit must be a positive finite number of seconds, got {seconds}"
            )
        return cls(
            seconds=seconds,
            deadline=time.monotonic() + seconds,
            cancel=cancel if cancel is not None else funnel.CancelToken(),
        )

    def remaining(self) -> float:
        """Seconds left (``0.0`` once the limit is reached)."""
        return max(0.0, self.deadline - time.monotonic())

    def describe(self) -> str:
        return f"{self.seconds:g} s"


@dataclass
class RowRecord:
    """A result row plus what the snippet needs to reproduce it."""

    row: Row
    #: Tolerance coefficients as given to the library (after overrides).
    given: dict[str, float]
    #: True when the library decided the status (snippet can reproduce it).
    from_library: bool
    #: The library's comparison and its full violation summary (only when
    #: ``from_library``); used by ``plot_signals`` to draw the same result.
    library: tuple[funnel.CompareResult, funnel.ViolationSummary] | None = None


@dataclass
class CompareOutcome:
    result: CompareResult
    #: Completed comparisons only (rows), in result order.
    records: list[RowRecord] = field(default_factory=list)
    x_range: tuple[float | None, float | None] = (None, None)
    #: (column, tolerance set) pairs stopped by the time limit, in order.
    not_completed: list[tuple[str, str]] = field(default_factory=list)


def _status_name(code: int) -> str:
    try:
        return funnel.Status(code).name
    except ValueError:
        return str(code)


def _verdict(code: int) -> Literal["pass", "fail", "error"]:
    if code == int(funnel.Status.PASS):
        return "pass"
    if code == int(funnel.Status.FAIL):
        return "fail"
    return "error"


def make_options(given: dict[str, float], lo: float | None, hi: float | None) -> funnel.Options:
    """Library options from the given coefficients (``None`` = not given)."""
    tol = funnel.Tolerances(**{k: given.get(k) for k in COEFFICIENTS})
    rng = funnel.Range(
        lo=float("-inf") if lo is None else lo,
        hi=float("inf") if hi is None else hi,
    )
    return funnel.Options(tolerances=tol, x_range=rng)


def _coefficients(t: funnel.Tolerances) -> Coefficients:
    def f(v: float | None) -> float:
        assert v is not None  # the library always returns resolved values
        return float(v)

    return Coefficients(
        atolx=f(t.atolx),
        atoly=f(t.atoly),
        ltolx=f(t.ltolx),
        ltoly=f(t.ltoly),
        rtolx=f(t.rtolx),
        rtoly=f(t.rtoly),
    )


def resolve_with_library(given: dict[str, float]) -> Coefficients:
    """The six coefficients the library resolves ``given`` to.

    Obtained from :func:`simtest.funnel.summarize` of a trivial two-point
    comparison, so the server never re-implements the resolution rule.
    """
    t = np.array([0.0, 1.0])
    y = np.zeros(2)
    opts = make_options(given, None, None)
    res = funnel.compare(t, y, t, y, opts)
    return _coefficients(funnel.summarize(res, t, opts).tolerances)


def compose_override(base: dict[str, float], override: ToleranceSpec | None) -> dict[str, float]:
    """Apply a per-column override axis-wise.

    An axis for which the override gives any coefficient is taken entirely
    from the override; the other axis keeps the set's coefficients.
    """
    if override is None:
        return dict(base)
    over = override.given()
    out: dict[str, float] = {}
    for axis in (X_COEFFICIENTS, Y_COEFFICIENTS):
        source = over if any(k in over for k in axis) else base
        for k in axis:
            if k in source:
                out[k] = source[k]
    return out


def no_x_tolerance_hint(records: list[RowRecord]) -> str | None:
    """A note for failed rows compared without any x (time) tolerance.

    Only rows the library judged FAIL and for which no x coefficient was
    given (so the library default, zero x tolerance, applied) count; an
    explicit ``atolx = 0`` is a deliberate choice and gets no hint.
    """
    count = sum(
        1
        for r in records
        if r.from_library
        and r.row.verdict == "fail"
        and not any(k in r.given for k in X_COEFFICIENTS)
    )
    if count == 0:
        return None
    return (
        f"{count} failing row(s) had no x (time) tolerance: none was given and the "
        "default is 0. If the test may be shifted or delayed in time against the "
        "reference (e.g. at steep edges), consider an x tolerance such as atolx "
        "(time units)"
    )


def _labels(sets: list[ToleranceSet]) -> list[str]:
    labels = [s.label if s.label is not None else f"set{i + 1}" for i, s in enumerate(sets)]
    seen: set[str] = set()
    for label in labels:
        if label in seen:
            raise CompareArgumentError(f"duplicate tolerance set label {label!r}")
        seen.add(label)
    return labels


def _file_info(sf: SignalFile) -> FileInfo:
    t = sf.time[np.isfinite(sf.time)]
    return FileInfo(
        path=str(sf.path),
        time_column=sf.time_column,
        time_column_rule="named time" if sf.time_column_rule == "named time" else "first column",
        row_count=sf.row_count,
        time_start=float(t[0]) if t.shape[0] else None,
        time_end=float(t[-1]) if t.shape[0] else None,
    )


def _span(sf: SignalFile) -> tuple[float, float] | None:
    t = sf.time[np.isfinite(sf.time)]
    if not t.shape[0]:
        return None
    return float(np.min(t)), float(np.max(t))


def _overlap(
    ref_span: tuple[float, float],
    tst_span: tuple[float, float],
    lo: float | None,
    hi: float | None,
) -> tuple[float, float]:
    """The x_range covered by both files (within the requested bounds)."""
    o_lo = max(ref_span[0], tst_span[0])
    o_hi = min(ref_span[1], tst_span[1])
    if lo is not None:
        o_lo = max(o_lo, lo)
    if hi is not None:
        o_hi = min(o_hi, hi)
    return o_lo, o_hi


def _range_json(window: tuple[float, float]) -> str:
    return f'{{"lo": {window[0]!r}, "hi": {window[1]!r}}}'


def _coverage_problems(
    ref_span: tuple[float, float] | None,
    tst_span: tuple[float, float] | None,
    lo: float | None,
    hi: float | None,
) -> dict[int, str]:
    """Problem texts for the library's MISSING_* statuses, keyed by code.

    The library judges coverage on both time extents clipped to x_range, so
    the overlap window below makes the status PASS or FAIL.
    """
    if ref_span is None or tst_span is None:
        return {}
    window = _overlap(ref_span, tst_span, lo, hi)
    if not window[0] < window[1]:
        return {}
    ref_txt = f"reference covers time [{ref_span[0]!r}, {ref_span[1]!r}]"
    tst_txt = f"test covers time [{tst_span[0]!r}, {tst_span[1]!r}]"
    within = "" if lo is None and hi is None else " within the requested x_range"
    fix = f"; x_range {_range_json(window)} compares the overlap"
    return {
        int(funnel.Status.MISSING_REFERENCE): (
            f"test extends beyond the reference{within}: {tst_txt}, {ref_txt}{fix}"
        ),
        int(funnel.Status.MISSING_TEST): (
            f"reference extends beyond the test{within}: {ref_txt}, {tst_txt}{fix}"
        ),
    }


def _column_problem(name: str, ref: SignalFile, tst: SignalFile) -> tuple[int | None, str] | None:
    """Server-detected problem of a column as ``(status code or None, text)``."""
    if name in (ref.time_column, tst.time_column):
        return None, f"{name!r} is the time column"
    in_ref = name in ref.signal_columns
    in_tst = name in tst.signal_columns
    if not in_ref and not in_tst:
        return int(funnel.Status.MISSING_REFERENCE), "column absent from both files"
    if not in_tst:
        return int(funnel.Status.MISSING_TEST), "column absent from the test file"
    if not in_ref:
        return int(funnel.Status.MISSING_REFERENCE), "column absent from the reference file"
    parts = []
    if ref.bad_cells[name]:
        parts.append(f"{ref.bad_cells[name]} in the reference file")
    if tst.bad_cells[name]:
        parts.append(f"{tst.bad_cells[name]} in the test file")
    if parts:
        return None, (
            "non-numeric, empty or non-finite values (" + ", ".join(parts) + "); not compared"
        )
    return None


def _library_row(
    column: str,
    label: str,
    res: funnel.CompareResult,
    s: funnel.ViolationSummary,
    overridden: bool,
    max_intervals: int,
    coverage_problem: str | None,
) -> Row:
    code = int(res.status)
    verdict = _verdict(code)
    row = Row(
        column=column,
        tolerance_set=label,
        verdict=verdict,
        status=code,
        status_name=_status_name(code),
        problem=None if verdict != "error" else funnel.status_message(code),
        tolerances=_coefficients(s.tolerances) if overridden else None,
    )
    if verdict == "error":
        if code in _LIBRARY_MISSING:
            # The library judged every point it could; report the counts and
            # say exactly which x_range compares the overlap.
            row.points_compared = s.points_compared
            row.points_outside = s.points_outside
            if coverage_problem is not None:
                row.problem = coverage_problem
        return row
    row.points_compared = s.points_compared
    if verdict == "pass":
        # Outside counts, fractions and intervals are zero by definition;
        # omitting them keeps results for many columns small.
        return row
    row.points_outside = s.points_outside
    row.fraction_of_points_outside = finite_or_none(s.fraction_of_points_outside)
    row.fraction_of_span_outside = finite_or_none(s.fraction_of_span_outside)
    row.interval_count = len(s.intervals)
    if s.worst is not None:
        row.worst = Worst(
            x=finite_or_none(s.worst.x),
            deviation=finite_or_none(s.worst.deviation),
            tube_half_width_y=finite_or_none(s.worst.tube_half_width_y),
        )
    ordered = sorted(s.intervals, key=lambda iv: abs(iv.worst_deviation), reverse=True)
    row.intervals = [
        Interval(
            start_x=iv.start_x,
            end_x=iv.end_x,
            direction=iv.direction,
            point_count=iv.point_count,
            worst_deviation=iv.worst_deviation,
            worst_x=iv.worst_x,
        )
        for iv in ordered[:max_intervals]
    ]
    return row


def run_compare(
    ref: SignalFile,
    tst: SignalFile,
    *,
    columns: list[str] | None = None,
    tolerances: list[ToleranceSet] | None = None,
    column_tolerances: dict[str, ToleranceSpec] | None = None,
    x_range: XRange | None = None,
    max_intervals: int = DEFAULT_MAX_INTERVALS,
    max_rows: int = DEFAULT_MAX_ROWS,
    limit: TimeLimit | None = None,
) -> CompareOutcome:
    """Compare ``tst`` against ``ref``; see the ``mcp-server`` spec.

    With a ``limit``, comparisons start only while time remains and a
    running one is stopped at the deadline; that comparison and all later
    ones are reported as not completed (rows cover completed comparisons
    only). A cancelled ``limit.cancel`` raises ``funnel.ComparisonCancelled``.
    """
    if max_intervals < 0:
        raise CompareArgumentError("max_intervals must be >= 0")
    if max_rows < 1:
        raise CompareArgumentError("max_rows must be >= 1")
    sets = list(tolerances) if tolerances else [ToleranceSet(label=DEFAULT_SET_LABEL)]
    labels = _labels(sets)
    overrides = dict(column_tolerances or {})
    lo = x_range.lo if x_range is not None else None
    hi = x_range.hi if x_range is not None else None
    if lo is not None and hi is not None and lo > hi:
        raise CompareArgumentError(f"x_range lo ({lo}) is greater than hi ({hi})")

    notes: list[str] = []
    only_ref: list[str] | None = None
    only_tst: list[str] | None = None
    if columns is None:
        selected = [c for c in ref.signal_columns if c in tst.signal_columns]
        only_ref = [c for c in ref.signal_columns if c not in tst.signal_columns]
        only_tst = [c for c in tst.signal_columns if c not in ref.signal_columns]
        if not selected:
            notes.append("the files have no signal column in common; nothing was compared")
    else:
        if not columns:
            raise CompareArgumentError("columns is empty; omit it to compare all common columns")
        union = list(ref.signal_columns) + [
            c for c in tst.signal_columns if c not in ref.signal_columns
        ]
        selected, unmatched = expand(columns, union)
        for entry in unmatched:
            if is_pattern(entry):
                notes.append(f"columns pattern {entry!r} matched no signal column")

    for name in overrides:
        if name not in selected:
            notes.append(f"override for column {name!r} ignored: column not compared")
    for label, sf in (("reference", ref), ("test", tst)):
        for p in sf.time_problems():
            notes.append(f"{label} file: {p}")

    problems = {c: _column_problem(c, ref, tst) for c in selected}
    valid = [c for c in selected if problems[c] is None]
    t_ref = np.asarray(ref.time, dtype=np.float64)
    t_tst = np.asarray(tst.time, dtype=np.float64)
    ref_span, tst_span = _span(ref), _span(tst)
    coverage = _coverage_problems(ref_span, tst_span, lo, hi)

    set_out: list[ToleranceSetOut] = []
    records: list[RowRecord] = []
    not_completed: list[tuple[str, str]] = []
    stopped = False
    for spec, label in zip(sets, labels, strict=True):
        base = spec.given()
        set_out.append(
            ToleranceSetOut(label=label, given=base, resolved=resolve_with_library(base))
        )
        default_opts = make_options(base, lo, hi)
        per_col_given = {c: compose_override(base, overrides.get(c)) for c in valid}
        per_col_opts = {c: make_options(per_col_given[c], lo, hi) for c in valid if c in overrides}
        for c in selected:
            problem = problems[c]
            if problem is not None:
                code, text = problem
                records.append(
                    RowRecord(
                        row=Row(
                            column=c,
                            tolerance_set=label,
                            verdict="error",
                            status=code,
                            status_name=None if code is None else _status_name(code),
                            problem=text,
                        ),
                        given=compose_override(base, overrides.get(c)),
                        from_library=False,
                    )
                )
                continue
            if stopped:
                not_completed.append((c, label))
                continue
            opts = per_col_opts.get(c, default_opts)
            try:
                res = funnel.compare(
                    t_ref,
                    np.asarray(ref.values[c], dtype=np.float64),
                    t_tst,
                    np.asarray(tst.values[c], dtype=np.float64),
                    opts,
                    timeout=None if limit is None else limit.remaining(),
                    cancel=None if limit is None else limit.cancel,
                )
            except funnel.ComparisonTimeout:
                stopped = True
                not_completed.append((c, label))
                continue
            code = int(res.status)
            summary = funnel.summarize(res, t_ref, opts)
            row = _library_row(
                c, label, res, summary, c in overrides, max_intervals,
                coverage.get(code),
            )
            records.append(
                RowRecord(
                    row=row,
                    given=per_col_given[c],
                    from_library=True,
                    library=(res, summary),
                )
            )

    if ref_span is not None and tst_span is not None:
        spans = (
            f"reference time spans [{ref_span[0]!r}, {ref_span[1]!r}], "
            f"test time spans [{tst_span[0]!r}, {tst_span[1]!r}]"
        )
        if ref_span[1] < tst_span[0] or tst_span[1] < ref_span[0]:
            notes.append(f"time ranges do not overlap: {spans}")
        elif any(r.row.status in _LIBRARY_MISSING for r in records if r.from_library):
            window = _overlap(ref_span, tst_span, lo, hi)
            notes.append(
                f"time ranges differ ({spans}); pass x_range {_range_json(window)} "
                "to compare only the overlap"
            )

    hint = no_x_tolerance_hint(records)
    if hint is not None:
        notes.append(hint)

    pending_out: list[NotCompleted] | None = None
    pending_omitted: int | None = None
    if not_completed:
        assert limit is not None
        total = len(records) + len(not_completed)
        notes.append(
            f"time limit of {limit.describe()} reached: {len(not_completed)} of {total} "
            "comparisons not completed (listed in not_completed); pass a larger time_limit, "
            "fewer columns or a narrower x_range"
        )
        pending_out = [
            NotCompleted(column=c, tolerance_set=label) for c, label in not_completed[:max_rows]
        ]
        pending_omitted = max(0, len(not_completed) - max_rows) or None

    totals = Totals(
        rows=len(records),
        passed=sum(r.row.verdict == "pass" for r in records),
        failed=sum(r.row.verdict == "fail" for r in records),
        errors=sum(r.row.verdict == "error" for r in records),
        not_completed=len(not_completed) or None,
    )
    ordered = sorted(records, key=lambda r: _VERDICT_ORDER[r.row.verdict])
    shown = ordered[:max_rows]

    def capped(names: list[str] | None) -> tuple[list[str] | None, int | None]:
        if not names:
            return None, None
        return names[:MAX_LISTED_COLUMNS], len(names)

    only_ref_list, only_ref_count = capped(only_ref)
    only_tst_list, only_tst_count = capped(only_tst)
    result = CompareResult(
        reference=_file_info(ref),
        test=_file_info(tst),
        x_range=RangeOut(lo=lo, hi=hi),
        tolerance_sets=set_out,
        totals=totals,
        rows=[r.row for r in shown],
        rows_omitted=len(ordered) - len(shown),
        columns_only_in_reference=only_ref_list,
        columns_only_in_reference_count=only_ref_count,
        columns_only_in_test=only_tst_list,
        columns_only_in_test_count=only_tst_count,
        time_limit_reached=True if not_completed else None,
        not_completed=pending_out,
        not_completed_omitted=pending_omitted,
        notes=notes,
    )
    return CompareOutcome(
        result=result, records=ordered, x_range=(lo, hi), not_completed=not_completed
    )
