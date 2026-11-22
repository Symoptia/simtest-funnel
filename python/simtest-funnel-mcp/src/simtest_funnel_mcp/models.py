"""Pydantic models: tool inputs and the published output schemas.

Optional output fields are omitted from the structured content when absent
(``model_dump(exclude_none=True)``) to keep results small.
"""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from simtest_funnel_mcp.arguments import StrictInput
from simtest_funnel_mcp.reader import ISO_DATETIME

COEFFICIENTS: tuple[str, ...] = ("atolx", "atoly", "ltolx", "ltoly", "rtolx", "rtoly")
X_COEFFICIENTS: tuple[str, ...] = ("atolx", "ltolx", "rtolx")
Y_COEFFICIENTS: tuple[str, ...] = ("atoly", "ltoly", "rtoly")

_NONNEG = "Must be >= 0. Omit for 'not given'."


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


class ToleranceSpec(StrictInput):
    """Any subset of the six tolerance coefficients (omitted = not given)."""

    # allow_inf_nan=False: pydantic would otherwise accept "inf"/"nan" strings.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    atolx: float | None = Field(
        default=None, ge=0, description=f"Absolute tolerance in x (time units; seconds on a date-time axis). {_NONNEG}"
    )
    atoly: float | None = Field(
        default=None, ge=0, description=f"Absolute tolerance in y (signal units). {_NONNEG}"
    )
    ltolx: float | None = Field(
        default=None, ge=0, description=(
            f"Tolerance in x relative to |t| at each sample (refused on a date-time axis). "
            f"{_NONNEG}"
        ),
    )
    ltoly: float | None = Field(
        default=None,
        ge=0,
        description=f"Tolerance in y relative to |y_ref| at each sample. {_NONNEG}",
    )
    rtolx: float | None = Field(
        default=None,
        ge=0,
        description=f"Tolerance in x relative to the reference time span. {_NONNEG}",
    )
    rtoly: float | None = Field(
        default=None,
        ge=0,
        description=f"Tolerance in y relative to the reference value range (max - min). {_NONNEG}",
    )

    def given(self) -> dict[str, float]:
        """The coefficients that were given."""
        out: dict[str, float] = {}
        for name in COEFFICIENTS:
            value = getattr(self, name)
            if value is not None:
                out[name] = float(value)
        return out


class ToleranceSet(ToleranceSpec):
    """A labelled tolerance set."""

    label: str | None = Field(
        default=None,
        min_length=1,
        description="Unique label echoed in every row (default: set1, set2, ...).",
    )


_BOUND = (
    "time bound: a finite number (on a date-time axis: seconds since 1970-01-01 UTC) or, "
    "on a date-time axis only, an ISO 8601 date-time string such as '2026-11-05T00:00' "
    "(with 'Z' or an offset exactly when the time columns have one); omit for unbounded."
)


