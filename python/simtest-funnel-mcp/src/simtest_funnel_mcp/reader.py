# --- simtest-funnel-mcp CSV reader (embedded verbatim in generated snippets) ---
# Dialect: comma-separated, one header row; lines whose first non-blank
# character is '#' and blank lines are skipped. Lines before header_line
# (1-based physical line) are skipped unread; the header is the first line at
# or after it that is neither blank nor a comment. The time column is the
# first column named 'time' (any case), else the first column. Every column is
# coerced to float64 (non-numeric and empty cells become NaN), except a time
# column whose non-empty cells all are ISO 8601 date-times: it becomes seconds
# since the Unix epoch (a cell without offset is read as UTC). A data row with
# more fields than the header is an error. A trailing delimiter on every line,
# header included, is accepted: the trailing unnamed, empty column is dropped.
import csv
import io
import re
import warnings
from typing import NamedTuple

import numpy as np
import pandas as pd
from numpy.typing import NDArray

#: Accept date-only cells such as 2026-11-20 (midnight).
ACCEPT_DATE_ONLY = True
#: YYYY-MM-DD[(T| )hh:mm[:ss[.f+]][Z|+hh[:mm]|+hhmm]], ASCII digits only (groups: date, time, fraction, zone).
ISO_DATETIME = r"([0-9]{4})-([0-9][0-9])-([0-9][0-9])(?:[T ]([0-9][0-9]):([0-9][0-9])(?::([0-9][0-9])(?:\.([0-9]+))?)?" + (
    r"(Z|[+-][0-9][0-9](?::?[0-9][0-9])?)?)" + ("?" if ACCEPT_DATE_ONLY else "")
)
_EOL = re.compile(rb"\r\n|\r|\n")


class CsvFormatError(ValueError):
    """The file is not a usable signal CSV (message names the problem)."""


class SignalTable(NamedTuple):
    """What :func:`read_signal_columns` read."""

    header: list[str]
    values: dict[str, NDArray[np.float64]]
    time_column: str
    time_column_rule: str  # "named time" or "first column"
    time_kind: str  # "numeric" or "datetime"
    time_zone: str | None  # datetime only: "offset", "none" or "mixed"
    header_line: int  # physical line of the header used
    time_cells: int  # non-empty cells of the time column
    iso_cells: int  # numeric time column: non-empty cells that are ISO 8601 date-times
    first_other_line: int  # ... and the line of the first other non-empty cell
    fraction_digits: int  # datetime: most fraction digits of a cell


def _is_skipped(line: bytes) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith(b"#")


def _data_line_number(body: bytes, row: int, header_line: int) -> int:
    """Physical line of data row ``row`` (1-based) of ``body`` (the lines after the header)."""
    seen = 0
    for number, line in enumerate(body.splitlines(), start=header_line + 1):
        if not _is_skipped(line):
            seen += 1
            if seen == row:
                return number
    return 0


def _days_from_civil(y: NDArray[np.int64], m: NDArray[np.int64], d: NDArray[np.int64]) -> NDArray[np.int64]:
    """Days since 1970-01-01 of proleptic Gregorian dates (vectorised)."""
    y = y - (m <= 2)
    era = y // 400
    yoe = y - era * 400
    doy = (153 * ((m + 9) % 12) + 2) // 5 + d - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468  # type: ignore[no-any-return]


