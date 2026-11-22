"""describe_signals: file characteristics and data problems."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import WriteCsv, open_meteo_text, structured
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


def _wide_file(write_csv: WriteCsv, n: int) -> Path:
    header = "time," + ",".join(f"model.subsystem.component{i}.port.signal" for i in range(n))
    rows = [",".join(["0"] + ["0"] * n), ",".join(["1"] + ["x"] * n)]
    return write_csv("wide.csv", header + "\n" + "\n".join(rows) + "\n")


def test_many_columns_are_capped(write_csv: WriteCsv) -> None:
    # Regression: 3000 columns produced ~470 kB.
    p = _wide_file(write_csv, 3000)
    result = describe_signals_impl(str(p), [])
    d = structured(result)
    assert len(d["columns"]) == 100
    assert (d["columns_total"], d["columns_selected"], d["columns_omitted"]) == (3000, 3000, 2900)
    assert len(d["problems"]) == 100 and d["problems_omitted"] == 2900
    text = result.content[0].text  # type: ignore[union-attr]
    assert "2900 more column(s) omitted" in text
    assert len(json.dumps(d)) < 25_000, len(json.dumps(d))
    assert len(text) < 20_000, len(text)


def test_columns_filter_with_names_and_globs(write_csv: WriteCsv) -> None:
    p = _wide_file(write_csv, 30)
    d = structured(
        describe_signals_impl(
            str(p), [],
            columns=["model.subsystem.component1?.port.signal",
                     "model.subsystem.component3.port.signal", "nope*"],
            max_columns=5,
        )
    )
    assert d["columns_selected"] == 11
    assert d["columns_omitted"] == 6
    assert [c["name"] for c in d["columns"]][:2] == [
        "model.subsystem.component3.port.signal", "model.subsystem.component10.port.signal"
    ]
    assert d["problems"][0] == "columns filter: no signal column matches 'nope*'"
    assert d["problems_omitted"] == 12 - 5  # 1 filter problem + 11 bad columns, 5 listed


def test_empty_columns_filter_is_an_error(write_csv: WriteCsv) -> None:
    p = write_csv("a.csv", "time,y\n0,1\n")
    with pytest.raises(ToolError, match="columns is empty"):
        describe_signals_impl(str(p), [], columns=[])


# --------------------------------------------------------------------------
# Header line and date-time time axis
# --------------------------------------------------------------------------


def test_open_meteo_time_column(open_meteo: Path) -> None:
    result = describe_signals_impl(str(open_meteo), [], header_line=4)
    d = structured(result)
    assert d["header_line"] == 4
    assert d["time_column"] == "time" and d["time_column_rule"] == "named time"
    assert d["time"] == {
        "kind": "datetime",
        "time_zone": "none",
        "start": 1793836800.0,
        "start_iso": "2026-11-05T00:00:00",
        "end": 1795129200.0,
        "end_iso": "2026-11-19T23:00:00",
        "span": 1292400.0,
        "span_duration": "P14DT23H",
        "sampling": {
            "uniform": True, "min_step": 3600.0, "median_step": 3600.0, "max_step": 3600.0,
            "median_step_duration": "PT1H",
        },
    }
    assert d["problems"] == ["time column 'time' has no time zone; read as UTC"]
    assert [c["name"] for c in d["columns"]][0] == "temperature_2m (°C)"
    text = result.content[0].text  # type: ignore[union-attr]
    assert text.splitlines()[0].endswith(
        "360 rows, time column 'time' (named time), ISO 8601 date-times (no time zone, "
        "read as UTC), header line 4"
    )
    assert text.splitlines()[1] == (
        "time 2026-11-05T00:00:00 .. 2026-11-19T23:00:00 (span P14DT23H), uniform, step PT1H"
    )


def test_open_meteo_without_header_line_suggests_it(open_meteo: Path) -> None:
    d = structured(describe_signals_impl(str(open_meteo), []))
    assert d["header_line"] == 1
    hint = d["problems"][0]
    assert hint.startswith("header taken from line 1 (")
    assert "line 3 is blank and line 4" in hint and "pass header_line=4" in hint


def test_numeric_time_column_reports_header_line_and_kind(demo_reference: Path) -> None:
    d = structured(describe_signals_impl(str(demo_reference), []))
    assert d["header_line"] == 1
    assert d["time"]["kind"] == "numeric"
    assert set(d["time"]) == {"kind", "start", "end", "span", "sampling"}
    assert set(d["time"]["sampling"]) == {"uniform", "min_step", "median_step", "max_step"}
    text = describe_signals_impl(str(demo_reference), []).content[0].text  # type: ignore[union-attr]
    assert "header line" not in text and "ISO" not in text


def test_header_line_past_the_end_is_a_tool_error(write_csv: WriteCsv) -> None:
    p = write_csv("a.csv", "time,y\n0,1\n")
    with pytest.raises(ToolError, match="header line 5 .the file has 2 lines"):
        describe_signals_impl(str(p), [], header_line=5)


def test_sub_second_iso_data_is_uniform(write_csv: WriteCsv) -> None:
    rows = "".join(
        f"2026-11-20T00:{k // 600:02d}:{(k % 600) / 10:04.1f}Z,1\n" for k in range(3000)
    )
    d = structured(describe_signals_impl(str(write_csv("a.csv", "time,a\n" + rows)), []))
    s = d["time"]["sampling"]
    assert d["time"]["time_zone"] == "offset"
    assert s["uniform"] is True, s
    assert s["median_step_duration"] == "PT0.1S"
    assert d["time"]["start_iso"] == "2026-11-20T00:00:00Z"


def test_epoch_numbers_and_iso_twin_are_described_identically(write_csv: WriteCsv) -> None:
    # Resolution-aware uniform check on every axis: 0.1 s epoch-second data
    # jitter by a few float64 spacings and still count as uniform.
    t0 = 1795132800
    num_rows = "".join(f"{t0 + k // 10}.{k % 10},1\n" for k in range(600))
    iso_rows = "".join(
        f"2026-11-20T00:{k // 600:02d}:{(k % 600) // 10:02d}.{k % 10},1\n" for k in range(600)
    )
    num = structured(describe_signals_impl(str(write_csv("n.csv", "time,a\n" + num_rows)), []))
    iso = structured(describe_signals_impl(str(write_csv("i.csv", "time,a\n" + iso_rows)), []))
    assert num["time"]["sampling"]["uniform"] is True
    numeric_fields = {k: v for k, v in iso["time"].items() if not k.endswith(("_iso", "_duration"))}
    numeric_fields.pop("time_zone")
    numeric_fields["kind"] = "numeric"
    sampling = dict(numeric_fields["sampling"])
    sampling.pop("median_step_duration")
    numeric_fields["sampling"] = sampling
    assert num["time"] == numeric_fields


def test_small_time_values_keep_the_relative_uniform_check(write_csv: WriteCsv) -> None:
    # Steps 1 and 1 + 2e-6: spread 2e-6 > 1e-6 * median, far above the float
    # spacing of t ~ 10, so non-uniform exactly as before.
    rows = "".join(f"{k + (2e-6 if k % 2 else 0)!r},1\n" for k in range(10))
    s = structured(describe_signals_impl(str(write_csv("a.csv", "t,y\n" + rows)), []))
    assert s["time"]["sampling"]["uniform"] is False
    rows = "".join(f"{k * 0.001!r},1\n" for k in range(1001))
    assert structured(
        describe_signals_impl(str(write_csv("b.csv", "t,y\n" + rows)), [])
    )["time"]["sampling"]["uniform"] is True


def test_more_than_six_fraction_digits_are_noted(write_csv: WriteCsv) -> None:
    p = write_csv("a.csv", "time,a\n2026-11-20T00:00:00.1234567Z,1\n2026-11-20T00:00:01Z,1\n")
    d = structured(describe_signals_impl(str(p), []))
    assert any("7 fraction digits" in n and "0.25 microseconds" in n for n in d["notes"])


def test_offset_axis_has_no_time_zone_problem(write_csv: WriteCsv) -> None:
    p = write_csv("a.csv", "time,a\n2026-11-20T00:00Z,1\n2026-11-20T01:00Z,1\n")
    d = structured(describe_signals_impl(str(p), []))
    assert d["problems"] == [] and d["time"]["end_iso"] == "2026-11-20T01:00:00Z"


def test_unixtime_twin_matches_iso_numbers(write_csv: WriteCsv) -> None:
    iso = structured(describe_signals_impl(
        str(write_csv("i.csv", open_meteo_text())), [], header_line=4))
    num = structured(describe_signals_impl(
        str(write_csv("n.csv", open_meteo_text(iso=False))), [], header_line=4))
    for k in ("start", "end", "span"):
        assert iso["time"][k] == num["time"][k]
    assert iso["columns"] == num["columns"]
