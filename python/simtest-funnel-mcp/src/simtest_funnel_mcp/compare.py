"""``compare_signals``: funnel comparison of CSV columns via ``simtest.funnel``.

All numerics (comparison, tolerance resolution, violation intervals) come
from the library; this module only selects columns, shapes options and
results, and bounds the output size.
"""

from __future__ import annotations

import difflib
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
    ColumnPair,
    CompareResult,
    FileInfo,
    Interval,
    NotCompleted,
    RangeOut,
    Row,
    ToleranceSet,
    ToleranceSetOut,
    TimeTolerance,
    ToleranceSpec,
    Totals,
    Worst,
    XRange,
)
from simtest_funnel_mcp.selection import expand, is_pattern
from simtest_funnel_mcp.timeaxis import format_duration, format_iso, parse_iso_bound

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
    #: Columns compared (``None``: the row key on both sides).
    reference_column: str | None = None
    test_column: str | None = None

    @property
    def columns(self) -> tuple[str, str]:
        """``(reference column, test column)`` of the row."""
        key = self.row.column
        return (self.reference_column or key, self.test_column or key)


@dataclass(frozen=True)
class Entry:
    """One compared column: row key, reference column, test column."""

    key: str
    reference: str
    test: str
    #: True for an explicit pair (rows then carry both column names).
    pair: bool = False


@dataclass
class CompareOutcome:
    result: CompareResult
    #: Completed comparisons only (rows), in result order.
    records: list[RowRecord] = field(default_factory=list)
    x_range: tuple[float | None, float | None] = (None, None)
    #: (row key, tolerance set) pairs stopped by the time limit, in order.
    not_completed: list[tuple[str, str]] = field(default_factory=list)
    #: Whether the time axis is a date-time axis, and its zone kind.
    datetime_axis: bool = False
    time_zone: str | None = None


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


def no_x_tolerance_hint(records: list[RowRecord], datetime_axis: bool = False) -> str | None:
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
        + ("(seconds on this date-time axis, e.g. atolx = 10800 for 3 h)" if datetime_axis
           else "(time units)")
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
    info = FileInfo(
        path=sf.name,
        header_line=sf.header_line,
        time_column=sf.time_column,
        time_column_rule="named time" if sf.time_column_rule == "named time" else "first column",
        time_kind=sf.time_kind,
        row_count=sf.row_count,
        time_start=float(t[0]) if t.shape[0] else None,
        time_end=float(t[-1]) if t.shape[0] else None,
    )
    if sf.is_datetime:
        info.time_zone = sf.time_zone
        info.time_start_iso = format_iso(info.time_start, sf.time_zone)
        info.time_end_iso = format_iso(info.time_end, sf.time_zone)
    return info


def _axis_kind(sf: SignalFile) -> str:
    if not sf.is_datetime:
        return "numeric"
    if sf.time_zone == "offset":
        return "ISO 8601 date-times with time zone offsets"
    if sf.time_zone == "none":
        return "ISO 8601 date-times without time zone (read as UTC)"
    return "ISO 8601 date-times, some with and some without time zone"


def check_time_axes(ref: SignalFile, tst: SignalFile) -> None:
    """Fail the call when the two time axes cannot be compared."""
    zones = {ref.time_zone, tst.time_zone}
    if ref.time_kind == tst.time_kind and not (ref.is_datetime and zones == {"offset", "none"}):
        return
    if ref.time_kind != tst.time_kind:
        fix = (
            "write both time columns the same way: both as numbers (e.g. seconds since "
            "1970-01-01 UTC) or both as ISO 8601 date-times"
        )
    else:
        fix = (
            "one time column has a time zone and the other has none; write both with "
            "offsets (e.g. 'Z' for UTC), or both without"
        )
    hints = "".join(f" {h}" for sf in (ref, tst) for h in sf.hints)
    raise CompareArgumentError(
        f"the time axes do not match: reference {ref.name} time column "
        f"{ref.time_column!r} is {_axis_kind(ref)}, test {tst.name} time column "
        f"{tst.time_column!r} is {_axis_kind(tst)}; {fix}.{hints}"
    )