def parse_iso(cells: "pd.Series[str]") -> tuple[NDArray[np.float64], NDArray[np.bool_], NDArray[np.bool_], int]:
    """ISO 8601 cells -> (epoch seconds, valid, has zone, most fraction digits); NaN if not valid."""
    n = len(cells)
    ok = cells.str.fullmatch(ISO_DATETIME).fillna(False).to_numpy(dtype=bool).copy()
    text = cells.where(ok, "1970-01-01").to_numpy(dtype=str)
    width = max(text.dtype.itemsize // 4, 19)
    c = text.astype(f"U{width}").view(np.uint32).reshape(n, width).astype(np.int64)
    length = (c != 0).sum(axis=1)

    def num(a: int, b: int) -> NDArray[np.int64]:  # digits at fixed positions a..b-1
        return ((c[:, a:b] - 48) * 10 ** np.arange(b - a - 1, -1, -1)).sum(axis=1)

    has_time = length > 10
    has_sec = has_time & (c[:, 16] == ord(":"))
    y, mo, d = num(0, 4), num(5, 7), num(8, 10)
    h, mi, s = num(11, 13) * has_time, num(14, 16) * has_time, num(17, 19) * has_sec
    # Variable tail after the minutes or seconds: optional fraction, then zone.
    pos = np.where(has_sec, 19, np.where(has_time, 16, 10))
    frac = np.full(n, "", dtype=object)
    zone = np.full(n, "", dtype=object)
    tail = np.flatnonzero(length > pos)
    if tail.shape[0]:
        rest = pd.Series([v[p:] for v, p in zip(text[tail].tolist(), pos[tail].tolist(), strict=True)], dtype=object)
        g = rest.str.extract(r"^(?:\.([0-9]+))?(Z|[+-][0-9][0-9](?::?[0-9][0-9])?)?\Z").fillna("")
        frac[tail], zone[tail] = g[0].to_numpy(dtype=object), g[1].to_numpy(dtype=object)
    zd = [z.replace(":", "") for z in zone[tail].tolist()]
    zh, zm = np.zeros(n, dtype=np.int64), np.zeros(n, dtype=np.int64)
    zh[tail] = [int(z[1:3] or 0) for z in zd]
    zm[tail] = [int(z[3:5] or 0) for z in zd]
    leap = (y % 4 == 0) & ((y % 100 != 0) | (y % 400 == 0))
    dim = np.array([0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])[np.clip(mo, 0, 12)] + (leap & (mo == 2))
    ok &= (mo >= 1) & (mo <= 12) & (d >= 1) & (d <= dim)
    ok &= (h <= 23) & (mi <= 59) & (s <= 59) & (zh <= 23) & (zm <= 59)
    sign = np.ones(n, dtype=np.int64)
    sign[tail] = [-1 if z.startswith("-") else 1 for z in zd]
    secs = _days_from_civil(y, mo, d) * 86400 + h * 3600 + mi * 60 + s - sign * (zh * 3600 + zm * 60)
    values = secs.astype(np.float64)
    has_frac = ok & (frac != "")
    if has_frac.any():
        # "<seconds>.<fraction>" parsed like a numeric cell: one correctly
        # rounded conversion, so a twin file with epoch seconds is identical.
        decimal = [
            f"{q}.{f}" if q >= 0 else f"-{-q - 1}.{10 ** len(f) - int(f):0{len(f)}d}" if int(f) else str(q)
            for q, f in zip(secs[has_frac].tolist(), frac[has_frac].tolist(), strict=True)
        ]
        values[has_frac] = pd.to_numeric(pd.Series(decimal, dtype=object)).to_numpy(dtype=np.float64)
    values[~ok] = np.nan
    digits = max((len(f) for f in frac[has_frac].tolist()), default=0)
    return values, ok, ok & (zone != ""), digits


def _numeric(col: "pd.Series[str]") -> NDArray[np.float64]:
    return pd.to_numeric(col, errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)


def read_signal_columns(path: str, header_line: int = 1) -> SignalTable:
    """Read a signal CSV; see the dialect above."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    start = 0
    for _ in range(header_line - 1):  # skip physical lines before header_line, unread
        m = _EOL.search(raw, start)
        start = len(raw) if m is None else m.end()
    line_no = header_line
    header_text = b""
    while start < len(raw):
        m = _EOL.search(raw, start)
        end = len(raw) if m is None else m.end()
        header_text, start = raw[start:end], end
        if not _is_skipped(header_text):
            break
        line_no += 1
    if _is_skipped(header_text):
        if header_line == 1:
            raise CsvFormatError("no CSV header found")
        raise CsvFormatError(
            f"no CSV header found at or after header line {header_line} "
            f"(the file has {len(raw.splitlines())} lines)"
        )
    body = raw[start:]
    fields = next(csv.reader([header_text.decode("utf-8")], skipinitialspace=True))
    header = [c.strip() for c in fields]
    width = len(header)
    data = body
    if b"#" in data:  # drop comment lines (and blank lines) before parsing
        data = b"".join(ln for ln in data.splitlines(keepends=True) if not _is_skipped(ln))
    frame: pd.DataFrame | None = None
    if data:
        too_wide = False
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", pd.errors.ParserWarning)
            try:
                frame = pd.read_csv(
                    io.BytesIO(data),
                    header=None,
                    names=list(range(width)),
                    # Never infer an index from surplus fields.
                    index_col=False,
                    dtype=str,
                    keep_default_na=False,
                    skipinitialspace=True,
                    encoding="utf-8",
                )
            except pd.errors.EmptyDataError:
                frame = None  # only blank lines after the header
            except pd.errors.ParserError as exc:
                if "Expected" not in str(exc):
                    raise CsvFormatError(f"cannot be parsed as CSV: {exc}") from exc
                too_wide = True
        # pandas silently drops one surplus field (with a ParserWarning).
        too_wide = too_wide or any(
            issubclass(w.category, pd.errors.ParserWarning) for w in caught
        )
        if too_wide:
            lines = (ln.decode("utf-8") for ln in body.splitlines() if not _is_skipped(ln))
            for row, row_fields in enumerate(csv.reader(lines, skipinitialspace=True), 1):
                if len(row_fields) > width:
                    raise CsvFormatError(
                        f"data row {row} (line {_data_line_number(body, row, line_no)}) has "
                        f"{len(row_fields)} fields, header has {width}"
                    )
            raise CsvFormatError(f"a data row has more fields than the header ({width})")
    if frame is not None:
        cells = [frame[i].fillna("").astype(str).str.strip() for i in range(width)]
    else:
        cells = [pd.Series([], dtype=str) for _ in range(width)]
    # Trailing delimiter on every line: drop trailing unnamed, all-empty columns.
    while width > 1 and header[-1] == "" and bool((cells[-1] == "").all()):
        header.pop()
        cells.pop()
        width -= 1
    for i, name in enumerate(header):
        if name == "":
            raise CsvFormatError(f"header column {i + 1} has no name")
    if len(set(header)) != len(header):
        dup = sorted({c for c in header if header.count(c) > 1})
        raise CsvFormatError(f"duplicate column names in header {header} (duplicated: {dup})")
    named = [i for i, c in enumerate(header) if c.strip().lower() == "time"]
    ti = named[0] if named else 0
    values = {name: _numeric(col) for i, (name, col) in enumerate(zip(header, cells, strict=True)) if i != ti}
    col = cells[ti]
    nonempty = (col != "").to_numpy()
    kind, zone, iso_cells, other_line, digits = "numeric", None, 0, 0, 0
    first = col[nonempty].iloc[0] if nonempty.any() else ""
    t: NDArray[np.float64] | None = None
    if re.fullmatch(ISO_DATETIME, first):  # cheap check before parsing a whole column
        iso, ok, zoned, digits = parse_iso(col)
        if ok[nonempty].all():
            t, kind = iso, "datetime"
            zone = "offset" if zoned[nonempty].all() else "mixed" if zoned.any() else "none"
    if t is None:
        t, digits = _numeric(col), 0
        if (nonempty & np.isnan(t)).any():  # report how much of it is ISO 8601
            ok = parse_iso(col)[1]
            iso_cells = int(ok.sum())
            others = np.flatnonzero(nonempty & ~ok)
            if iso_cells and others.shape[0]:
                other_line = _data_line_number(body, int(others[0]) + 1, line_no)
    values = {header[ti]: t, **values}
    values = {name: values[name] for name in header}
    return SignalTable(
        header, values, header[ti], "named time" if named else "first column",
        kind, zone, line_no, int(nonempty.sum()), iso_cells, other_line, digits,
    )
