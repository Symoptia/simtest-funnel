# --- simtest-funnel-mcp CSV reader (embedded verbatim in generated snippets) ---
# Dialect: comma-separated, one header row; lines whose first non-blank
# character is '#' and blank lines are skipped. Every column is coerced to
# float64 (non-numeric and empty cells become NaN). A data row with more
# fields than the header is an error. A trailing delimiter on every line,
# header included, is accepted: the trailing unnamed, empty column is dropped.
import csv
import io
import warnings

import numpy as np
import pandas as pd
from numpy.typing import NDArray


class CsvFormatError(ValueError):
    """The file is not a usable signal CSV (message names the problem)."""


def _is_skipped(line: bytes) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith(b"#")


def _data_line_number(raw: bytes, row: int) -> int:
    """1-based file line of data row ``row`` (1-based; header excluded)."""
    seen = -1  # the header is kept line 0
    for number, line in enumerate(raw.splitlines(), start=1):
        if not _is_skipped(line):
            seen += 1
            if seen == row:
                return number
    return 0


def read_signal_columns(path: str) -> tuple[list[str], dict[str, NDArray[np.float64]]]:
    """Return ``(column names in file order, float64 values per column)``."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw
    if b"#" in text:  # drop comment lines (and blank lines) before parsing
        text = b"".join(ln for ln in text.splitlines(keepends=True) if not _is_skipped(ln))
    start = 0
    header_line = b""
    while start < len(text):
        end = text.find(b"\n", start)
        end = len(text) if end < 0 else end + 1
        header_line, start = text[start:end], end
        if header_line.strip():
            break
    if not header_line.strip():
        raise CsvFormatError("no CSV header found")
    fields = next(csv.reader([header_line.decode("utf-8")], skipinitialspace=True))
    header = [c.strip() for c in fields]
    width = len(header)
    frame: pd.DataFrame | None = None
    if start < len(text):
        buffer = io.BytesIO(text)
        buffer.seek(start)
        too_wide = False
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", pd.errors.ParserWarning)
            try:
                frame = pd.read_csv(
                    buffer,
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
            lines = (ln.decode("utf-8") for ln in raw.splitlines() if not _is_skipped(ln))
            next(lines)  # header
            for row, row_fields in enumerate(csv.reader(lines, skipinitialspace=True), 1):
                if len(row_fields) > width:
                    raise CsvFormatError(
                        f"data row {row} (line {_data_line_number(raw, row)}) has "
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
        raise CsvFormatError(f"duplicate column names in header {header}")
    values = {
        name: pd.to_numeric(col, errors="coerce").to_numpy(dtype=np.float64, na_value=np.nan)
        for name, col in zip(header, cells, strict=True)
    }
    return header, values
