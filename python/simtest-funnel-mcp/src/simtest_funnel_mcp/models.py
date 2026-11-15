"""Pydantic models: tool inputs and the published output schemas.

Optional output fields are omitted from the structured content when absent
(``model_dump(exclude_none=True)``) to keep results small.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

COEFFICIENTS: tuple[str, ...] = ("atolx", "atoly", "ltolx", "ltoly", "rtolx", "rtoly")
X_COEFFICIENTS: tuple[str, ...] = ("atolx", "ltolx", "rtolx")
Y_COEFFICIENTS: tuple[str, ...] = ("atoly", "ltoly", "rtoly")

_NONNEG = "Must be >= 0. Omit for 'not given'."


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


class ToleranceSpec(BaseModel):
    """Any subset of the six tolerance coefficients (omitted = not given)."""

    model_config = ConfigDict(extra="forbid")

    atolx: float | None = Field(
        default=None, ge=0, description=f"Absolute tolerance in x (time units). {_NONNEG}"
    )
    atoly: float | None = Field(
        default=None, ge=0, description=f"Absolute tolerance in y (signal units). {_NONNEG}"
    )
    ltolx: float | None = Field(
        default=None, ge=0, description=f"Tolerance in x relative to |t| at each sample. {_NONNEG}"
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


class XRange(BaseModel):
    """Time window to compare (inclusive); omitted bound = unbounded."""

    model_config = ConfigDict(extra="forbid")

    lo: float | None = Field(default=None, description="Lower time bound.")
    hi: float | None = Field(default=None, description="Upper time bound.")


# --------------------------------------------------------------------------
# describe_signals output
# --------------------------------------------------------------------------


class Sampling(BaseModel):
    uniform: bool
    min_step: float | None = None
    median_step: float | None = None
    max_step: float | None = None


class TimeInfo(BaseModel):
    start: float | None = None
    end: float | None = None
    span: float | None = None
    sampling: Sampling


class ColumnInfo(BaseModel):
    name: str
    min: float | None = None
    max: float | None = None
    range: float | None = None
    bad_values: int | None = Field(
        default=None, description="Number of non-numeric, empty or non-finite cells."
    )


class DescribeResult(BaseModel):
    path: str
    time_column: str
    time_column_rule: Literal["named time", "first column"]
    row_count: int
    time: TimeInfo
    columns: list[ColumnInfo]
    problems: list[str] = Field(default_factory=list)


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
    path: str
    time_column: str
    time_column_rule: Literal["named time", "first column"]
    row_count: int
    time_start: float | None = None
    time_end: float | None = None


class RangeOut(BaseModel):
    lo: float | None = None
    hi: float | None = None


class ToleranceSetOut(BaseModel):
    label: str
    given: dict[str, float]
    resolved: Coefficients


class Totals(BaseModel):
    """Verdict counts over all rows (including omitted ones)."""

    rows: int
    passed: int
    failed: int
    errors: int


class Worst(BaseModel):
    x: float | None = None
    deviation: float | None = None
    tube_half_width_y: float | None = None


class Interval(BaseModel):
    start_x: float
    end_x: float
    direction: Literal["above", "below"]
    point_count: int
    worst_deviation: float
    worst_x: float


class Row(BaseModel):
    column: str
    tolerance_set: str
    verdict: Literal["pass", "fail", "error"]
    status: int | None = None
    status_name: str | None = None
    problem: str | None = None
    tolerances: Coefficients | None = Field(
        default=None, description="Resolved values; present only when a column override applied."
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
    notes: list[str] = Field(default_factory=list)
    snippet: str | None = None
