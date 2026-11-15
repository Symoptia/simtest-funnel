"""describe_signals: file characteristics and data problems."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import WriteCsv, structured
from mcp.server.mcpserver.exceptions import ToolError

from simtest_funnel_mcp.server import describe_signals_impl


def test_demo_reference(demo_reference: Path) -> None:
    result = describe_signals_impl(str(demo_reference), [])
    d = structured(result)
    assert d["path"] == str(demo_reference)
    assert d["time_column"] == "time"
    assert d["time_column_rule"] == "named time"
    assert d["row_count"] == 1001
    assert d["time"]["start"] == 0.0
    assert d["time"]["end"] == 1.0
    assert d["time"]["span"] == 1.0
    sampling = d["time"]["sampling"]
    assert sampling["uniform"] is True
    assert sampling["median_step"] == pytest.approx(0.001)
    assert [c["name"] for c in d["columns"]] == ["x", "y", "z"]
    x = d["columns"][0]
    assert (x["min"], x["max"], x["range"]) == (-1.0, 1.0, 2.0)
    assert d["problems"] == []
    # No sample values: the whole result stays tiny.
    assert len(json.dumps(d)) < 1000
    text = result.content[0].text  # type: ignore[union-attr]
    assert "1001 rows" in text
    assert "uniform, step 0.001" in text
    assert "  x -1 1 2" in text


def test_non_uniform_sampling(write_csv: WriteCsv) -> None:
    d = structured(describe_signals_impl(str(write_csv("a.csv", "t,y\n0,0\n1,1\n3,0\n")), []))
    assert d["time_column_rule"] == "first column"
    s = d["time"]["sampling"]
    assert s == {"uniform": False, "min_step": 1.0, "median_step": 1.5, "max_step": 2.0}


def test_problems_are_reported(write_csv: WriteCsv) -> None:
    p = write_csv("a.csv", "time,y,z\n0,1,1\n2,abc,2\n1,,3\n")
    result = describe_signals_impl(str(p), [])
    assert not result.is_error
    d = structured(result)
    y = d["columns"][0]
    assert y["bad_values"] == 2
    assert "bad_values" not in d["columns"][1]
    problems = " | ".join(d["problems"])
    assert "not non-decreasing" in problems
    assert "column 'y' has 2 non-numeric" in problems


def test_header_only_file(write_csv: WriteCsv) -> None:
    d = structured(describe_signals_impl(str(write_csv("a.csv", "time,y\n")), []))
    assert d["row_count"] == 0
    assert "no data rows" in d["problems"][0]


def test_missing_file_is_a_tool_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="does not exist"):
        describe_signals_impl(str(tmp_path / "missing.csv"), [])


def test_relative_path_resolves_against_first_root(write_csv: WriteCsv, tmp_path: Path) -> None:
    write_csv("rel.csv", "time,y\n0,1\n1,2\n")
    d = structured(describe_signals_impl("rel.csv", [tmp_path.resolve()]))
    assert d["path"] == str((tmp_path / "rel.csv").resolve())


def test_path_outside_roots_is_refused(demo_reference: Path, tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="outside the client's workspace roots"):
        describe_signals_impl(str(demo_reference), [tmp_path.resolve()])


def test_symlink_escaping_root_is_refused(demo_reference: Path, tmp_path: Path) -> None:
    link = tmp_path / "link.csv"
    link.symlink_to(demo_reference)
    with pytest.raises(ToolError, match="outside"):
        describe_signals_impl(str(link), [tmp_path.resolve()])


def test_same_call_twice_is_identical(demo_reference: Path) -> None:
    a = describe_signals_impl(str(demo_reference), [])
    b = describe_signals_impl(str(demo_reference), [])
    assert a.structured_content == b.structured_content