def resolve_bounds(
    x_range: XRange | None, ref: SignalFile
) -> tuple[float | None, float | None]:
    """x-range bounds as numbers; ISO strings only on a date-time axis, with
    a time zone exactly when the axis has one."""
    if x_range is None:
        return None, None
    out: list[float | None] = []
    for name, v in (("lo", x_range.lo), ("hi", x_range.hi)):
        if not isinstance(v, str):
            out.append(None if v is None else float(v))
            continue
        if not ref.is_datetime:
            raise CompareArgumentError(
                f"x_range {name} {v!r} is a date-time, but the time columns are numeric; "
                "give a number"
            )
        try:
            value, zoned = parse_iso_bound(v)
        except ValueError as exc:
            raise CompareArgumentError(f"x_range {name}: {exc}") from exc
        if ref.time_zone == "offset" and not zoned:
            raise CompareArgumentError(
                f"x_range {name} {v!r} has no time zone, but the time columns have offsets; "
                "add 'Z' or an offset, e.g. '2026-11-05T00:00Z'"
            )
        if ref.time_zone == "none" and zoned:
            raise CompareArgumentError(
                f"x_range {name} {v!r} has a time zone, but the time columns have none "
                "(read as UTC); drop the 'Z' or offset"
            )
        out.append(value)
    return out[0], out[1]


def check_ltolx(
    datetime_axis: bool,
    sets: list[ToleranceSet],
    labels: list[str],
    overrides: dict[str, ToleranceSpec],
) -> None:
    """Refuse a non-zero ltolx on a date-time axis."""
    if not datetime_axis:
        return
    where = [
        (f"tolerance set {label!r}", spec.ltolx)
        for spec, label in zip(sets, labels, strict=True)
    ] + [(f"column_tolerances[{k!r}]", spec.ltolx) for k, spec in overrides.items()]
    for name, ltolx in where:
        if ltolx:
            raise CompareArgumentError(
                f"ltolx = {ltolx:g} in {name}: on a date-time axis times are seconds since "
                "1970-01-01 (about 1.8e9), and ltolx scales with that absolute time, so it "
                "is meaningless. Give atolx in seconds instead (e.g. atolx = 10800 for "
                "plus or minus 3 hours); ltolx = 0 is accepted"
            )


def time_tolerance(c: Coefficients, ref_span: float | None) -> TimeTolerance | None:
    """The resolved x half-width ``max(atolx, rtolx * span)`` if non-zero."""
    seconds = max(c.atolx, c.rtolx * (ref_span or 0.0))
    if not seconds > 0:
        return None
    duration = format_duration(seconds)
    assert duration is not None
    return TimeTolerance(seconds=seconds, duration=duration)


def _reference_span(sf: SignalFile, lo: float | None, hi: float | None) -> float | None:
    """max - min of the reference time within ``[lo, hi]``."""
    t = sf.time[np.isfinite(sf.time)]
    if lo is not None:
        t = t[t >= lo]
    if hi is not None:
        t = t[t <= hi]
    return float(np.max(t) - np.min(t)) if t.shape[0] else None


def add_iso(row: Row, zone: str | None) -> None:
    """Fill the ISO siblings of a row's times (date-time axes)."""
    if row.worst is not None:
        row.worst.x_iso = format_iso(row.worst.x, zone)
    for iv in row.intervals or []:
        iv.start_x_iso = format_iso(iv.start_x, zone)
        iv.end_x_iso = format_iso(iv.end_x, zone)
        iv.worst_x_iso = format_iso(iv.worst_x, zone)


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


def _times(span: tuple[float, float], zone: str | None, datetime_axis: bool) -> str:
    """``[a, b]``, plus the ISO form on a date-time axis."""
    text = f"[{span[0]!r}, {span[1]!r}]"
    if datetime_axis:
        text += f" ({format_iso(span[0], zone)} .. {format_iso(span[1], zone)})"
    return text