class XRange(StrictInput):
    """Time window to compare (inclusive); omitted bound = unbounded."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    lo: float | str | None = Field(default=None, description=f"Lower {_BOUND}")
    hi: float | str | None = Field(default=None, description=f"Upper {_BOUND}")

    @field_validator("lo", "hi")
    @classmethod
    def _iso_or_number(cls, v: float | str | None) -> float | str | None:
        """Strings must be ISO 8601 date-times; numeric strings are read as
        numbers as before (so ``"-inf"`` stays a validation error)."""
        if not isinstance(v, str):
            return v
        if re.fullmatch(ISO_DATETIME, v.strip()):
            return v.strip()
        try:
            number = float(v)
        except ValueError:
            raise ValueError(
                f"{v!r} is neither a number nor an ISO 8601 date-time "
                "(YYYY-MM-DD[Thh:mm[:ss[.f]][Z|+hh:mm]])"
            ) from None
        if not math.isfinite(number):
            raise ValueError("bound must be finite")
        return number


class ColumnPair(StrictInput):
    """A reference column compared against a differently named test column."""

    reference: str = Field(min_length=1, description="Exact reference column name.")
    test: str = Field(min_length=1, description="Exact test column name.")
    label: str | None = Field(
        default=None,
        min_length=1,
        description="Row key (default: the test column); used by column_tolerances.",
    )

    @property
    def key(self) -> str:
        return self.label if self.label is not None else self.test


class TimeTolerance(BaseModel):
    """Resolved x half-width on a date-time axis."""

    seconds: float
    duration: str = Field(description="ISO 8601 duration, e.g. PT3H.")


# --------------------------------------------------------------------------
# describe_signals output
# --------------------------------------------------------------------------


class Sampling(BaseModel):
    uniform: bool
    min_step: float | None = None
    median_step: float | None = None
    max_step: float | None = None
    median_step_duration: str | None = Field(
        default=None, description="Date-time axes: median step as ISO 8601 duration."
    )


class TimeInfo(BaseModel):
    kind: Literal["numeric", "datetime"] = Field(
        default="numeric",
        description="numeric, or datetime (ISO 8601 cells read as seconds since the epoch).",
    )
    time_zone: Literal["offset", "none", "mixed"] | None = Field(
        default=None,
        description="Date-time axes: cells carry offsets, none (read as UTC), or mixed.",
    )
    start: float | None = None
    start_iso: str | None = None
    end: float | None = None
    end_iso: str | None = None
    span: float | None = None
    span_duration: str | None = None
    sampling: Sampling


class ColumnInfo(BaseModel):
    name: str
    min: float | None = None
    max: float | None = None
    range: float | None = None
    bad_values: int | None = Field(
        default=None, description="Number of non-numeric, empty or non-finite cells."
    )


class SourceInfo(BaseModel):
    """Where an input given as a URL came from (absent for local files)."""

    url: str = Field(description="The URL as given (normalised).")
    final_url: str | None = Field(default=None, description="The URL after redirects.")
    fetched_at: str = Field(description="When it was fetched (UTC, ISO 8601).")
    size: int = Field(description="Bytes of content read (after decompression).")
    sha256: str = Field(description="SHA-256 of the content read (hex).")
    content_type: str | None = None
    reused: bool = Field(
        description="True when this call used the copy cached by an earlier call of this "
        "server process; false for the call that fetched it."
    )


class DescribeResult(BaseModel):
    path: str = Field(description="Resolved local path, or the URL for a URL input.")
    source: SourceInfo | None = Field(default=None, description="URL inputs only.")
    header_line: int = Field(default=1, description="Physical line of the header used.")
    time_column: str
    time_column_rule: Literal["named time", "first column"]
    row_count: int
    time: TimeInfo
    columns: list[ColumnInfo]
    columns_total: int = Field(description="Signal columns in the file.")
    columns_selected: int = Field(
        description="Signal columns matching the 'columns' filter (all when no filter)."
    )
    columns_omitted: int = Field(
        default=0, description="Selected columns not listed because of max_columns."
    )
    problems: list[str] = Field(default_factory=list)
    problems_omitted: int = Field(
        default=0, description="Problems not listed because of max_columns."
    )
    notes: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# compare_signals output
# --------------------------------------------------------------------------


class Coefficients(BaseModel):
    """The six resolved coefficients."""

    atolx: float
    atoly: float
    ltolx: float
    ltoly: float
    rtolx: float
    rtoly: float


class FileInfo(BaseModel):
    path: str = Field(description="Resolved local path, or the URL for a URL input.")
    source: SourceInfo | None = Field(default=None, description="URL inputs only.")
    header_line: int | None = Field(default=None, description="Physical line of the header used.")
    time_column: str
    time_column_rule: Literal["named time", "first column"]
    time_kind: Literal["numeric", "datetime"] | None = None
    time_zone: Literal["offset", "none", "mixed"] | None = None
    row_count: int
    time_start: float | None = None
    time_start_iso: str | None = None
    time_end: float | None = None
    time_end_iso: str | None = None


class RangeOut(BaseModel):
    lo: float | None = None
    lo_iso: str | None = None
    hi: float | None = None
    hi_iso: str | None = None


class ToleranceSetOut(BaseModel):
    label: str
    given: dict[str, float]
    resolved: Coefficients
    time_tolerance: TimeTolerance | None = Field(
        default=None,
        description="Date-time axes: the non-zero x half-width in seconds and as a duration.",
    )


class Totals(BaseModel):
    """Verdict counts over all rows (including omitted ones)."""

    rows: int
    passed: int
    failed: int
    errors: int
    not_completed: int | None = Field(
        default=None,
        description=(
            "Comparisons stopped by the time limit (no row); absent when all completed."
        ),
    )


class NotCompleted(BaseModel):
    """A (column, tolerance set) comparison stopped by the time limit."""

    column: str
    tolerance_set: str
    reference_column: str | None = None
    test_column: str | None = None


#: Shared wording of the deviation and difference fields.
DEVIATION_HELP = (
    "Distance of the test point OUTSIDE the tube (not test minus reference): test minus "
    "the upper edge if above (positive), test minus the lower edge if below (negative)."
)
DIFFERENCE_HELP = (
    "Test value minus the reference value at the same x (reference linearly "
    "interpolated; at a repeated reference time its first value)."
)


class Worst(BaseModel):
    """The judged test point farthest outside the tube."""

    x: float | None = Field(default=None, description="x (time) of the worst point.")
    x_iso: str | None = None
    deviation: float | None = Field(default=None, description=DEVIATION_HELP)
    difference: float | None = Field(default=None, description=DIFFERENCE_HELP)
    tube_half_width_y: float | None = Field(
        default=None,
        description=(
            "Vertical half-width of the tube at x (half the distance between its edges): "
            "wider than the y tolerance where an x tolerance widens the tube."
        ),
    )


class Interval(BaseModel):
    """A run of consecutive judged test points outside the tube on one side."""

    start_x: float
    start_x_iso: str | None = None
    end_x: float
    end_x_iso: str | None = None
    direction: Literal["above", "below"]
    point_count: int
    worst_deviation: float = Field(
        description="Deviation (see worst.deviation) with the largest magnitude in the run."
    )
    worst_x: float = Field(description="x of the worst point of the run.")
    worst_x_iso: str | None = None
    worst_difference: float | None = Field(
        default=None, description=f"At worst_x: {DIFFERENCE_HELP}"
    )


class Row(BaseModel):
    column: str = Field(
        description="Row key: the column name, or for a pair its label (else its test column)."
    )
    reference_column: str | None = Field(default=None, description="Pair rows only.")
    test_column: str | None = Field(default=None, description="Pair rows only.")
    tolerance_set: str
    verdict: Literal["pass", "fail", "error"]
    status: int | None = None
    status_name: str | None = None
    problem: str | None = None
    tolerances: Coefficients | None = Field(
        default=None, description="Resolved values; present only when a column override applied."
    )
    time_tolerance: TimeTolerance | None = Field(
        default=None,
        description="Date-time axes: x half-width when an override changed the x axis.",
    )
    points_compared: int | None = None
    points_outside: int | None = None
    fraction_of_points_outside: float | None = None
    fraction_of_span_outside: float | None = None
    worst: Worst | None = None
    interval_count: int | None = None
    intervals: list[Interval] | None = None


class CompareResult(BaseModel):
    reference: FileInfo
    test: FileInfo
    x_range: RangeOut
    tolerance_sets: list[ToleranceSetOut]
    totals: Totals
    rows: list[Row]
    rows_omitted: int = 0
    columns_only_in_reference: list[str] | None = None
    columns_only_in_reference_count: int | None = None
    columns_only_in_test: list[str] | None = None
    columns_only_in_test_count: int | None = None
    time_limit_reached: bool | None = Field(
        default=None,
        description="True when the time limit stopped the call; rows cover completed "
        "comparisons only. Absent when every comparison completed.",
    )
    not_completed: list[NotCompleted] | None = Field(
        default=None,
        description="Comparisons not completed within the time limit (capped by max_rows).",
    )
    not_completed_omitted: int | None = None
    notes: list[str] = Field(default_factory=list)
    snippet: str | None = None


# --------------------------------------------------------------------------
# plot_signals output
# --------------------------------------------------------------------------


class PlotFile(BaseModel):
    """The plot file written to ``output_path``."""

    path: str
    format: Literal["svg", "png"]
    bytes: int
    width_px: int | None = Field(default=None, description="PNG only.")
    height_px: int | None = Field(default=None, description="PNG only.")


class PlotPreview(BaseModel):
    """The inline PNG preview (sent as MCP image content)."""

    format: Literal["png"] = "png"
    width_px: int
    height_px: int
    bytes: int


class DrawnPoints(BaseModel):
    """How many points were drawn per series (the comparison used all samples)."""

    reference: int
    test: int
    tube_lower: int = Field(description="Points drawn for the tube's lower bound (reduced).")
    tube_upper: int = Field(description="Points drawn for the tube's upper bound (reduced).")
    violation_markers: int
    violation_regions: int
    buckets: int = Field(
        description="Min/max buckets used to reduce reference, test and tube bounds."
    )


class PlotResult(BaseModel):
    reference: FileInfo
    test: FileInfo
    x_range: RangeOut
    tolerance_set: ToleranceSetOut
    row: Row = Field(description="Same fields as a compare_signals row.")
    view: RangeOut = Field(description="Time window shown on the x axis.")
    file: PlotFile | None = Field(default=None, description="Absent when no output_path.")
    preview: PlotPreview
    drawn: DrawnPoints
    notes: list[str] = Field(default_factory=list)
