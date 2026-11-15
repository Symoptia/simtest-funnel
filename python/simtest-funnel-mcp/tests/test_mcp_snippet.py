"""The opt-in pytest snippet reproduces the server's verdicts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import json

import pytest
from conftest import WriteCsv, structured

from simtest_funnel_mcp.models import ToleranceSet, ToleranceSpec, XRange
from simtest_funnel_mcp.server import compare_signals_impl

LOOSE = ToleranceSet(label="loose", atolx=0.1, atoly=0.1)
NOXTOL = ToleranceSet(label="noxtol", atolx=0.0, atoly=0.1)


def _run_snippet(
    snippet: str, tmp_path: Path, data_root: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the snippet from ``tmp_path``; data paths resolve against
    ``data_root`` (default: this process's working directory, which is the
    base the server used when no roots were declared)."""
    path = tmp_path / "test_reproduced.py"
    path.write_text(snippet)
    env = {**os.environ, "SIMTEST_FUNNEL_DATA_ROOT": str(data_root or Path.cwd())}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(path)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=env,
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
    # The snippet is sent once, in the structured content; the text points there.
    text = result.content[0].text  # type: ignore[union-attr]
    assert "```python" not in text and "def test_funnel" not in text
    assert "structured content field 'snippet'" in text
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


def test_snippet_covers_only_returned_rows_and_is_sent_once(write_csv: WriteCsv) -> None:
    # Regression: the snippet listed all 3000 columns (ignoring max_rows) and
    # was sent twice (structured + text), ~620 kB.
    n = 3000
    header = "time," + ",".join(f"c{i}" for i in range(n))
    body = "\n".join(",".join([str(k)] + [str(k)] * n) for k in range(3))
    p = write_csv("wide.csv", header + "\n" + body + "\n")
    result = compare_signals_impl(str(p), str(p), [], include_snippet=True, max_rows=5)
    d = structured(result)
    snippet = d["snippet"]
    assert snippet.count("funnel.Status.PASS),") == 5
    assert "# 2995 row(s) not returned by the server (max_rows) are not included." in snippet
    text = result.content[0].text  # type: ignore[union-attr]
    assert "def test_funnel" not in text
    assert len(json.dumps(d)) < 15_000


def test_snippet_size_guard(
    demo_reference: Path, demo_test: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from simtest_funnel_mcp import snippet as snippet_module

    base = structured(
        compare_signals_impl(str(demo_reference), str(demo_test), [], include_snippet=True)
    )["snippet"]
    monkeypatch.setattr(snippet_module, "MAX_SNIPPET_CHARS", len(base) + 200)
    tight = structured(
        compare_signals_impl(
            str(demo_reference), str(demo_test), [], include_snippet=True,
            tolerances=[LOOSE, NOXTOL],
        )
    )["snippet"]
    assert len(tight) <= len(base) + 200
    assert "left out to keep this snippet under the size cap" in tight


def test_snippet_paths_are_relative_to_the_workspace_root(
    write_csv: WriteCsv, tmp_path: Path
) -> None:
    # Regression: absolute local paths made the "CI" snippet unusable elsewhere.
    sub = tmp_path / "data"
    sub.mkdir()
    (sub / "ref.csv").write_text("time,x\n0,0\n1,1\n2,2\n")
    (sub / "tst.csv").write_text("time,x\n0,0\n1,1\n2,2\n")
    root = tmp_path.resolve()
    d = structured(
        compare_signals_impl("data/ref.csv", "data/tst.csv", [root], include_snippet=True)
    )
    snippet = d["snippet"]
    assert "REFERENCE = DATA_ROOT / 'data/ref.csv'" in snippet
    assert 'os.environ.get("SIMTEST_FUNNEL_DATA_ROOT", Path.cwd())' in snippet
    assert str(root) not in snippet.split("DATA_ROOT = ")[1].split("REFERENCE_TIME")[0]
    # Copy the data elsewhere (as in a CI checkout) and run from there.
    elsewhere = tmp_path / "ci"
    (elsewhere / "data").mkdir(parents=True)
    for name in ("ref.csv", "tst.csv"):
        (elsewhere / "data" / name).write_text((sub / name).read_text())
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    proc = _run_snippet(snippet, run_dir, data_root=elsewhere)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_snippet_path_outside_base_stays_absolute(
    write_csv: WriteCsv, demo_reference: Path
) -> None:
    d = structured(
        compare_signals_impl(
            str(demo_reference), str(demo_reference), [], include_snippet=True, columns=["x"]
        )
    )
    snippet = d["snippet"]
    # The demo files lie under the repository (the test's working directory).
    assert "REFERENCE = DATA_ROOT / 'examples/web/public/reference.csv'" in snippet
    ref = write_csv("ref.csv", "time,x\n0,0\n1,1\n")
    d2 = structured(compare_signals_impl(str(ref), str(ref), [], include_snippet=True))
    assert "will not resolve on another machine" in d2["snippet"]
    assert f"REFERENCE = Path({str(ref)!r})" in d2["snippet"]


def test_snippet_reads_files_like_the_server(write_csv: WriteCsv, tmp_path: Path) -> None:
    # '#' inside the header is data, comment lines are skipped, trailing
    # delimiter on every line is accepted -- in the server and the snippet.
    text = "# comment\ntime,a#1,b,\n0,0,1,\n  # indented comment\n1,1,1,\n2,2,1,\n"
    ref = write_csv("ref.csv", text)
    tst = write_csv("tst.csv", text.replace("2,2,1,", "2,2.5,1,"))
    d = structured(
        compare_signals_impl(
            str(ref), str(tst), [], tolerances=[ToleranceSet(atolx=0.0, atoly=0.1)],
            include_snippet=True,
        )
    )
    rows = {r["column"]: r["verdict"] for r in d["rows"]}
    assert rows == {"a#1": "fail", "b": "pass"}
    proc = _run_snippet(d["snippet"], tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "2 passed" in proc.stdout


def test_trailing_comma_rows_fail_the_call(write_csv: WriteCsv) -> None:
    from mcp.server.mcpserver.exceptions import ToolError

    ref = write_csv("ref.csv", "time,a\n0,1,\n1,2,\n")
    with pytest.raises(ToolError, match=r"data row 1 \(line 2\) has 3 fields, header has 2"):
        compare_signals_impl(str(ref), str(ref), [])