def _coverage_problems(
    ref_span: tuple[float, float] | None,
    tst_span: tuple[float, float] | None,
    lo: float | None,
    hi: float | None,
    zone: str | None = None,
    datetime_axis: bool = False,
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
    ref_txt = f"reference covers time {_times(ref_span, zone, datetime_axis)}"
    tst_txt = f"test covers time {_times(tst_span, zone, datetime_axis)}"
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


def _missing(name: str, side: str, sf: SignalFile) -> str:
    text = f"column {name!r} absent from the {side} file"
    close = difflib.get_close_matches(name, list(sf.signal_columns), n=3)
    if close:
        text += "; did you mean " + " or ".join(repr(c) for c in close) + "?"
    if is_pattern(name):
        text += "; pairs take exact names, use columns for patterns"
    return text


def _pair_problem(e: Entry, ref: SignalFile, tst: SignalFile) -> tuple[int | None, str] | None:
    """Server-detected problem of a column pair (as :func:`_column_problem`)."""
    if e.reference == ref.time_column:
        return None, f"{e.reference!r} is the time column of the reference file"
    if e.test == tst.time_column:
        return None, f"{e.test!r} is the time column of the test file"
    in_ref = e.reference in ref.signal_columns
    in_tst = e.test in tst.signal_columns
    if not in_ref and not in_tst:
        return int(funnel.Status.MISSING_REFERENCE), (
            _missing(e.reference, "reference", ref) + "; " + _missing(e.test, "test", tst)
        )
    if not in_tst:
        return int(funnel.Status.MISSING_TEST), _missing(e.test, "test", tst)
    if not in_ref:
        return int(funnel.Status.MISSING_REFERENCE), _missing(e.reference, "reference", ref)
    parts = []
    if ref.bad_cells[e.reference]:
        parts.append(f"{ref.bad_cells[e.reference]} in the reference column")
    if tst.bad_cells[e.test]:
        parts.append(f"{tst.bad_cells[e.test]} in the test column")
    if parts:
        return None, (
            "non-numeric, empty or non-finite values (" + ", ".join(parts) + "); not compared"
        )
    return None


def _pair_entries(pairs: list[ColumnPair]) -> list[Entry]:
    """Entries of explicit pairs; row keys must be unique."""
    entries = [Entry(p.key, p.reference, p.test, pair=True) for p in pairs]
    seen: set[str] = set()
    for e in entries:
        if e.key in seen:
            raise CompareArgumentError(
                f"pairs: row key {e.key!r} is used by more than one pair (a pair's key is "
                "its label, else its test column); give the pairs distinct labels"
            )
        seen.add(e.key)
    return entries


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
    pairs: list[ColumnPair] | None = None,
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
    if pairs is not None and columns is not None:
        raise CompareArgumentError(
            "pairs and columns cannot be combined: use columns for same-name columns "
            "(names or patterns), pairs for differently named reference/test columns"
        )
    if pairs is not None and not pairs:
        raise CompareArgumentError("pairs is empty; omit it or give at least one pair")
    sets = list(tolerances) if tolerances else [ToleranceSet(label=DEFAULT_SET_LABEL)]
    labels = _labels(sets)
    overrides = dict(column_tolerances or {})
    check_time_axes(ref, tst)
    dt_axis = ref.is_datetime
    zone = ref.time_zone if dt_axis else None
    check_ltolx(dt_axis, sets, labels, overrides)
    lo, hi = resolve_bounds(x_range, ref)
    if lo is not None and hi is not None and lo > hi:
        raise CompareArgumentError(f"x_range lo ({lo}) is greater than hi ({hi})")

    notes: list[str] = []
    only_ref: list[str] | None = None
    only_tst: list[str] | None = None
    entries: list[Entry]
    if pairs is not None:
        entries = _pair_entries(pairs)
    elif columns is None:
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
    if pairs is None:
        entries = [Entry(c, c, c) for c in selected]

    keys = [e.key for e in entries]
    for name in overrides:
        if name not in keys:
            notes.append(f"override for column {name!r} ignored: column not compared")
    for label, sf in (("reference", ref), ("test", tst)):
        if label == "test" and tst is ref:
            continue
        for h in sf.hints:
            notes.append(f"{label} file: {h}")
        for p in sf.time_problems():
            notes.append(f"{label} file: {p}")

    problems = {
        e.key: _pair_problem(e, ref, tst) if e.pair else _column_problem(e.key, ref, tst)
        for e in entries
    }
    mixed = [name for name, sf in (("reference", ref), ("test", tst)) if sf.time_zone == "mixed"]
    if mixed:
        text = (
            f"time column of the {' and '.join(mixed)} file mixes timestamps with and "
            "without a time zone; not compared"
        )
        problems = {k: v if v is not None else (None, text) for k, v in problems.items()}
    valid = [e.key for e in entries if problems[e.key] is None]
    t_ref = np.asarray(ref.time, dtype=np.float64)
    t_tst = np.asarray(tst.time, dtype=np.float64)
    ref_span, tst_span = _span(ref), _span(tst)
    coverage = _coverage_problems(ref_span, tst_span, lo, hi, zone, dt_axis)
    x_span = _reference_span(ref, lo, hi) if dt_axis else None

    set_out: list[ToleranceSetOut] = []
    records: list[RowRecord] = []
    not_completed: list[tuple[str, str]] = []
    pending: list[tuple[Entry, str]] = []
    stopped = False
    for spec, label in zip(sets, labels, strict=True):
        base = spec.given()
        resolved = resolve_with_library(base)
        set_out.append(
            ToleranceSetOut(
                label=label, given=base, resolved=resolved,
                time_tolerance=time_tolerance(resolved, x_span) if dt_axis else None,
            )
        )
        default_opts = make_options(base, lo, hi)
        per_col_given = {c: compose_override(base, overrides.get(c)) for c in valid}
        per_col_opts = {c: make_options(per_col_given[c], lo, hi) for c in valid if c in overrides}
        for e in entries:
            c = e.key
            pair_cols = (e.reference, e.test) if e.pair else (None, None)
            problem = problems[c]
            if problem is not None:
                code, text = problem
                records.append(
                    RowRecord(
                        row=Row(
                            column=c,
                            reference_column=pair_cols[0],
                            test_column=pair_cols[1],
                            tolerance_set=label,
                            verdict="error",
                            status=code,
                            status_name=None if code is None else _status_name(code),
                            problem=text,
                        ),
                        given=compose_override(base, overrides.get(c)),
                        from_library=False,
                        reference_column=e.reference,
                        test_column=e.test,
                    )
                )
                continue
            if stopped:
                not_completed.append((c, label))
                pending.append((e, label))
                continue
            opts = per_col_opts.get(c, default_opts)
            try:
                res = funnel.compare(
                    t_ref,
                    np.asarray(ref.values[e.reference], dtype=np.float64),
                    t_tst,
                    np.asarray(tst.values[e.test], dtype=np.float64),
                    opts,
                    timeout=None if limit is None else limit.remaining(),
                    cancel=None if limit is None else limit.cancel,
                )
            except funnel.ComparisonTimeout:
                stopped = True
                not_completed.append((c, label))
                pending.append((e, label))
                continue
            code = int(res.status)
            summary = funnel.summarize(res, t_ref, opts)
            row = _library_row(
                c, label, res, summary, c in overrides, max_intervals,
                coverage.get(code),
            )
            row.reference_column, row.test_column = pair_cols
            if dt_axis:
                add_iso(row, zone)
                override = overrides.get(c)
                if override is not None and any(k in override.given() for k in X_COEFFICIENTS):
                    row.time_tolerance = time_tolerance(_coefficients(summary.tolerances), x_span)
            records.append(
                RowRecord(
                    row=row,
                    given=per_col_given[c],
                    from_library=True,
                    library=(res, summary),
                    reference_column=e.reference,
                    test_column=e.test,
                )
            )

    if ref_span is not None and tst_span is not None:
        spans = (
            f"reference time spans {_times(ref_span, zone, dt_axis)}, "
            f"test time spans {_times(tst_span, zone, dt_axis)}"
        )
        if ref_span[1] < tst_span[0] or tst_span[1] < ref_span[0]:
            notes.append(f"time ranges do not overlap: {spans}")
        elif any(r.row.status in _LIBRARY_MISSING for r in records if r.from_library):
            window = _overlap(ref_span, tst_span, lo, hi)
            notes.append(
                f"time ranges differ ({spans}); pass x_range {_range_json(window)} "
                "to compare only the overlap"
            )

    hint = no_x_tolerance_hint(records, dt_axis)
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
            NotCompleted(
                column=e.key,
                tolerance_set=label,
                reference_column=e.reference if e.pair else None,
                test_column=e.test if e.pair else None,
            )
            for e, label in pending[:max_rows]
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
        x_range=RangeOut(
            lo=lo,
            hi=hi,
            lo_iso=format_iso(lo, zone) if dt_axis else None,
            hi_iso=format_iso(hi, zone) if dt_axis else None,
        ),
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
        result=result,
        records=ordered,
        x_range=(lo, hi),
        not_completed=not_completed,
        datetime_axis=dt_axis,
        time_zone=zone,
    )
