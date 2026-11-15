"""CSV loading: dialect, time-column rule and numeric coercion.

Dialect: see :mod:`simtest_funnel_mcp.reader` (shared verbatim with the
generated pytest snippets). The time column is the first column named
``time`` (case-insensitive), otherwise the first column.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from simtest_funnel_mcp.reader import CsvFormatError, read_signal_columns

#: How the time column was chosen.
RULE_NAMED = "named time"
RULE_FIRST = "first column"


class SignalFileError(Exception):
    """A file cannot be used at all (missing, unreadable, not CSV, no signals)."""


@dataclass(frozen=True)
class SignalFile:
    """A loaded CSV file: every column coerced to float64."""

    path: Path
    time_column: str
    time_column_rule: str
    #: Signal column names in file order (the time column excluded).
    signal_columns: tuple[str, ...]
    #: Coerced values per column (time column included); non-numeric and
    #: empty cells are NaN.
    values: dict[str, NDArray[np.float64]]
    #: Count of non-numeric, empty or non-finite cells per column (time
    #: column included).
    bad_cells: dict[str, int]

    @property
    def row_count(self) -> int:
        return int(self.values[self.time_column].shape[0])

    @property
    def time(self) -> NDArray[np.float64]:
        return self.values[self.time_column]

    def time_problems(self) -> list[str]:
        """Problems of the time column (empty list when it is usable)."""
        problems: list[str] = []
        bad = self.bad_cells[self.time_column]
        if bad:
            problems.append(
                f"time column {self.time_column!r} has {bad} non-numeric, empty "
                "or non-finite value(s)"
            )
        t = self.time
        finite = t[np.isfinite(t)]
        if finite.shape[0] >= 2 and bool(np.any(np.diff(finite) < 0)):
            problems.append(f"time column {self.time_column!r} is not non-decreasing")
        return problems


def choose_time_column(columns: list[str]) -> tuple[str, str]:
    """Return ``(time column, rule)`` for a header."""
    for name in columns:
        if name.strip().lower() == "time":
            return name, RULE_NAMED
    return columns[0], RULE_FIRST


def load_csv(path: Path) -> SignalFile:
    """Load ``path``; raise :class:`SignalFileError` if it cannot be used."""
    if not path.exists():
        raise SignalFileError(f"{path}: file does not exist")
    if not path.is_file():
        raise SignalFileError(f"{path}: not a regular file")
    try:
        columns, values = read_signal_columns(str(path))
    except CsvFormatError as exc:
        raise SignalFileError(f"{path}: {exc}") from exc
    except (pd.errors.ParserError, UnicodeDecodeError, OSError) as exc:
        raise SignalFileError(f"{path}: cannot be read as CSV: {exc}") from exc
    if len(columns) < 2:
        raise SignalFileError(
            f"{path}: needs a time column and at least one signal column, "
            f"found columns {columns}"
        )
    time_column, rule = choose_time_column(columns)
    bad_cells = {name: int(np.count_nonzero(~np.isfinite(arr))) for name, arr in values.items()}
    signal_columns = tuple(c for c in columns if c != time_column)
    return SignalFile(
        path=path,
        time_column=time_column,
        time_column_rule=rule,
        signal_columns=signal_columns,
        values=values,
        bad_cells=bad_cells,
    )
