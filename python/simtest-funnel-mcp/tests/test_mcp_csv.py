"""CSV loading: dialect, time-column rule, coercion and file errors."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from conftest import WriteCsv

from simtest_funnel_mcp.csvio import RULE_FIRST, RULE_NAMED, SignalFileError, load_csv


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
