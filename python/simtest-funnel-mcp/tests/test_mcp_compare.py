"""compare_signals: verdicts, tolerance sets, overrides, problems and caps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import (
    OPEN_METEO_REF,
    WriteCsv,
    open_meteo_column,
    open_meteo_text,
    structured,
)
from mcp.server.mcpserver.exceptions import ToolError

import simtest.funnel as funnel
from simtest_funnel_mcp.compare import compose_override, resolve_with_library
from simtest_funnel_mcp.models import ColumnPair, ToleranceSet, ToleranceSpec, XRange
from simtest_funnel_mcp.server import compare_signals_impl

LOOSE = ToleranceSet(label="loose", atolx=0.1, atoly=0.1)
NOXTOL = ToleranceSet(label="noxtol", atolx=0.0, atoly=0.1)


def _compare(ref: Path, tst: Path, **kwargs: Any) -> dict[str, Any]:
    return structured(compare_signals_impl(str(ref), str(tst), [], **kwargs))


def _rows(d: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["column"], r["tolerance_set"]): r for r in d["rows"]}


def _library_status(ref: Path, tst: Path, column: str, tol: funnel.Tolerances) -> int:
    import pandas as pd

    r = pd.read_csv(ref)
    t = pd.read_csv(tst)
    return funnel.compare(
        r["time"].to_numpy(), r[column].to_numpy(), t["time"].to_numpy(), t[column].to_numpy(),
        funnel.Options(tolerances=tol),
    ).status


def test_pass_and_fail_on_demo(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(demo_reference, demo_test, tolerances=[LOOSE])
    rows = _rows(d)
    assert rows[("x", "loose")]["verdict"] == "pass"
    assert rows[("y", "loose")]["verdict"] == "pass"
    z = rows[("z", "loose")]
    assert z["verdict"] == "fail"
    assert z["status"] == -1 and z["status_name"] == "FAIL"
    assert z["points_compared"] == 1001
    assert z["points_outside"] > 0
    assert 0 < z["fraction_of_points_outside"] < 1
    assert set(z["worst"]) == {"x", "deviation", "difference", "tube_half_width_y"}
    assert d["totals"] == {"rows": 3, "passed": 2, "failed": 1, "errors": 0}
    # Passing rows carry only the headline: no zero counts, no intervals.
    assert rows[("x", "loose")] == {
        "column": "x", "tolerance_set": "loose", "verdict": "pass", "status": 0,
        "status_name": "PASS", "points_compared": 1001,
    }
    # Verdicts agree with calling the library directly.
    for col in ("x", "y", "z"):
        tol = funnel.Tolerances(atolx=0.1, atoly=0.1)
        assert rows[(col, "loose")]["status"] == _library_status(
            demo_reference, demo_test, col, tol
        )
    assert d["reference"]["time_column"] == "time"
    assert d["test"]["time_column_rule"] == "named time"


def test_intervals_worst_first_and_capped(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(demo_reference, demo_test, tolerances=[NOXTOL], columns=["y"], max_intervals=3)
    y = d["rows"][0]
    assert y["verdict"] == "fail"
    assert y["interval_count"] > 3
    assert len(y["intervals"]) == 3
    devs = [abs(iv["worst_deviation"]) for iv in y["intervals"]]
    assert devs == sorted(devs, reverse=True)
    assert abs(y["worst"]["deviation"]) == pytest.approx(devs[0])
    assert set(y["intervals"][0]) == {
        "start_x", "end_x", "direction", "point_count", "worst_deviation", "worst_x",
        "worst_difference",
    }
    text = compare_signals_impl(
        str(demo_reference), str(demo_test), [], tolerances=[NOXTOL], columns=["y"],
        max_intervals=3,
    ).content[0].text  # type: ignore[union-attr]
    assert f"... {y['interval_count'] - 3} more interval(s)" in text


def test_max_intervals_zero_keeps_count(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(demo_reference, demo_test, tolerances=[LOOSE], columns=["z"], max_intervals=0)
    z = d["rows"][0]
    assert z["intervals"] == []
    assert z["interval_count"] > 0


def test_default_interval_cap_is_five(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(demo_reference, demo_test, tolerances=[NOXTOL], columns=["y"])
    assert len(d["rows"][0]["intervals"]) == 5


def test_multiple_sets_one_row_per_column_and_set(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(demo_reference, demo_test, tolerances=[LOOSE, NOXTOL])
    assert len(d["rows"]) == 6
    rows = _rows(d)
    # Tolerance in x is what lets y pass.
    assert rows[("y", "loose")]["verdict"] == "pass"
    assert rows[("y", "noxtol")]["verdict"] == "fail"
    assert [s["label"] for s in d["tolerance_sets"]] == ["loose", "noxtol"]
    # Errors and failures come before passes.
    verdicts = [r["verdict"] for r in d["rows"]]
    assert verdicts == sorted(verdicts, key={"error": 0, "fail": 1, "pass": 2}.__getitem__)


def test_resolved_tolerances_come_from_the_library(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(
        demo_reference, demo_test, tolerances=[ToleranceSet(label="y1pct", rtoly=0.01)]
    )
    s = d["tolerance_sets"][0]
    assert s["given"] == {"rtoly": 0.01}
    assert s["resolved"] == {
        "atolx": 0.0, "atoly": 0.0, "ltolx": 0.0, "ltoly": 0.0, "rtolx": 0.0, "rtoly": 0.01
    }
    # Same as what summarize reports for that comparison.
    t = np.array([0.0, 1.0])
    opts = funnel.Options(tolerances=funnel.Tolerances(rtoly=0.01))
    lib = funnel.summarize(funnel.compare(t, t, t, t, opts), t, opts).tolerances
    assert s["resolved"]["rtolx"] == lib.rtolx


def test_no_sets_means_library_default(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(demo_reference, demo_test)
    s = d["tolerance_sets"]
    assert len(s) == 1 and s[0]["label"] == "default" and s[0]["given"] == {}
    default = funnel.default_options().tolerances
    assert s[0]["resolved"]["rtolx"] == default.rtolx
    assert s[0]["resolved"]["rtoly"] == default.rtoly
    assert s[0]["resolved"] == {
        "atolx": 0.0, "atoly": 0.0, "ltolx": 0.0, "ltoly": 0.0, "rtolx": 0.0, "rtoly": 0.002
    }
    assert d["totals"]["rows"] == 3


def test_unlabelled_sets_get_positional_labels(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(
        demo_reference, demo_test, columns=["x"],
        tolerances=[ToleranceSet(atoly=0.1), ToleranceSet(atoly=0.2)],
    )
    assert [s["label"] for s in d["tolerance_sets"]] == ["set1", "set2"]


def test_duplicate_labels_are_an_error(demo_reference: Path, demo_test: Path) -> None:
    with pytest.raises(ToolError, match="duplicate tolerance set label 'a'"):
        _compare(
            demo_reference, demo_test,
            tolerances=[ToleranceSet(label="a"), ToleranceSet(label="a", atoly=1)],
        )


def test_compose_override_is_axis_wise() -> None:
    base = {"atolx": 0.1, "atoly": 0.1}
    assert compose_override(base, ToleranceSpec(rtoly=0.5)) == {"atolx": 0.1, "rtoly": 0.5}
    assert compose_override(base, ToleranceSpec(ltolx=0.2)) == {"ltolx": 0.2, "atoly": 0.1}
    assert compose_override(base, None) == base


def test_column_override(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(
        demo_reference, demo_test, tolerances=[LOOSE],
        column_tolerances={"z": ToleranceSpec(rtoly=0.5)},
    )
    rows = _rows(d)
    z = rows[("z", "loose")]
    assert z["tolerances"] == {
        "atolx": 0.1, "atoly": 0.0, "ltolx": 0.0, "ltoly": 0.0, "rtolx": 0.0, "rtoly": 0.5
    }
    assert "tolerances" not in rows[("x", "loose")]
    assert z["status"] == _library_status(
        demo_reference, demo_test, "z", funnel.Tolerances(atolx=0.1, rtoly=0.5)
    )


def test_override_for_uncompared_column_is_noted(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(
        demo_reference, demo_test, columns=["x"], column_tolerances={"q": ToleranceSpec(atoly=1)}
    )
    assert any("override for column 'q' ignored" in n for n in d["notes"])


def test_x_range(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(
        demo_reference, demo_test, tolerances=[LOOSE], columns=["z"],
        x_range=XRange(lo=0.0, hi=0.4),
    )
    assert d["x_range"] == {"lo": 0.0, "hi": 0.4}
    z = d["rows"][0]
    assert z["points_compared"] == 401
    # The library is given the same window: full-range interval count differs.
    full = _compare(demo_reference, demo_test, tolerances=[LOOSE], columns=["z"])
    assert full["rows"][0]["points_compared"] == 1001
    assert all(iv["end_x"] <= 0.4 for iv in z.get("intervals", []))


def test_x_range_lo_above_hi_is_an_error(demo_reference: Path, demo_test: Path) -> None:
    with pytest.raises(ToolError, match="greater than hi"):
        _compare(demo_reference, demo_test, x_range=XRange(lo=1.0, hi=0.0))


def test_subset_and_missing_columns(demo_reference: Path, write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,x,q\n0,0,1\n1,1,1\n2,2,1\n")
    tst = write_csv("tst.csv", "time,x,r\n0,0,1\n1,1,1\n2,2,1\n")
    d = _compare(ref, tst, columns=["x", "q", "r", "nope"])
    rows = _rows(d)
    assert rows[("x", "default")]["verdict"] == "pass"
    q = rows[("q", "default")]
    assert (q["verdict"], q["status"], q["status_name"]) == ("error", 2, "MISSING_TEST")
    assert "absent from the test file" in q["problem"]
    r = rows[("r", "default")]
    assert (r["status"], r["status_name"]) == (1, "MISSING_REFERENCE")
    assert "absent from the reference file" in r["problem"]
    assert "absent from both" in rows[("nope", "default")]["problem"]
    assert d["totals"] == {"rows": 4, "passed": 1, "failed": 0, "errors": 3}


def test_default_selection_lists_one_sided_columns(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,a,b\n0,0,1\n1,1,1\n")
    tst = write_csv("tst.csv", "time,b,c\n0,1,1\n1,1,1\n")
    d = _compare(ref, tst)
    assert [r["column"] for r in d["rows"]] == ["b"]
    assert d["columns_only_in_reference"] == ["a"]
    assert d["columns_only_in_reference_count"] == 1
    assert d["columns_only_in_test"] == ["c"]


def test_no_common_columns(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,a\n0,0\n1,1\n")
    tst = write_csv("tst.csv", "time,c\n0,1\n1,1\n")
    d = _compare(ref, tst)
    assert d["rows"] == []
    assert any("no signal column in common" in n for n in d["notes"])


def test_non_numeric_column_does_not_fail_the_call(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,x,y\n0,0,0\n1,1,1\n2,2,2\n")
    tst = write_csv("tst.csv", "time,x,y\n0,0,0\n1,1,oops\n2,2,2\n")
    d = _compare(ref, tst)
    rows = _rows(d)
    y = rows[("y", "default")]
    assert y["verdict"] == "error"
    assert "status" not in y
    assert "1 in the test file" in y["problem"]
    assert rows[("x", "default")]["verdict"] == "pass"


def test_time_column_requested(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(demo_reference, demo_test, columns=["time"])
    assert "is the time column" in d["rows"][0]["problem"]


def test_non_monotonic_time_uses_library_status(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,x\n0,0\n2,1\n1,2\n3,3\n")
    tst = write_csv("tst.csv", "time,x\n0,0\n1,1\n2,2\n3,3\n")
    d = _compare(ref, tst)
    x = d["rows"][0]
    assert (x["verdict"], x["status_name"]) == ("error", "NON_MONOTONIC")
    assert x["problem"] == funnel.status_message(funnel.Status.NON_MONOTONIC)
    assert any("reference file: time column 'time' is not non-decreasing" in n for n in d["notes"])


def test_disjoint_time_ranges(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,x\n0,0\n1,1\n")
    tst = write_csv("tst.csv", "time,x\n2,0\n3,1\n")
    d = _compare(ref, tst)
    assert d["rows"][0]["verdict"] == "error"
    assert "status" in d["rows"][0]
    assert any(n.startswith("time ranges do not overlap") for n in d["notes"])


def test_partial_overlap_suggests_x_range(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,x\n0,0\n1,1\n2,2\n")
    tst = write_csv("tst.csv", "time,x\n0,0\n1,1\n2,2\n3,3\n")
    d = _compare(ref, tst)
    assert d["rows"][0]["status_name"] == "MISSING_REFERENCE"
    assert any("pass x_range" in n for n in d["notes"])


def test_different_time_column_names(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "t,x\n0,0\n1,1\n2,2\n")
    tst = write_csv("tst.csv", "x,Time\n0,0\n1,1\n2,2\n")
    d = _compare(ref, tst)
    assert d["reference"]["time_column"] == "t"
    assert d["test"]["time_column"] == "Time"
    assert d["rows"][0]["verdict"] == "pass"


def _wide(write_csv: WriteCsv, name: str, n_cols: int, offset: float) -> Path:
    t = np.linspace(0, 1, 50)
    header = "time," + ",".join(f"s{i}" for i in range(n_cols))
    lines = [header]
    for k, tk in enumerate(t):
        vals = [f"{tk:.6g}"] + [f"{np.sin(tk + i) + (offset if i % 50 == 0 else 0):.6g}"
                                for i in range(n_cols)]
        lines.append(",".join(vals))
        del k
    return write_csv(name, "\n".join(lines) + "\n")


def test_two_hundred_columns_are_capped(write_csv: WriteCsv) -> None:
    ref = _wide(write_csv, "ref.csv", 200, 0.0)
    tst = _wide(write_csv, "tst.csv", 200, 1.0)  # s0, s50, s100, s150 fail
    result = compare_signals_impl(str(ref), str(tst), [])
    d = structured(result)
    assert d["totals"] == {"rows": 200, "passed": 196, "failed": 4, "errors": 0}
    assert len(d["rows"]) == 100
    assert d["rows_omitted"] == 100
    assert [r["column"] for r in d["rows"][:4]] == ["s0", "s50", "s100", "s150"]
    size = len(json.dumps(d))
    text = result.content[0].text  # type: ignore[union-attr]
    print(f"200 columns: structured {size} B, text {len(text)} B")
    assert size < 16_000, size
    assert len(text) < 5_000, len(text)
    assert "100 row(s) omitted" in text
    small = structured(compare_signals_impl(str(ref), str(tst), [], max_rows=4))
    assert [r["verdict"] for r in small["rows"]] == ["fail"] * 4


def test_text_rendering(demo_reference: Path, demo_test: Path) -> None:
    result = compare_signals_impl(
        str(demo_reference), str(demo_test), [], tolerances=[LOOSE, NOXTOL]
    )
    text = result.content[0].text  # type: ignore[union-attr]
    assert "result: 3 fail, 0 error, 3 pass (6 rows)" in text
    assert "PASS [loose]: x, y" in text
    assert "PASS [noxtol]: x" in text
    assert "FAIL z [loose]:" in text
    assert "tolerance set loose: atolx=0.1 atoly=0.1 ltolx=0" in text
    assert "snippet" not in text
    assert "snippet" not in structured(result)


def test_longer_test_range_reports_counts_and_overlap_x_range(write_csv: WriteCsv) -> None:
    # Regression: every row was a bare MISSING_REFERENCE error and the note's
    # advice to pass x_range did not help (the library ignored it).
    t_ref = np.linspace(0.0, 1.0, 11)
    t_tst = np.linspace(0.0, 1.1, 12)
    ref = write_csv("ref.csv", "time,x\n" + "".join(f"{float(t)!r},{float(t)!r}\n" for t in t_ref))
    tst = write_csv("tst.csv", "time,x\n" + "".join(f"{float(t)!r},{float(t)!r}\n" for t in t_tst))
    d = _compare(ref, tst, tolerances=[LOOSE])
    x = d["rows"][0]
    assert (x["verdict"], x["status_name"]) == ("error", "MISSING_REFERENCE")
    assert x["points_compared"] == 11 and x["points_outside"] == 0
    assert "test covers time [0.0, 1.1]" in x["problem"]
    assert "reference covers time [0.0, 1.0]" in x["problem"]
    assert 'x_range {"lo": 0.0, "hi": 1.0} compares the overlap' in x["problem"]
    assert any('pass x_range {"lo": 0.0, "hi": 1.0}' in n for n in d["notes"])
    # Following the advice works.
    fixed = _compare(ref, tst, tolerances=[LOOSE], x_range=XRange(lo=0.0, hi=1.0))
    assert fixed["rows"][0]["verdict"] == "pass"
    assert not any("time ranges differ" in n for n in fixed["notes"])
    text = compare_signals_impl(
        str(ref), str(tst), [], tolerances=[LOOSE]
    ).content[0].text  # type: ignore[union-attr]
    assert "MISSING_REFERENCE (0/11 points outside)" in text


def test_longer_reference_range_within_requested_x_range(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,x\n0,0\n1,1\n2,2\n3,3\n")
    tst = write_csv("tst.csv", "time,x\n1,1\n2,2\n")
    d = _compare(ref, tst, x_range=XRange(lo=0.5))
    x = d["rows"][0]
    assert x["status_name"] == "MISSING_TEST"
    assert "within the requested x_range" in x["problem"]
    assert 'x_range {"lo": 1.0, "hi": 2.0}' in x["problem"]


def test_signal_column_named_time_next_to_time_column(write_csv: WriteCsv) -> None:
    # Regression: the internal key "time" collided with a signal column "time".
    ref = write_csv("ref.csv", "Time,time,a\n0,5,1\n1,6,2\n2,7,3\n")
    tst = write_csv("tst.csv", "Time,time,a\n0,5,1\n1,6,2\n2,9,3\n")
    d = _compare(ref, tst, tolerances=[ToleranceSet(atolx=0.0, atoly=0.1)])
    rows = _rows(d)
    assert d["reference"]["time_column"] == "Time"
    assert rows[("time", "set1")]["verdict"] == "fail"
    assert rows[("time", "set1")]["worst"]["x"] == 2.0
    assert rows[("a", "set1")]["verdict"] == "pass"


def test_columns_accept_glob_patterns(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,m.a.y,m.b.y,m.c.u,q\n0,0,0,0,0\n1,1,1,1,1\n")
    tst = write_csv("tst.csv", "time,m.a.y,m.b.y,m.c.u,r\n0,0,0,0,0\n1,1,1,1,1\n")
    d = _compare(ref, tst, columns=["m.*.y", "q", "z*"])
    assert [r["column"] for r in d["rows"] if r["verdict"] == "pass"] == ["m.a.y", "m.b.y"]
    assert _rows(d)[("q", "default")]["status_name"] == "MISSING_TEST"
    assert any("pattern 'z*' matched no signal column" in n for n in d["notes"])


def test_epoch_times_keep_full_precision(write_csv: WriteCsv) -> None:
    # Regression: 10-significant-digit rounding turned 1731628800.25 into
    # 1731628800.0 in structured content and 1.732e+09 in text.
    t0 = 1731628800.0
    times = [t0 + 0.25 * k for k in range(8)]
    ref = write_csv("ref.csv", "time,x\n" + "".join(f"{t!r},0\n" for t in times))
    vals = [0, 0, 0, 0, 0, 0, 0, 0]
    vals[1] = vals[2] = vals[3] = 5
    tst = write_csv(
        "tst.csv", "time,x\n" + "".join(f"{t!r},{v}\n" for t, v in zip(times, vals, strict=True))
    )
    result = compare_signals_impl(
        str(ref), str(tst), [], tolerances=[ToleranceSet(atolx=0.0, atoly=0.1)],
        x_range=XRange(lo=t0 + 0.25),
    )
    d = structured(result)
    iv = d["rows"][0]["intervals"][0]
    assert (iv["start_x"], iv["end_x"]) == (t0 + 0.25, t0 + 0.75)
    assert d["x_range"]["lo"] == t0 + 0.25
    assert d["reference"]["time_end"] == t0 + 1.75
    text = result.content[0].text  # type: ignore[union-attr]
    assert "t=1731628800.25..1731628800.75" in text
    assert "x_range 1731628800.25 .. -" in text


def test_non_finite_arguments_are_rejected() -> None:
    from pydantic import ValidationError

    for bad in ({"lo": "-inf"}, {"hi": 1e999}, {"lo": "nan"}):
        with pytest.raises(ValidationError):
            XRange.model_validate(bad)
    for bad_tol in ({"atoly": "inf"}, {"rtolx": float("nan")}):
        with pytest.raises(ValidationError):
            ToleranceSet.model_validate(bad_tol)


# --------------------------------------------------------------------------
# Default x tolerance (zero) and the hint on failed rows
# --------------------------------------------------------------------------

NO_X_HINT = "had no x (time) tolerance"


def _step_edge_files(write_csv: WriteCsv) -> tuple[Path, Path]:
    """The shared step-edge case: the test step is delayed by 0.001 in time."""
    t = np.arange(101) / 100.0
    y_ref = np.clip((t - 0.49) / 0.01, 0.0, 1.0)
    y_tst = np.clip((t - 0.491) / 0.01, 0.0, 1.0)

    def text(y: np.ndarray) -> str:
        return "time,y\n" + "".join(
            f"{float(a)!r},{float(b)!r}\n" for a, b in zip(t, y, strict=True)
        )

    return write_csv("ref.csv", text(y_ref)), write_csv("tst.csv", text(y_tst))


def test_default_has_no_x_tolerance_and_shifted_edge_fails(write_csv: WriteCsv) -> None:
    ref, tst = _step_edge_files(write_csv)
    d = _compare(ref, tst)
    assert d["tolerance_sets"][0]["resolved"] == {
        "atolx": 0.0, "atoly": 0.0, "ltolx": 0.0, "ltoly": 0.0, "rtolx": 0.0, "rtoly": 0.002
    }
    assert d["rows"][0]["verdict"] == "fail"
    hints = [n for n in d["notes"] if NO_X_HINT in n]
    assert hints == [
        "1 failing row(s) had no x (time) tolerance: none was given and the default is 0. "
        "If the test may be shifted or delayed in time against the reference (e.g. at "
        "steep edges), consider an x tolerance such as atolx (time units)"
    ]
    # The text rendering shows the note too.
    text = compare_signals_impl(str(ref), str(tst), []).content[0].text  # type: ignore[union-attr]
    assert NO_X_HINT in text
    # With an explicit x tolerance the shifted edge passes and there is no hint.
    ok = _compare(ref, tst, tolerances=[ToleranceSet(atolx=0.002)])
    assert ok["rows"][0]["verdict"] == "pass"
    assert not any(NO_X_HINT in n for n in ok["notes"])


def test_no_x_hint_only_for_failures_without_x_given(write_csv: WriteCsv) -> None:
    ref, tst = _step_edge_files(write_csv)
    sets = [
        ToleranceSet(label="only_y", atoly=0.05),  # fails, no x given -> counted
        ToleranceSet(label="zero_x", atolx=0, atoly=0.05),  # fails, x given as 0 -> not
        ToleranceSet(label="with_x", atolx=0.002, atoly=0.05),  # passes -> not
    ]
    d = _compare(ref, tst, tolerances=sets)
    rows = _rows(d)
    assert [rows[("y", s)]["verdict"] for s in ("only_y", "zero_x", "with_x")] == [
        "fail", "fail", "pass"
    ]
    hints = [n for n in d["notes"] if NO_X_HINT in n]
    assert len(hints) == 1 and hints[0].startswith("1 failing row(s)")
    # A per-column override that gives an x coefficient counts as x given.
    over = _compare(
        ref, tst, tolerances=[sets[0]], column_tolerances={"y": ToleranceSpec(atolx=0)}
    )
    assert over["rows"][0]["verdict"] == "fail"
    assert not any(NO_X_HINT in n for n in over["notes"])


def test_no_x_hint_absent_when_everything_passes(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(demo_reference, demo_test, tolerances=[ToleranceSet(atoly=10.0)])
    assert d["totals"]["failed"] == 0
    assert not any(NO_X_HINT in n for n in d["notes"])


# --------------------------------------------------------------------------
# Prerequisite: no default x tolerance (zero-default-x-tolerance)
# --------------------------------------------------------------------------


def test_default_x_tolerance_resolves_to_zero() -> None:
    c = resolve_with_library({})
    assert (c.atolx, c.ltolx, c.rtolx, c.rtoly) == (0.0, 0.0, 0.0, 0.002)


# --------------------------------------------------------------------------
# Column pairs
# --------------------------------------------------------------------------

DAYS = (1, 3, 5)
C2 = ToleranceSet(label="2C", atoly=2)
C2_3H = ToleranceSet(label="2C_3h", atoly=2, atolx=10800)


def _day_pairs(*days: int) -> list[ColumnPair]:
    return [
        ColumnPair(reference=OPEN_METEO_REF, test=open_meteo_column(d), label=f"day{d}")
        for d in days
    ]


def _om(path: Path, **kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("header_line", 4)
    return structured(compare_signals_impl(str(path), None, [], **kwargs))


def test_forecasts_against_the_latest_run_in_one_file(open_meteo: Path) -> None:
    d = _om(open_meteo, pairs=_day_pairs(*DAYS), tolerances=[C2, C2_3H])
    assert d["totals"]["rows"] == 6
    rows = _rows(d)
    assert set(rows) == {(f"day{k}", s) for k in DAYS for s in ("2C", "2C_3h")}
    for k in DAYS:
        r = rows[(f"day{k}", "2C")]
        assert r["reference_column"] == OPEN_METEO_REF
        assert r["test_column"] == open_meteo_column(k)
    # The day-1 forecast is close, the day-5 one is not; 3 h in x helps.
    assert rows[("day1", "2C")]["verdict"] == "pass"
    assert rows[("day5", "2C")]["points_outside"] > rows[("day5", "2C_3h")]["points_outside"]
    # One file: same file named as reference and test, read once.
    assert d["reference"]["path"] == d["test"]["path"] == str(open_meteo)
    assert d["reference"]["header_line"] == d["test"]["header_line"] == 4
    assert "columns_only_in_reference" not in d and "columns_only_in_test" not in d
    # Equal to comparing the columns with the library directly.
    from simtest_funnel_mcp.csvio import load_csv

    sf = load_csv(open_meteo, 4)
    lib = funnel.compare(
        sf.time, sf.values[OPEN_METEO_REF], sf.time, sf.values[open_meteo_column(5)],
        funnel.Options(tolerances=funnel.Tolerances(atoly=2.0, atolx=10800.0)),
    )
    assert rows[("day5", "2C_3h")]["status"] == lib.status


def test_pair_rows_are_rendered_with_both_names(open_meteo: Path) -> None:
    text = compare_signals_impl(
        str(open_meteo), None, [], header_line=4, pairs=_day_pairs(1, 5), tolerances=[C2]
    ).content[0].text  # type: ignore[union-attr]
    assert (
        "FAIL day5 (temperature_2m (°C) -> temperature_2m_previous_day5 (°C)) [2C]:" in text
    )
    assert "PASS [2C]: day1 (temperature_2m (°C) -> temperature_2m_previous_day1 (°C))" in text


def test_override_addressed_by_label(open_meteo: Path) -> None:
    d = _om(
        open_meteo, pairs=_day_pairs(1, 3), tolerances=[C2],
        column_tolerances={"day3": ToleranceSpec(atoly=3)},
    )
    rows = _rows(d)
    assert rows[("day3", "2C")]["tolerances"]["atoly"] == 3.0
    assert "tolerances" not in rows[("day1", "2C")]
    assert not any("ignored" in n for n in d["notes"])


def test_override_addressed_by_test_column(write_csv: WriteCsv) -> None:
    p = write_csv("a.csv", "time,b,b_model,c\n0,0,0,0\n1,1,1.5,1\n2,2,2,2\n")
    d = structured(
        compare_signals_impl(
            str(p), None, [], pairs=[ColumnPair(reference="b", test="b_model")],
            tolerances=[ToleranceSet(atoly=0.1)],
            column_tolerances={"b_model": ToleranceSpec(atoly=1), "b": ToleranceSpec(atoly=9)},
        )
    )
    (row,) = d["rows"]
    assert row["column"] == "b_model" and row["verdict"] == "pass"
    assert row["tolerances"]["atoly"] == 1.0
    assert any("override for column 'b' ignored" in n for n in d["notes"])


def test_clashing_keys(write_csv: WriteCsv) -> None:
    p = write_csv("a.csv", "time,a,b,x\n0,0,0,0\n1,1,1,1\n")
    with pytest.raises(ToolError, match="row key 'x' is used by more than one pair.*labels"):
        compare_signals_impl(
            str(p), None, [],
            pairs=[ColumnPair(reference="a", test="x"), ColumnPair(reference="b", test="x")],
        )
    with pytest.raises(ToolError, match="row key 'x'"):
        compare_signals_impl(
            str(p), None, [],
            pairs=[ColumnPair(reference="a", test="x"),
                   ColumnPair(reference="b", test="a", label="x")],
        )


def test_pairs_together_with_columns(open_meteo: Path) -> None:
    with pytest.raises(ToolError, match="pairs and columns cannot be combined"):
        _om(open_meteo, pairs=_day_pairs(1), columns=[OPEN_METEO_REF])
    with pytest.raises(ToolError, match="pairs is empty"):
        _om(open_meteo, pairs=[])


def test_pattern_in_a_pair(open_meteo: Path) -> None:
    pair = ColumnPair(reference=OPEN_METEO_REF, test="temperature_2m_previous_day*")
    (row,) = _om(open_meteo, pairs=[pair])["rows"]
    assert (row["verdict"], row["status_name"]) == ("error", "MISSING_TEST")
    assert "pairs take exact names, use columns for patterns" in row["problem"]


def test_name_without_the_unit_suffix(open_meteo: Path) -> None:
    pair = ColumnPair(reference="temperature_2m", test=open_meteo_column(1))
    (row,) = _om(open_meteo, pairs=[pair])["rows"]
    assert (row["verdict"], row["status_name"]) == ("error", "MISSING_REFERENCE")
    assert row["problem"].startswith(
        "column 'temperature_2m' absent from the reference file; did you mean "
        "'temperature_2m (°C)'"
    )


def test_time_column_in_a_pair(open_meteo: Path) -> None:
    (row,) = _om(open_meteo, pairs=[ColumnPair(reference="time", test=OPEN_METEO_REF)])["rows"]
    assert row["verdict"] == "error" and "is the time column" in row["problem"]


def test_pair_of_a_column_with_itself_in_one_file_is_refused(
    open_meteo: Path, write_csv: WriteCsv
) -> None:
    """It would pass trivially: an error row, the other pairs still compared."""
    pairs = [ColumnPair(reference=OPEN_METEO_REF, test=OPEN_METEO_REF, label="self"),
             *_day_pairs(1)]
    rows = {r["column"]: r for r in _om(open_meteo, pairs=pairs)["rows"]}
    assert rows["self"]["verdict"] == "error"
    assert "compared with itself" in rows["self"]["problem"]
    assert "Pass test_path" in rows["self"]["problem"]
    assert rows["day1"]["verdict"] != "error"
    # The same file given as test_path is the same loaded file: refused too.
    ref = write_csv("ref.csv", "time,y\n0,0\n1,1\n")
    (row,) = _compare(ref, ref, pairs=[ColumnPair(reference="y", test="y")])["rows"]
    assert row["verdict"] == "error" and "compared with itself" in row["problem"]
    # Two files with the same column name: compared.
    tst = write_csv("tst.csv", "time,y\n0,0\n1,1\n")
    (row,) = _compare(ref, tst, pairs=[ColumnPair(reference="y", test="y")])["rows"]
    assert row["verdict"] == "pass"


def test_same_name_rows_have_no_pair_fields(demo_reference: Path, demo_test: Path) -> None:
    for kwargs in ({}, {"columns": ["z"]}):
        d = _compare(demo_reference, demo_test, **kwargs)
        assert all("reference_column" not in r and "test_column" not in r for r in d["rows"])


def test_pairs_across_two_files(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,plant.y\n0,0\n1,1\n2,2\n")
    tst = write_csv("tst.csv", "time,model.y\n0,0\n1,1\n2,5\n")
    d = _compare(ref, tst, pairs=[ColumnPair(reference="plant.y", test="model.y")],
                 tolerances=[ToleranceSet(atoly=0.1)])
    (row,) = d["rows"]
    assert row["column"] == "model.y" and row["verdict"] == "fail"
    assert d["reference"]["path"] != d["test"]["path"]


def test_no_test_path_and_no_pairs(demo_reference: Path) -> None:
    with pytest.raises(ToolError, match="Pass test_path, or pairs"):
        compare_signals_impl(str(demo_reference), None, [])
    with pytest.raises(ToolError, match="compared with itself"):
        compare_signals_impl(str(demo_reference), None, [], columns=["x"])


def test_separate_and_default_test_header_line(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", open_meteo_text())
    plain = write_csv("plain.csv", open_meteo_text(preamble=False))
    pairs = _day_pairs(1)
    d = structured(compare_signals_impl(
        str(ref), str(plain), [], header_line=4, test_header_line=1, pairs=pairs))
    assert (d["reference"]["header_line"], d["test"]["header_line"]) == (4, 1)
    assert d["rows"][0]["verdict"] != "error"
    # Without test_header_line the test file is also read from line 4: here
    # that skips three data rows of the plain file.
    d4 = structured(compare_signals_impl(str(ref), str(plain), [], header_line=4, pairs=pairs))
    assert d4["test"]["header_line"] == 4
    # Line 4 (the 3rd data row) becomes the header: 357 rows remain.
    assert d4["test"]["row_count"] == 360 - 3
    # Test file with the preamble, reference plain: the hint names test_header_line.
    with pytest.raises(ToolError) as info:
        compare_signals_impl(str(plain), str(ref), [], pairs=pairs)
    assert "the time axes do not match" in str(info.value)
    assert "pass test_header_line=4" in str(info.value)


# --------------------------------------------------------------------------
# Date-time time axis
# --------------------------------------------------------------------------


def test_iso_file_and_unixtime_twin_give_identical_results(write_csv: WriteCsv) -> None:
    iso = write_csv("iso.csv", open_meteo_text())
    num = write_csv("num.csv", open_meteo_text(iso=False))
    kwargs: dict[str, Any] = {
        "pairs": _day_pairs(*DAYS), "tolerances": [C2, C2_3H], "header_line": 4,
        "max_intervals": 100,
    }
    a = structured(compare_signals_impl(str(iso), None, [], **kwargs))
    b = structured(compare_signals_impl(str(num), None, [], **kwargs))

    def strip(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: strip(x) for k, x in v.items()
                    if not k.endswith("_iso") and k not in ("path", "time_kind", "time_zone",
                                                            "time_tolerance")}
        if isinstance(v, list):
            return [strip(x) for x in v]
        return v

    assert strip(a["rows"]) == strip(b["rows"])
    assert a["totals"] == b["totals"]
    assert strip(a["tolerance_sets"]) == strip(b["tolerance_sets"])
    assert a["rows"][0]["intervals"][0]["start_x_iso"].startswith("2026-11-")


def _hourly(write_csv: WriteCsv, name: str, values: list[float], zone: str = "",
            start_hour: int = 0) -> Path:
    rows = "".join(
        f"2026-11-20T{start_hour + h:02d}:00{zone},{v!r}\n" for h, v in enumerate(values)
    )
    return write_csv(name, "time,y\n" + rows)


def test_three_hours_in_x(write_csv: WriteCsv) -> None:
    # A peak shifted by 2 hours: atolx = 10800 s (3 h) forgives it, atolx = 0 does not.
    base = [0.0] * 24
    ref_v, tst_v = list(base), list(base)
    ref_v[10] = 10.0
    tst_v[12] = 10.0
    ref = _hourly(write_csv, "ref.csv", ref_v)
    tst = _hourly(write_csv, "tst.csv", tst_v)
    d = _compare(ref, tst, tolerances=[ToleranceSet(label="3h", atoly=2, atolx=10800),
                                       ToleranceSet(label="0h", atoly=2, atolx=0)])
    rows = _rows(d)
    assert rows[("y", "3h")]["verdict"] == "pass"
    assert rows[("y", "0h")]["verdict"] == "fail"
    assert d["tolerance_sets"][0]["time_tolerance"] == {"seconds": 10800.0, "duration": "PT3H"}
    assert "time_tolerance" not in d["tolerance_sets"][1]


def test_explicit_rtolx_on_dates_is_echoed_as_a_duration(open_meteo: Path) -> None:
    d = _om(open_meteo, pairs=_day_pairs(1), tolerances=[ToleranceSet(rtolx=0.01)])
    s = d["tolerance_sets"][0]
    assert s["resolved"]["rtolx"] == 0.01
    assert s["time_tolerance"]["seconds"] == pytest.approx(12924.0)
    assert s["time_tolerance"]["duration"] == "PT3H35M24S"
    text = compare_signals_impl(
        str(open_meteo), None, [], header_line=4, pairs=_day_pairs(1),
        tolerances=[ToleranceSet(rtolx=0.01)],
    ).content[0].text  # type: ignore[union-attr]
    assert "time tolerance 12924 s (PT3H35M24S)" in text


def test_x_override_on_dates_echoes_the_row_time_tolerance(open_meteo: Path) -> None:
    d = _om(open_meteo, pairs=_day_pairs(1, 5), tolerances=[C2],
            column_tolerances={"day5": ToleranceSpec(atolx=7200)})
    rows = _rows(d)
    assert rows[("day5", "2C")]["time_tolerance"] == {"seconds": 7200.0, "duration": "PT2H"}
    assert "time_tolerance" not in rows[("day1", "2C")]


def test_ltolx_on_dates(open_meteo: Path) -> None:
    with pytest.raises(ToolError, match="ltolx = 0.001 in tolerance set 'set1'.*atolx"):
        _om(open_meteo, pairs=_day_pairs(1), tolerances=[ToleranceSet(ltolx=0.001)])
    with pytest.raises(ToolError, match=r"ltolx = 0.5 in column_tolerances\['day1'\]"):
        _om(open_meteo, pairs=_day_pairs(1),
            column_tolerances={"day1": ToleranceSpec(ltolx=0.5)})
    ok = _om(open_meteo, pairs=_day_pairs(1), tolerances=[ToleranceSet(ltolx=0, atoly=2)])
    assert ok["rows"][0]["verdict"] == "pass"


def test_both_without_time_zone_compare_normally(write_csv: WriteCsv) -> None:
    ref = _hourly(write_csv, "ref.csv", [0.0, 1.0, 2.0])
    tst = _hourly(write_csv, "tst.csv", [0.0, 1.0, 2.0])
    d = _compare(ref, tst)
    assert d["rows"][0]["verdict"] == "pass"
    assert d["reference"]["time_zone"] == "none"
    assert d["reference"]["time_start_iso"] == "2026-11-20T00:00:00"


def test_zone_less_against_offsets(write_csv: WriteCsv) -> None:
    ref = _hourly(write_csv, "ref.csv", [0.0, 1.0])
    tst = _hourly(write_csv, "tst.csv", [0.0, 1.0], zone="Z")
    with pytest.raises(ToolError) as info:
        _compare(ref, tst)
    msg = str(info.value)
    assert str(ref) in msg and str(tst) in msg
    assert "without time zone" in msg and "with time zone offsets" in msg
    assert "write both with offsets (e.g. 'Z' for UTC), or both without" in msg


def test_numeric_against_date_time(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,y\n1795132800,0\n1795136400,1\n")
    tst = _hourly(write_csv, "tst.csv", [0.0, 1.0])
    with pytest.raises(ToolError, match="is numeric, test .* is ISO 8601 date-times"):
        _compare(ref, tst)


def test_mixed_offsets_make_rows_errors(write_csv: WriteCsv) -> None:
    ref = write_csv("ref.csv", "time,y\n2026-11-20T00:00,0\n2026-11-20T01:00Z,1\n")
    d = _compare(ref, ref)
    row = d["rows"][0]
    assert row["verdict"] == "error" and "mixes timestamps" in row["problem"]
    assert any("mixes timestamps with and without a time zone" in n for n in d["notes"])


def test_iso_bounds(open_meteo: Path) -> None:
    d = _om(open_meteo, pairs=_day_pairs(5), tolerances=[C2],
            x_range=XRange(lo="2026-11-05T00:00", hi="2026-11-10T00:00"))
    assert d["x_range"] == {
        "lo": 1793836800.0, "lo_iso": "2026-11-05T00:00:00",
        "hi": 1794268800.0, "hi_iso": "2026-11-10T00:00:00",
    }
    assert d["rows"][0]["points_compared"] == 5 * 24 + 1
    # Numeric bounds are epoch seconds and give the same result.
    same = _om(open_meteo, pairs=_day_pairs(5), tolerances=[C2],
               x_range=XRange(lo=1793836800, hi=1794268800))
    assert same["rows"] == d["rows"]


def test_iso_bounds_on_an_offset_axis(write_csv: WriteCsv) -> None:
    ref = _hourly(write_csv, "ref.csv", [0.0, 1.0, 2.0, 3.0], zone="+01:00")
    d = _compare(ref, ref, x_range=XRange(lo="2026-11-20T00:00Z"))
    assert d["x_range"]["lo_iso"] == "2026-11-20T00:00:00Z"
    # Cells 00:00..03:00+01:00 are 23:00Z (19th) .. 02:00Z; three are >= 00:00Z.
    assert d["rows"][0]["points_compared"] == 3
    with pytest.raises(ToolError, match="has no time zone, but the time columns have offsets"):
        _compare(ref, ref, x_range=XRange(lo="2026-11-20T00:00"))
    zone_less = _hourly(write_csv, "zl.csv", [0.0, 1.0])
    with pytest.raises(ToolError, match="has a time zone, but the time columns have none"):
        _compare(zone_less, zone_less, x_range=XRange(hi="2026-11-20T00:00Z"))


def test_iso_bound_on_a_numeric_axis(demo_reference: Path, demo_test: Path) -> None:
    with pytest.raises(ToolError, match="the time columns are numeric"):
        _compare(demo_reference, demo_test, x_range=XRange(lo="2026-11-05T00:00"))


def test_x_range_strings_are_validated() -> None:
    from pydantic import ValidationError

    assert XRange.model_validate({"lo": "2026-11-05T00:00"}).lo == "2026-11-05T00:00"
    assert XRange.model_validate({"lo": "0.5"}).lo == 0.5  # numeric strings as before
    for bad in ({"lo": "-inf"}, {"hi": "yesterday"}, {"lo": "2026-11-05T25:00x"}):
        with pytest.raises(ValidationError):
            XRange.model_validate(bad)


def test_zero_x_tolerance_on_epoch_data_matches_data_shifted_to_zero(
    write_csv: WriteCsv,
) -> None:
    t0 = 1795132800
    t = np.arange(200) * 0.5
    y_ref = np.sin(t / 7.0)
    y_tst = y_ref + np.where((t > 30) & (t < 34), 0.3, 0.0)

    def text(times: np.ndarray, y: np.ndarray) -> str:
        return "time,y\n" + "".join(f"{a!r},{b!r}\n" for a, b in zip(times.tolist(), y.tolist()))

    tol = [ToleranceSet(atoly=0.1, atolx=0)]
    epoch = _compare(write_csv("er.csv", text(t + t0, y_ref)),
                     write_csv("et.csv", text(t + t0, y_tst)), tolerances=tol)
    zero = _compare(write_csv("zr.csv", text(t, y_ref)),
                    write_csv("zt.csv", text(t, y_tst)), tolerances=tol)
    keys = ("verdict", "status", "points_compared", "points_outside", "interval_count")
    assert [epoch["rows"][0][k] for k in keys] == [zero["rows"][0][k] for k in keys]


def test_failing_interval_on_a_date_axis(write_csv: WriteCsv) -> None:
    ref_v = [0.0] * 12
    tst_v = [5.0 if 3 <= h <= 7 else 0.0 for h in range(12)]
    ref = _hourly(write_csv, "ref.csv", ref_v)
    tst = _hourly(write_csv, "tst.csv", tst_v)
    result = compare_signals_impl(str(ref), str(tst), [], tolerances=[ToleranceSet(atoly=1)])
    iv = structured(result)["rows"][0]["intervals"][0]
    assert (iv["start_x"], iv["start_x_iso"]) == (1795143600.0, "2026-11-20T03:00:00")
    assert (iv["end_x"], iv["end_x_iso"]) == (1795158000.0, "2026-11-20T07:00:00")
    assert iv["worst_x_iso"].startswith("2026-11-20T0")
    assert structured(result)["rows"][0]["worst"]["x_iso"].startswith("2026-11-20T0")
    text = result.content[0].text  # type: ignore[union-attr]
    assert "t=2026-11-20T03:00:00..2026-11-20T07:00:00" in text
    assert "atolx = 10800 for 3 h" in text  # the no-x-tolerance hint in seconds


def test_numeric_axis_output_has_no_iso_fields(demo_reference: Path, demo_test: Path) -> None:
    d = _compare(demo_reference, demo_test, tolerances=[NOXTOL])
    blob = json.dumps(d)
    assert "_iso" not in blob and "time_tolerance" not in blob and "time_zone" not in blob
    assert d["reference"]["time_kind"] == "numeric" and d["reference"]["header_line"] == 1


# --------------------------------------------------------------------------
# x_range: the tube is built from the reference beyond the window
# --------------------------------------------------------------------------

HOUR = 3600.0
DAY = 86400.0
T0 = 1793491200.0  # 2026-11-01T00:00 (no time zone, read as UTC)
SHIFT_3H = ToleranceSet(label="3h", atolx=10800, atoly=0.05)


def _daily_cycle_csv(write_csv: WriteCsv, name: str, delay_h: float) -> Path:
    """Hourly daily temperature cycle over 6 days, ``delay_h`` hours late."""
    import datetime as dt

    lines = ["time,temperature"]
    for h in range(145):
        s = h * HOUR
        v = 10.0 + 5.0 * np.cos(2.0 * np.pi * (s - (14.0 + delay_h) * HOUR) / DAY)
        stamp = dt.datetime(2026, 11, 1) + dt.timedelta(hours=h)
        lines.append(f"{stamp:%Y-%m-%dT%H:%M},{v:.12g}")
    return write_csv(name, "\n".join(lines) + "\n")


def _window(ref: Path, tst: Path, lo: float | None, hi: float | None) -> dict[str, Any]:
    x_range = None if lo is None and hi is None else XRange(lo=lo, hi=hi)
    d = _compare(ref, tst, tolerances=[SHIFT_3H], x_range=x_range)
    row: dict[str, Any] = d["rows"][0]
    return row


def test_x_range_shift_within_atolx_passes_at_window_edges(write_csv: WriteCsv) -> None:
    ref = _daily_cycle_csv(write_csv, "ref.csv", 0.0)
    tst = _daily_cycle_csv(write_csv, "test.csv", 2.0)
    # The whole files fail only in the first hours (no earlier reference).
    full = _window(ref, tst, None, None)
    assert full["verdict"] == "fail"
    assert all(iv["end_x"] < T0 + 3 * HOUR for iv in full["intervals"])
    # A 2-day window: the 2 h delay is inside the 3 h tolerance at both edges.
    row = _window(ref, tst, T0 + 2 * DAY, T0 + 4 * DAY)
    assert row["verdict"] == "pass"
    assert row["points_compared"] == 49 and not row.get("points_outside")
    # ISO bounds give the same row.
    iso = _compare(ref, tst, tolerances=[SHIFT_3H],
                   x_range=XRange(lo="2026-11-03T00:00", hi="2026-11-05T00:00"))
    assert iso["rows"][0] == row


def test_x_range_window_edges_cases(write_csv: WriteCsv) -> None:
    ref = _daily_cycle_csv(write_csv, "ref.csv", 0.0)
    tst = _daily_cycle_csv(write_csv, "test.csv", 2.0)
    end = T0 + 144 * HOUR
    # Narrower than the x tolerance (two samples, 1 h).
    narrow = _window(ref, tst, T0 + 2.5 * DAY, T0 + 2.5 * DAY + HOUR)
    assert (narrow["verdict"], narrow["points_compared"]) == ("pass", 2)
    # At the data start nothing is extended: fails there as the whole files do.
    assert _window(ref, tst, T0, T0 + DAY)["verdict"] == "fail"
    assert _window(ref, tst, T0 + 3 * HOUR, T0 + DAY)["verdict"] == "pass"
    # Partly outside the data: compared on the overlap.
    part = _window(ref, tst, end - DAY, end + DAY)
    assert (part["verdict"], part["points_compared"]) == ("pass", 25)
    # Wholly outside the data, even within the tolerance of its end.
    outside = _window(ref, tst, end + HOUR / 2, end + 2 * HOUR)
    assert outside["verdict"] == "error"


# --------------------------------------------------------------------------
# Test minus reference at the worst points; notes on record edges and spans
# --------------------------------------------------------------------------


def _signal_csv(t: np.ndarray, y: np.ndarray) -> str:
    return "time,value\n" + "".join(f"{float(a)!r},{float(b)!r}\n" for a, b in zip(t, y, strict=True))


def test_difference_on_the_open_meteo_sample() -> None:
    from conftest import OPEN_METEO_SAMPLE

    if not OPEN_METEO_SAMPLE.is_file():
        pytest.skip("the bundled sample (repository examples/) is not present")
    day3 = "temperature_2m_previous_day3 (°C)"
    d = structured(compare_signals_impl(
        str(OPEN_METEO_SAMPLE), None, [], header_line=4,
        pairs=[ColumnPair(reference=OPEN_METEO_REF, test=day3, label="day3")],
        tolerances=[ToleranceSet(label="2C_3h", atoly=2, atolx=10800)],
    ))
    row = d["rows"][0]
    worst = row["worst"]
    assert worst["x_iso"] == "2026-11-19T04:00:00"
    assert worst["deviation"] == -0.9 and worst["tube_half_width_y"] == 2.15
    # Independent: both columns share the hourly time column, so the
    # difference is the plain difference of the two cells in that row.
    import csv

    with OPEN_METEO_SAMPLE.open(encoding="utf-8") as fh:
        lines = fh.read().splitlines()[3:]
    table = list(csv.DictReader(lines))
    cells = {r["time"]: r for r in table}
    for x_iso, diff in [(worst["x_iso"], worst["difference"])] + [
        (iv["worst_x_iso"], iv["worst_difference"]) for iv in row["intervals"]
    ]:
        r = cells[x_iso[:16]]
        assert diff == pytest.approx(float(r[day3]) - float(r[OPEN_METEO_REF]), abs=1e-9)
    assert worst["difference"] == pytest.approx(-3.0)
    # deviation (outside the tube) and half-width bracket the difference.
    assert abs(worst["difference"]) <= abs(worst["deviation"]) + worst["tube_half_width_y"] + 1e-9
    text = compare_signals_impl(
        str(OPEN_METEO_SAMPLE), None, [], header_line=4,
        pairs=[ColumnPair(reference=OPEN_METEO_REF, test=day3, label="day3")],
        tolerances=[ToleranceSet(label="2C_3h", atoly=2, atolx=10800)],
    ).content[0].text  # type: ignore[union-attr]
    assert (
        "worst -0.9 outside the tube at t=2026-11-19T04:00:00 (test - reference -3, "
        "tube half-width 2.15)"
    ) in text
    assert "(6 pts, worst -0.9 at t=2026-11-19T04:00:00, test - reference -3)" in text


def test_difference_interpolates_the_reference_like_the_library(write_csv: WriteCsv) -> None:
    # Reference on integer times with a step at t=3 (repeated time), test
    # half a step later: the reference is interpolated at the test's x.
    t_ref = np.array([0.0, 1.0, 2.0, 3.0, 3.0, 4.0, 5.0])
    y_ref = np.array([0.0, 1.0, 2.0, 3.0, 10.0, 10.0, 10.0])
    t_tst = np.array([0.0, 0.5, 1.5, 2.5, 3.0, 3.5, 4.5, 5.0])
    y_tst = np.array([0.0, 0.5, 1.5, 4.0, 3.0, 10.0, 12.5, 10.0])
    ref = write_csv("ref.csv", _signal_csv(t_ref, y_ref))
    tst = write_csv("tst.csv", _signal_csv(t_tst, y_tst))
    d = _compare(ref, tst, tolerances=[ToleranceSet(atoly=0.1)], max_intervals=10)
    row = d["rows"][0]
    expected = {2.5: 4.0 - 2.5, 4.5: 12.5 - 10.0}
    assert row["worst"]["x"] == 4.5 and row["worst"]["difference"] == pytest.approx(2.5)
    got = {iv["worst_x"]: iv["worst_difference"] for iv in row["intervals"]}
    assert got == pytest.approx(expected)


def _edge_files(write_csv: WriteCsv, shift: float, bump: bool = False) -> tuple[Path, Path]:
    """Reference sin(t) at 0.05 from 0 to 10, test shifted by ``shift``
    (positive: delayed), optionally with a +0.2 bump at 6 <= t <= 6.5."""
    t = np.round(np.arange(201) * 0.05, 10)
    y = np.sin(t - shift) + (0.2 * ((t >= 6) & (t <= 6.5)) if bump else 0.0)
    return write_csv("ref.csv", _signal_csv(t, np.sin(t))), write_csv("tst.csv", _signal_csv(t, y))


def _edge_note(d: dict[str, Any]) -> list[str]:
    return [n for n in d["notes"] if "of the first or last reference sample" in n]


def test_record_edge_note_for_a_delayed_test(write_csv: WriteCsv) -> None:
    ref, tst = _edge_files(write_csv, 0.1)
    d = _compare(ref, tst, tolerances=[
        ToleranceSet(label="edge", atoly=0.06, atolx=0.15),
        ToleranceSet(label="noxtol", atoly=0.03),
    ])
    rows = _rows(d)
    edge = rows[("value", "edge")]
    assert edge["verdict"] == "fail" and edge["points_outside"] == 1
    assert edge["intervals"][0]["start_x"] == edge["intervals"][0]["end_x"] == 0.0
    notes = _edge_note(d)
    assert notes == [
        "1 failing row(s) with an x (time) tolerance fail within one x half-width of the "
        "first or last reference sample (value [edge]). There the tube cannot use the x "
        "tolerance fully: the reference has no samples before its first (or after its last) "
        "to shift against, so a delayed (or advanced) test can leave the tube at the start "
        "(or end) of the record. If that edge is a row's only failure, exclude it with "
        'x_range (e.g. {"lo": 0.15} for value [edge]) or accept it'
    ]
    # The suggested x_range removes exactly that failure.
    windowed = _compare(ref, tst, tolerances=[ToleranceSet(label="edge", atoly=0.06, atolx=0.15)],
                        x_range=XRange(lo=0.15))
    assert windowed["rows"][0]["verdict"] == "pass" and not _edge_note(windowed)


def test_record_edge_note_at_the_end_for_an_advanced_test(write_csv: WriteCsv) -> None:
    ref, tst = _edge_files(write_csv, -0.1)
    d = _compare(ref, tst, tolerances=[ToleranceSet(label="edge", atoly=0.06, atolx=0.15)])
    assert d["rows"][0]["verdict"] == "fail"
    (note,) = _edge_note(d)
    assert '{"hi": 9.85}' in note


def test_no_record_edge_note_for_failures_elsewhere(write_csv: WriteCsv) -> None:
    ref, tst = _edge_files(write_csv, 0.0, bump=True)
    d = _compare(ref, tst, tolerances=[
        ToleranceSet(label="bump", atoly=0.05, atolx=0.1),
        ToleranceSet(label="noxtol", atoly=0.05),
    ])
    rows = _rows(d)
    assert rows[("value", "bump")]["verdict"] == "fail"
    assert all(6 <= iv["start_x"] <= 6.5 for iv in rows[("value", "bump")]["intervals"])
    assert _edge_note(d) == []


def test_differing_spans_note_when_the_overlap_fails(write_csv: WriteCsv) -> None:
    t = np.round(np.arange(201) * 0.05, 10)
    short = t[t <= 8.0]
    ref = write_csv("ref.csv", _signal_csv(t, np.sin(t)))
    bad = write_csv("bad.csv", _signal_csv(short, np.sin(short) + 0.2 * (short > 4)))
    good = write_csv("good.csv", _signal_csv(short, np.sin(short)))
    d = _compare(ref, bad, tolerances=[ToleranceSet(label="tight", atoly=0.05)])
    row = d["rows"][0]
    # Verified behaviour: the library reports FAIL, not MISSING_TEST, when
    # the overlap fails; the row alone does not show that the spans differ.
    assert row["verdict"] == "fail" and row["status_name"] == "FAIL"
    spans = [n for n in d["notes"] if n.startswith("time ranges differ")]
    assert spans == [
        "time ranges differ (reference time spans [0.0, 10.0], test time spans [0.0, 8.0]): "
        "the reference extends beyond the test (MISSING_TEST). 1 failing row(s) (value "
        "[tight]) were judged on the overlap only; a failure takes precedence over the "
        "coverage error, which those rows would get if they passed there. Pass x_range "
        '{"lo": 0.0, "hi": 8.0} to compare only the overlap, and say that the rest was not '
        "compared"
    ]
    # Passing overlap: the coverage error and its note, no failure note.
    ok = _compare(ref, good, tolerances=[ToleranceSet(label="tight", atoly=0.05)])
    assert ok["rows"][0]["status_name"] == "MISSING_TEST"
    assert [n for n in ok["notes"] if "failing row" in n] == []
    # Comparing the overlap: no note at all.
    window = _compare(ref, bad, tolerances=[ToleranceSet(atoly=0.05)], x_range=XRange(lo=0, hi=8))
    assert not [n for n in window["notes"] if n.startswith("time ranges")]
