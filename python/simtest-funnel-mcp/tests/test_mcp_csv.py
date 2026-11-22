"""CSV loading: dialect, time-column rule, coercion and file errors."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from conftest import OPEN_METEO_REF, OPEN_METEO_START, WriteCsv, open_meteo_column

from simtest_funnel_mcp.csvio import RULE_FIRST, RULE_NAMED, SignalFileError, load_csv
from simtest_funnel_mcp.reader import read_signal_columns


def test_demo_file(demo_reference: Path) -> None:
    sf = load_csv(demo_reference)
    assert sf.time_column == "time"
    assert sf.time_column_rule == RULE_NAMED
    assert sf.signal_columns == ("x", "y", "z")
    assert sf.row_count == 1001
    assert sf.time_problems() == []


def test_time_column_named_case_insensitive_not_first(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "signal,Time,value\n1,0,2\n3,1,4\n"))
    assert sf.time_column == "Time"
    assert sf.time_column_rule == RULE_NAMED
    assert sf.signal_columns == ("signal", "value")
    np.testing.assert_array_equal(sf.time, [0.0, 1.0])


def test_first_column_rule(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "t,u,v\n0,1,2\n1,3,4\n"))
    assert sf.time_column == "t"
    assert sf.time_column_rule == RULE_FIRST


def test_comments_and_spaces(write_csv: WriteCsv) -> None:
    text = "# generated\ntime, y\n# a comment line\n0, 1.5\n1,  2.5\n"
    sf = load_csv(write_csv("a.csv", text))
    assert sf.signal_columns == ("y",)
    np.testing.assert_array_equal(sf.values["y"], [1.5, 2.5])
    assert sf.bad_cells["y"] == 0


def test_bad_cells_are_counted(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "time,y,z\n0,abc,1\n1,,2\n2,3,inf\n"))
    assert sf.bad_cells == {"time": 0, "y": 2, "z": 1}
    assert np.isnan(sf.values["y"][0])


def test_time_problems(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "time,y\n0,1\n2,1\n1,1\nx,1\n"))
    problems = sf.time_problems()
    assert any("1 non-numeric" in p for p in problems)
    assert any("not non-decreasing" in p for p in problems)


def test_header_only(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "time,y\n"))
    assert sf.row_count == 0


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "no CSV header"),
        ("time\n0\n1\n", "at least one signal column"),
        ("time,y,y\n0,1,2\n", "duplicate column names"),
    ],
)
def test_unusable_files(write_csv: WriteCsv, text: str, message: str) -> None:
    with pytest.raises(SignalFileError, match=message):
        load_csv(write_csv("bad.csv", text))


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SignalFileError, match="does not exist"):
        load_csv(tmp_path / "nope.csv")


def test_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SignalFileError, match="not a regular file"):
        load_csv(tmp_path)


def test_trailing_comma_on_data_rows_is_an_error(write_csv: WriteCsv) -> None:
    # Regression: pandas used the first field as index and shifted columns.
    with pytest.raises(SignalFileError, match=r"data row 1 \(line 2\) has 3 fields, header has 2"):
        load_csv(write_csv("a.csv", "time,a\n0,1,\n1,2,\n2,3,\n"))


def test_extra_field_on_a_later_row_is_an_error(write_csv: WriteCsv) -> None:
    text = "# comment\ntime,a\n0,1\n\n1,2,7\n"
    with pytest.raises(SignalFileError, match=r"data row 2 \(line 5\) has 3 fields, header has 2"):
        load_csv(write_csv("a.csv", text))
    with pytest.raises(SignalFileError, match=r"data row 2 \(line 3\) has 4 fields, header has 2"):
        load_csv(write_csv("b.csv", "time,a\n0,1\n1,2,7,8\n"))


def test_trailing_comma_on_every_line_is_accepted(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "time,a,\n0,1,\n1,2,\n2,3,\n"))
    assert sf.signal_columns == ("a",)
    np.testing.assert_array_equal(sf.values["a"], [1.0, 2.0, 3.0])
    assert sf.bad_cells == {"time": 0, "a": 0}


def test_empty_column_name_is_an_error(write_csv: WriteCsv) -> None:
    with pytest.raises(SignalFileError, match="header column 2 has no name"):
        load_csv(write_csv("a.csv", "time,,b\n0,1,2\n"))


def test_hash_inside_a_line_is_data(write_csv: WriteCsv) -> None:
    # Regression: comment="#" truncated the header at 'a#1'.
    text = "  # leading comment\ntime,a#1,b\n0,1,2\n  # indented comment\n1,1,2\n"
    sf = load_csv(write_csv("a.csv", text))
    assert sf.signal_columns == ("a#1", "b")
    np.testing.assert_array_equal(sf.values["b"], [2.0, 2.0])
    assert sf.row_count == 2


def test_columns_differing_from_time_only_by_case(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "Time,time,a\n0,5,1\n1,6,2\n"))
    assert sf.time_column == "Time"
    assert sf.signal_columns == ("time", "a")


def test_bom_and_crlf(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "﻿time,a\r\n0,1\r\n1,2\r\n"))
    assert sf.time_column == "time"
    np.testing.assert_array_equal(sf.values["a"], [1.0, 2.0])


# --------------------------------------------------------------------------
# Header line, preamble hint and ISO 8601 date-time time columns
# --------------------------------------------------------------------------

def test_comment_lines_before_the_header_with_the_default_header_line(
    write_csv: WriteCsv,
) -> None:
    sf = load_csv(write_csv("a.csv", "# one\n# two\ntime,a\n0,1\n1,2\n"))
    assert sf.signal_columns == ("a",)
    assert sf.header_line == 3
    assert sf.time_kind == "numeric" and sf.time_zone is None and sf.hints == ()


def test_open_meteo_with_header_line_4(open_meteo: Path) -> None:
    sf = load_csv(open_meteo, 4)
    assert sf.header_line == 4
    assert sf.time_column == "time"
    assert sf.signal_columns == (OPEN_METEO_REF,) + tuple(
        open_meteo_column(d) for d in (1, 3, 5)
    )
    assert (sf.time_kind, sf.time_zone) == ("datetime", "none")
    assert sf.row_count == 360
    assert sf.time[0] == OPEN_METEO_START and sf.time[-1] == OPEN_METEO_START + 359 * 3600
    assert sf.time_problems() == [] and sf.hints == ()
    # Header line 3 (the blank line) finds the same header.
    assert load_csv(open_meteo, 3).signal_columns == sf.signal_columns


def test_header_line_past_the_end(write_csv: WriteCsv) -> None:
    p = write_csv("a.csv", "time,a\n" + "".join(f"{i},{i}\n" for i in range(19)))
    with pytest.raises(SignalFileError) as info:
        load_csv(p, 50)
    msg = str(info.value)
    assert str(p) in msg and "header line 50" in msg and "the file has 20 lines" in msg


def test_header_line_must_be_positive(write_csv: WriteCsv) -> None:
    with pytest.raises(SignalFileError, match="header_line must be >= 1"):
        load_csv(write_csv("a.csv", "time,a\n0,1\n"), 0)


def test_data_row_line_numbers_stay_physical_with_a_header_line(write_csv: WriteCsv) -> None:
    text = "meta\nmeta\n\ntime,a\n0,1\n\n1,2,3\n"
    with pytest.raises(SignalFileError, match=r"data row 2 \(line 7\) has 3 fields"):
        load_csv(write_csv("a.csv", text), 4)


def test_preamble_hint_on_a_padded_read(open_meteo: Path) -> None:
    # The 5-field rows are narrower than the 6-field metadata header: the
    # read "succeeds" with padding, the hint explains it.
    sf = load_csv(open_meteo)
    assert sf.time_column == "latitude"
    (hint,) = sf.hints
    assert hint.startswith("header taken from line 1 ('latitude,longitude,elevation,")
    assert "line 3 is blank and line 4 ('time,temperature_2m (°C)," in hint
    assert hint.endswith("if it is, pass header_line=4")
    # The quoted header row is cut to 80 characters.
    quoted = hint.split("line 4 (")[1].split(") looks like")[0]
    assert len(quoted) <= 82 and quoted.endswith("...'")


def test_preamble_hint_on_a_failing_read(write_csv: WriteCsv) -> None:
    # Six signal columns: the header row (7 fields) is wider than the metadata.
    meta = "latitude,longitude,elevation,utc_offset_seconds,timezone,timezone_abbreviation\n"
    text = meta + "59.33,18.07,21.0,0,GMT,GMT\n\ntime,a,b,c,d,e,f\n2026-11-05T00:00,1,2,3,4,5,6\n"
    with pytest.raises(SignalFileError) as info:
        load_csv(write_csv("a.csv", text), arg="test_header_line")
    msg = str(info.value)
    assert "data row 2 (line 4) has 7 fields, header has 6" in msg
    assert "line 3 is blank and line 4 ('time,a,b,c,d,e,f') looks like a header row" in msg
    assert msg.endswith("If it is, pass test_header_line=4.")


def test_preamble_hint_in_a_file_with_lone_cr_line_breaks(write_csv: WriteCsv, tmp_path: Path) -> None:
    meta = "latitude,longitude,elevation,utc_offset_seconds,timezone,timezone_abbreviation"
    lines = [meta, "59.33,18.07,21.0,0,GMT,GMT", "", "time,a,b,c,d,e,f",
             "2026-11-05T00:00,1,2,3,4,5,6"]
    path = tmp_path / "cr.csv"
    path.write_bytes(("\r".join(lines) + "\r").encode())
    with pytest.raises(SignalFileError) as info:
        load_csv(path)
    msg = str(info.value)
    assert "line 3 is blank and line 4 ('time,a,b,c,d,e,f') looks like a header row" in msg
    assert msg.endswith("If it is, pass header_line=4.")


def test_no_preamble_hint_on_a_plain_file_with_a_blank_line(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "time,a,b\n\n0,1,2\n1,2,3\n"))
    assert sf.hints == ()
    # Not even when the time column has a problem.
    bad = load_csv(write_csv("b.csv", "time,a,b\n\n0,1,2\nx,2,3\n"))
    assert bad.time_problems() and bad.hints == ()


def test_duplicate_names_are_listed(write_csv: WriteCsv) -> None:
    with pytest.raises(SignalFileError, match=r"duplicated: \['y'\]"):
        load_csv(write_csv("a.csv", "time,y,y\n0,1,2\n"))


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("2026-11-20T00:00", 1795132800.0),
        ("2026-11-20 00:00:00", 1795132800.0),
        ("2026-11-20T00:00:00.25Z", 1795132800.25),
        ("2026-11-20T01:00+01:00", 1795132800.0),
        ("2026-11-20T01:00+0100", 1795132800.0),
        ("2026-11-20T01:00+01", 1795132800.0),
        ("2026-11-19T23:30-00:30", 1795132800.0),
    ],
)
def test_iso_forms_accepted(write_csv: WriteCsv, cell: str, expected: float) -> None:
    sf = load_csv(write_csv("a.csv", f"time,a\n{cell},1\n"))
    assert sf.time_kind == "datetime"
    assert sf.time[0] == expected


@pytest.mark.parametrize(
    "cell",
    [
        "２０２６-11-20T00:00",  # fullwidth digits
        "١٩٧٠-01-01T00:00Z",  # Arabic-Indic digits
        "2026-11-20T00:0٥Z",  # one Arabic-Indic digit in the minutes
        "2026-11-20T00:00:00.２５Z",  # fullwidth fraction
        "2026-11-20T01:00+０1:00",  # fullwidth zone
        "२०२६-११-२०",  # Devanagari date only
    ],
)
def test_iso_needs_ascii_digits(write_csv: WriteCsv, cell: str) -> None:
    """Unicode digits are not ISO 8601 digits: the cell is not a date-time
    (the column stays numeric with that cell unusable)."""
    from simtest_funnel_mcp.models import XRange

    sf = load_csv(write_csv("a.csv", f"time,a\n{cell},1\n2026-11-20T00:00,2\n"))
    assert sf.time_kind == "numeric"
    assert sf.time_problems()
    # Neither as an x_range bound.
    with pytest.raises(ValueError):
        XRange(lo=cell)


def test_iso_fraction_is_bit_identical_to_the_epoch_number(write_csv: WriteCsv) -> None:
    cells = ["2026-11-20T00:00:00.25Z", "2026-11-20T00:00:00.1Z", "1969-12-31T23:59:59.9Z",
             "2026-11-20T00:00:00.123456789Z"]
    numbers = ["1795132800.25", "1795132800.1", "-0.1", "1795132800.123456789"]
    iso = load_csv(write_csv("iso.csv", "time,a\n" + "".join(f"{c},1\n" for c in cells)))
    num = load_csv(write_csv("num.csv", "time,a\n" + "".join(f"{c},1\n" for c in numbers)))
    assert iso.time.tobytes() == num.time.tobytes()
    assert iso.fraction_digits == 9


def test_zone_kinds(write_csv: WriteCsv) -> None:
    none = load_csv(write_csv("a.csv", "time,a\n2026-11-20T00:00,1\n2026-11-20T01:00,1\n"))
    assert none.time_zone == "none"
    offset = load_csv(write_csv("b.csv", "time,a\n2026-11-20T00:00Z,1\n2026-11-20T02:00+01:00,1\n"))
    assert offset.time_zone == "offset"
    assert offset.time.tolist() == [1795132800.0, 1795136400.0]
    mixed = load_csv(write_csv("c.csv", "time,a\n2026-11-20T00:00,1\n2026-11-20T01:00Z,1\n"))
    assert mixed.time_zone == "mixed"
    assert any("mixes timestamps with and without a time zone" in p for p in mixed.time_problems())


def test_partly_iso_time_column_is_reported_without_values(write_csv: WriteCsv) -> None:
    rows = [f"2026-11-20T{h % 24:02d}:{h // 24:02d},1" for h in range(98)]
    rows.insert(40, "oops,1")
    rows.insert(70, "2026-13-01T00:00,1")  # matches the pattern, but no month 13
    sf = load_csv(write_csv("a.csv", "time,a\n" + "\n".join(rows) + "\n"))
    assert sf.time_kind == "numeric"
    (problem,) = sf.time_problems()
    assert "98 of 100 non-empty cells are ISO 8601 date-times" in problem
    assert "first other value at line 42" in problem  # header line 1, row 41
    assert "oops" not in problem and "2026-13" not in problem


def test_years_0001_and_9999(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "time,a\n0001-01-01T00:00,1\n9999-12-31T23:59:59,2\n"))
    assert sf.time_kind == "datetime"
    assert sf.time.tolist() == [-62135596800.0, 253402300799.0]


@pytest.mark.parametrize(
    "cell",
    ["2026-02-30T00:00", "2026-11-20T24:00", "2026-11-20T00:00:60", "2026-11-20t00:00",
     "2026-11-20T00:00z", "2026-11-20T00", "20261120T0000", "2026-11-20T00:00+25:00"],
)
def test_not_date_times(write_csv: WriteCsv, cell: str) -> None:
    sf = load_csv(write_csv("a.csv", f"time,a\n2026-11-20T00:00,1\n{cell},1\n"))
    assert sf.time_kind == "numeric"
    assert sf.time_problems()


def test_date_only_cells_are_midnight(write_csv: WriteCsv) -> None:
    # Date-only cells (Open-Meteo daily data); ACCEPT_DATE_ONLY in reader.py.
    sf = load_csv(write_csv("a.csv", "time,a\n2026-11-20,1\n2026-11-21,2\n"))
    assert (sf.time_kind, sf.time_zone) == ("datetime", "none")
    assert sf.time.tolist() == [1795132800.0, 1795219200.0]


def test_dates_and_date_times_mixed_in_one_column(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "time,a\n2026-11-20,1\n2026-11-20T12:00,2\n2026-11-21,3\n"))
    assert (sf.time_kind, sf.time_zone) == ("datetime", "none")
    assert sf.time.tolist() == [1795132800.0, 1795176000.0, 1795219200.0]


def test_empty_cells_do_not_prevent_detection(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "time,a\n2026-11-20T00:00,1\n,2\n2026-11-20T02:00,3\n"))
    assert sf.time_kind == "datetime"
    assert sf.time_problems() == ["time column 'time' has 1 empty value(s)"]


def test_only_the_time_column_is_converted(write_csv: WriteCsv) -> None:
    sf = load_csv(write_csv("a.csv", "time,a,when\n0,1,2026-11-20T00:00\n1,2,2026-11-20T01:00\n"))
    assert sf.time_kind == "numeric"
    assert sf.bad_cells["when"] == 2


def test_reader_returns_the_table(write_csv: WriteCsv) -> None:
    p = write_csv("a.csv", "x\n\nsignal,Time\n1,2026-11-20T00:00Z\n")
    table = read_signal_columns(str(p), 2)
    assert (table.time_column, table.time_column_rule) == ("Time", "named time")
    assert table.header == ["signal", "Time"]
    assert (table.time_kind, table.time_zone, table.header_line) == ("datetime", "offset", 3)


def test_iso_file_reads_within_a_small_multiple_of_a_numeric_one(tmp_path: Path) -> None:
    """ISO times are parsed vectorised: 100 000 rows take at most a small
    multiple of the numeric twin's time (best of three, plus 0.1 s against
    timer and scheduling noise); a per-cell parse would take seconds."""
    import time

    n = 100_000
    t = OPEN_METEO_START + np.arange(n)
    iso = np.datetime_as_string(t.astype("datetime64[s]"))
    y = (np.arange(n) % 7).astype(str)
    (tmp_path / "iso.csv").write_text("time,a\n" + "\n".join(np.char.add(np.char.add(iso, ","), y)) + "\n")
    (tmp_path / "num.csv").write_text(
        "time,a\n" + "\n".join(np.char.add(np.char.add(t.astype(str), ","), y)) + "\n"
    )

    def best(name: str) -> float:
        times = []
        for _ in range(3):
            start = time.perf_counter()
            load_csv(tmp_path / name)
            times.append(time.perf_counter() - start)
        return min(times)

    num, iso_time = best("num.csv"), best("iso.csv")
    print(f"100k rows: numeric {num:.2f} s, ISO {iso_time:.2f} s")
    assert iso_time < 4 * num + 0.1, (iso_time, num)
    assert (load_csv(tmp_path / "iso.csv").time == load_csv(tmp_path / "num.csv").time).all()
