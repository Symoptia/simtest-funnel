"""The opt-in pytest snippet reproduces the server's verdicts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from conftest import WriteCsv, structured

from simtest_funnel_mcp.models import ToleranceSet, ToleranceSpec, XRange
from simtest_funnel_mcp.server import compare_signals_impl


def _run_snippet(snippet: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "test_reproduced.py"
    path.write_text(snippet)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(path)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )


def test_snippet_reproduces_demo_verdicts(
    demo_reference: Path, demo_test: Path, tmp_path: Path
) -> None:
    result = compare_signals_impl(
        str(demo_reference),
        str(demo_test),
        [],
        tolerances=[
            ToleranceSet(label="loose", atolx=0.1, atoly=0.1),
            ToleranceSet(label="noxtol", atolx=0.0, atoly=0.1),
            ToleranceSet(label="y1pct"),
        ],
        column_tolerances={"z": ToleranceSpec(rtoly=0.5)},
        include_snippet=True,
    )
    d = structured(result)
    snippet = d["snippet"]
    assert "funnel.Tolerances(atolx=0.1, rtoly=0.5)" in snippet  # override composed
    assert "funnel.Status.FAIL" in snippet and "funnel.Status.PASS" in snippet
    assert "```python" in result.content[0].text  # type: ignore[union-attr]
    proc = _run_snippet(snippet, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{d['totals']['rows']} passed" in proc.stdout


def test_snippet_detects_a_changed_verdict(
    demo_reference: Path, demo_test: Path, tmp_path: Path
) -> None:
    d = structured(
        compare_signals_impl(
            str(demo_reference),
            str(demo_test),
            [],
            columns=["z"],
            tolerances=[ToleranceSet(atolx=0.1, atoly=0.1)],
            include_snippet=True,
        )
    )
    gate = d["snippet"].replace("funnel.Status.FAIL", "funnel.Status.PASS")
    proc = _run_snippet(gate, tmp_path)
    assert proc.returncode == 1, proc.stdout
    assert "1 failed" in proc.stdout


def test_snippet_with_time_column_x_range_and_skipped_rows(
    write_csv: WriteCsv, tmp_path: Path
) -> None:
    ref = write_csv("ref.csv", "# header comment\nsignal,Time,q\n0,0,1\n1,1,1\n2,2,1\n3,3,1\n")
    tst = write_csv("tst.csv", "signal,Time\n0,0\n1.5,1\n2,2\n3,3\n")
    d = structured(
        compare_signals_impl(
            str(ref),
            str(tst),
            [],
            columns=["signal", "q"],
            tolerances=[ToleranceSet(atoly=0.1, atolx=0.0)],
            x_range=XRange(lo=0.5),
            include_snippet=True,
        )
    )
    snippet = d["snippet"]
    assert "REFERENCE_TIME = 'Time'" in snippet
    assert "funnel.Range(lo=0.5, hi=float(\"inf\"))" in snippet
    assert "#   q [set1]: column absent from the test file" in snippet
    proc = _run_snippet(snippet, tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "1 passed" in proc.stdout
