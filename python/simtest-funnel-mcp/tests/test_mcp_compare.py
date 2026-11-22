"""compare_signals: verdicts, tolerance sets, overrides, problems and caps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import WriteCsv, structured
from mcp.server.mcpserver.exceptions import ToolError

import simtest.funnel as funnel
from simtest_funnel_mcp.compare import compose_override
from simtest_funnel_mcp.models import ToleranceSet, ToleranceSpec, XRange
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
    assert set(z["worst"]) == {"x", "deviation", "tube_half_width_y"}
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
        "start_x", "end_x", "direction", "point_count", "worst_deviation", "worst_x"
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
