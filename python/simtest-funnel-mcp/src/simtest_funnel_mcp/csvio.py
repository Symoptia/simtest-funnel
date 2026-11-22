"""CSV loading: dialect, header line, time-column rule and numeric coercion.

Dialect, header line, time-column rule and the ISO 8601 date-time time
column: see :mod:`simtest_funnel_mcp.reader` (shared verbatim with the
generated pytest snippets). This module adds the server-side concerns: file
errors, data problems and the preamble hint (design §3), which only adds
text and never changes what is read.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from simtest_funnel_mcp.reader import ISO_DATETIME, CsvFormatError, read_signal_columns

#: How the time column was chosen.
RULE_NAMED = "named time"
RULE_FIRST = "first column"

#: Physical lines scanned for a preamble.
PREAMBLE_SCAN_LINES = 100
#: Quoted header/preamble lines are cut to this many characters.
QUOTE_CHARS = 80

TimeKind = Literal["numeric", "datetime"]
TimeZone = Literal["offset", "none", "mixed"]


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
    #: empty cells are NaN. A date-time time column holds epoch seconds.
    values: dict[str, NDArray[np.float64]]
    #: Count of non-numeric, empty or non-finite cells per column (time
    #: column included).
    bad_cells: dict[str, int]
    #: Physical line of the header used (1-based).
    header_line: int = 1
    time_kind: TimeKind = "numeric"
    #: Date-time axes only: every cell has an offset, none has, or mixed.
    time_zone: TimeZone | None = None
    #: Numeric time column: non-empty cells that are ISO 8601 date-times,
    #: non-empty cells in total and the line of the first other cell.
    iso_cells: int = 0
    nonempty_time_cells: int = 0
    first_other_line: int = 0
    #: Date-time axes: most fraction digits of a time cell.
    fraction_digits: int = 0
    #: Preamble hints for a read that succeeded but looks implausible.
    hints: tuple[str, ...] = field(default=())
    #: What results and messages call the file: the URL for a fetched file
    #: (whose local cache path is never shown), else ``None`` (the path).
    display: str | None = None

    @property
    def name(self) -> str:
        """The file's name in results and messages (path or URL)."""
        return self.display if self.display is not None else str(self.path)

    @property
    def row_count(self) -> int:
        return int(self.values[self.time_column].shape[0])

    @property
    def time(self) -> NDArray[np.float64]:
        return self.values[self.time_column]

    @property
    def is_datetime(self) -> bool:
        return self.time_kind == "datetime"

    def time_problems(self) -> list[str]:
        """Problems of the time column (empty list when it is usable)."""
        problems: list[str] = []
        bad = self.bad_cells[self.time_column]
        name = self.time_column
        if bad and self.is_datetime:
            problems.append(f"time column {name!r} has {bad} empty value(s)")
        elif bad:
            text = f"time column {name!r} has {bad} non-numeric, empty or non-finite value(s)"
            if self.iso_cells:
                text += (
                    f"; {self.iso_cells} of {self.nonempty_time_cells} non-empty cells are "
                    f"ISO 8601 date-times (first other value at line {self.first_other_line}), "
                    "so it is not read as a date-time column: every non-empty cell must be one"
                )
            problems.append(text)
        if self.time_zone == "mixed":
            problems.append(
                f"time column {name!r} mixes timestamps with and without a time zone; write "
                "all of them with an offset (e.g. 'Z' for UTC) or all without"
            )
        t = self.time
        finite = t[np.isfinite(t)]
        if finite.shape[0] >= 2 and bool(np.any(np.diff(finite) < 0)):
            problems.append(f"time column {name!r} is not non-decreasing")
        return problems


def choose_time_column(columns: list[str]) -> tuple[str, str]:
    """Return ``(time column, rule)`` for a header (the reader applies the same rule)."""
    for name in columns:
        if name.strip().lower() == "time":
            return name, RULE_NAMED
    return columns[0], RULE_FIRST


# --------------------------------------------------------------------------
# Preamble hint
# --------------------------------------------------------------------------


def _head_lines(path: Path) -> list[str]:
    """The first :data:`PREAMBLE_SCAN_LINES` physical lines (decoded leniently)."""
    out: list[str] = []
    try:
        with open(path, "rb") as fh:
            for _ in range(PREAMBLE_SCAN_LINES):
                line = fh.readline()
                if not line:
                    break
                out.append(line.decode("utf-8", errors="replace"))
    except OSError:
        return []
    if out and out[0].startswith("﻿"):
        out[0] = out[0][1:]
    return [ln.rstrip("\r\n") for ln in out]


def _skipped(line: str) -> bool:
    s = line.strip()
    return not s or s.startswith("#")


def _fields(line: str) -> list[str]:
    return [f.strip() for f in next(csv.reader([line], skipinitialspace=True), [])]


def _is_value(f: str) -> bool:
    """A number or an ISO 8601 date-time (what a data cell looks like)."""
    if re.fullmatch(ISO_DATETIME, f):
        return True
    try:
        float(f)
    except ValueError:
        return False
    return True


def _quote(line: str) -> str:
    s = line.strip()
    return repr(s if len(s) <= QUOTE_CHARS else s[: QUOTE_CHARS - 3] + "...")


def _header_index(lines: list[str], header_line: int) -> int | None:
    """0-based index of the header used for ``header_line`` (None: not in the scan)."""
    for i in range(header_line - 1, len(lines)):
        if not _skipped(lines[i]):
            return i
    return None


def preamble_candidate(lines: list[str], header_index: int) -> int | None:
    """0-based index of a line after the header that looks like the real
    header after a preamble (design §3), or ``None``."""
    for i in range(header_index + 1, len(lines)):
        if lines[i - 1].strip() or _skipped(lines[i]):
            continue
        fields = _fields(lines[i])
        if len(fields) < 2 or any(_is_value(f) for f in fields):
            continue
        nxt = next((j for j in range(i + 1, len(lines)) if not _skipped(lines[j])), None)
        if nxt is None:
            continue
        data = _fields(lines[nxt])
        if len(data) == len(fields) and any(_is_value(f) for f in data):
            return i
    return None


def preamble_hint(
    lines: list[str], header_line: int, arg: str, *, failed: bool, time_unusable: bool
) -> str | None:
    """Hint text suggesting a header line, or ``None`` when there is no reason.

    Given when a candidate exists and the read failed, the header used has a
    different field count than the candidate, or the time column is unusable.
    """
    h = _header_index(lines, header_line)
    if h is None:
        return None
    c = preamble_candidate(lines, h)
    if c is None:
        return None
    width_differs = len(_fields(lines[h])) != len(_fields(lines[c]))
    if not (failed or width_differs or time_unusable):
        return None
    where = (
        f"line {c} is blank and line {c + 1} ({_quote(lines[c])}) looks like a header row"
    )
    if failed:
        return f"The file seems to start with a preamble: {where}. If it is, pass {arg}={c + 1}."
    return (
        f"header taken from line {h + 1} ({_quote(lines[h])}), but the file seems to start "
        f"with a preamble: {where}; if it is, pass {arg}={c + 1}"
    )


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_csv(
    path: Path, header_line: int = 1, *, arg: str = "header_line", display: str | None = None
) -> SignalFile:
    """Load ``path``; raise :class:`SignalFileError` if it cannot be used.

    ``arg`` names the header line argument in hints (``header_line`` or
    ``test_header_line``). ``display`` replaces the path in messages and
    results (the URL of a fetched file).
    """
    if display is not None:
        try:
            sf = load_csv(path, header_line, arg=arg)
        except SignalFileError as exc:
            raise SignalFileError(str(exc).replace(str(path), display)) from None
        return _replace(sf, display=display)
    if header_line < 1:
        raise SignalFileError(f"{path}: {arg} must be >= 1, got {header_line}")
    if not path.exists():
        raise SignalFileError(f"{path}: file does not exist")
    if not path.is_file():
        raise SignalFileError(f"{path}: not a regular file")

    def fail(message: str) -> SignalFileError:
        hint = preamble_hint(
            _head_lines(path), header_line, arg, failed=True, time_unusable=False
        )
        return SignalFileError(f"{message}. {hint}" if hint else message)

    try:
        table = read_signal_columns(str(path), header_line)
    except CsvFormatError as exc:
        raise fail(f"{path}: {exc}") from exc
    except (pd.errors.ParserError, UnicodeDecodeError, OSError) as exc:
        raise fail(f"{path}: cannot be read as CSV: {exc}") from exc
    columns, values = table.header, table.values
    if len(columns) < 2:
        raise fail(
            f"{path}: needs a time column and at least one signal column, "
            f"found columns {columns}"
        )
    bad_cells = {name: int(np.count_nonzero(~np.isfinite(arr))) for name, arr in values.items()}
    time_column = table.time_column
    signal_columns = tuple(c for c in columns if c != time_column)
    sf = SignalFile(
        path=path,
        time_column=time_column,
        time_column_rule=RULE_NAMED if table.time_column_rule == RULE_NAMED else RULE_FIRST,
        signal_columns=signal_columns,
        values=values,
        bad_cells=bad_cells,
        header_line=table.header_line,
        time_kind="datetime" if table.time_kind == "datetime" else "numeric",
        time_zone=(
            None if table.time_zone is None
            else "offset" if table.time_zone == "offset"
            else "none" if table.time_zone == "none" else "mixed"
        ),
        iso_cells=table.iso_cells,
        nonempty_time_cells=table.time_cells,
        first_other_line=table.first_other_line,
        fraction_digits=table.fraction_digits,
    )
    time_unusable = bool(sf.bad_cells[time_column]) or sf.time_zone == "mixed"
    hint = preamble_hint(
        _head_lines(path), header_line, arg, failed=False, time_unusable=time_unusable
    )
    if hint is not None:
        sf = _replace(sf, hints=(hint,))
    return sf


def _replace(sf: SignalFile, **changes: object) -> SignalFile:
    return replace(sf, **changes)  # type: ignore[arg-type]
