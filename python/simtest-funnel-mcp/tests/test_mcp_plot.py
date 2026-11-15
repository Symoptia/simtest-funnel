"""plot_signals: preparation, rendering, output paths and results."""

from __future__ import annotations

import base64
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import WriteCsv, structured
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import TextContent
from numpy.typing import NDArray

from simtest_funnel_mcp.csvio import load_csv
from simtest_funnel_mcp.models import ToleranceSet, XRange
from simtest_funnel_mcp.plot import (
    GID_VIOLATION_MARKERS,
    GID_VIOLATION_REGIONS,
    PlotData,
    PlotOutcome,
    png_size,
    prepare_plot,
    render,
    widen_and_merge,
)
from simtest_funnel_mcp.server import (
    compare_signals_impl,
    plot_signals_impl,
    resolve_output_path,
)

LOOSE = ToleranceSet(label="loose", atolx=0.1, atoly=0.1)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _write_signal(path: Path, t: NDArray[np.float64], y: NDArray[np.float64]) -> Path:
    np.savetxt(path, np.column_stack([t, y]), delimiter=",", header="time,y", comments="",
               fmt="%.12g")
    return path


@pytest.fixture(scope="module")
def spike_files(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """200 000 smooth samples; the test differs by one sample (a spike)."""
    d = tmp_path_factory.mktemp("spike")
    n = 200_000
    t = np.linspace(0.0, 100.0, n)
    y = np.sin(t / 5.0)
    yt = y.copy()
    yt[123_457] += 3.0
    return _write_signal(d / "ref.csv", t, y), _write_signal(d / "test.csv", t, yt)


@pytest.fixture(scope="module")
def edge_files(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """A step delayed just beyond the x tolerance: a two-sample violation."""
    d = tmp_path_factory.mktemp("edge")
    t = np.round(np.arange(0, 10_001) * 1e-4, 10)
    y = (t >= 0.5).astype(float)
    yt = (t >= 0.5 + 0.0102).astype(float)
    return _write_signal(d / "ref.csv", t, y), _write_signal(d / "test.csv", t, yt)


def _prepare(ref: Path, tst: Path, column: str, tol: ToleranceSet | None,
             x_range: XRange | None = None) -> PlotOutcome:
    return prepare_plot(load_csv(ref), load_csv(tst), column=column, tolerance=tol,
                        x_range=x_range, max_intervals=5)


def _assert_every_interval_marked(outcome: PlotOutcome) -> None:
    assert outcome.record.library is not None
    summary = outcome.record.library[1]
    data = outcome.data
    assert summary.intervals, "expected a failing case"
    for iv in summary.intervals:
        inside = (data.marker_x >= iv.start_x) & (data.marker_x <= iv.end_x)
        assert inside.any(), iv
        # ... and the marked points are drawn test points.
        assert np.isin(data.marker_x[inside], data.test_x).all()
        assert any(a <= iv.start_x and iv.end_x <= b for a, b in data.regions), iv


def _svg_ids(svg: bytes) -> set[str]:
    root = ET.fromstring(svg)
    return {el.attrib["id"] for el in root.iter() if "id" in el.attrib}


# --------------------------------------------------------------------------
# Preparation: the plot agrees with the verdict
# --------------------------------------------------------------------------


def test_single_spike_in_long_signal_is_drawn_and_marked(
    spike_files: tuple[Path, Path],
) -> None:
    outcome = _prepare(*spike_files, "y", ToleranceSet(atolx=0.01, atoly=0.05))
    assert outcome.record.row.verdict == "fail"
    assert outcome.record.row.interval_count == 1
    _assert_every_interval_marked(outcome)
    data = outcome.data
    assert data.test_x.shape[0] <= 2 * data.buckets + 3
    assert data.ref_x.shape[0] <= 2 * data.buckets + 2
    # The single-sample region is widened to be visible.
    (a, b), = data.regions
    assert b - a >= 0.004 * (data.view[1] - data.view[0]) * 0.999
    svg = render(data, "svg")
    assert {GID_VIOLATION_MARKERS, GID_VIOLATION_REGIONS} <= _svg_ids(svg)


def test_steep_edge_violation_is_marked(edge_files: tuple[Path, Path]) -> None:
    outcome = _prepare(*edge_files, "y", ToleranceSet(atolx=0.01, atoly=0.05))
    assert outcome.record.row.verdict == "fail"
    _assert_every_interval_marked(outcome)
    assert {GID_VIOLATION_MARKERS, GID_VIOLATION_REGIONS} <= _svg_ids(render(outcome.data, "svg"))


def test_every_interval_marked_with_hard_reduction(demo_reference: Path, demo_test: Path) -> None:
    # z with no x tolerance has many intervals; 5 buckets keep only pins visible.
    ref, tst = load_csv(demo_reference), load_csv(demo_test)
    outcome = prepare_plot(ref, tst, column="y", tolerance=ToleranceSet(atolx=0, atoly=0.01),
                           x_range=None, max_intervals=5, buckets=5)
    assert outcome.record.row.interval_count is not None
    assert outcome.record.row.interval_count > 5
    _assert_every_interval_marked(outcome)


def test_passing_plot_has_no_violation_marks(demo_reference: Path, demo_test: Path) -> None:
    outcome = _prepare(demo_reference, demo_test, "x", LOOSE)
    assert outcome.record.row.verdict == "pass"
    assert outcome.data.marker_x.shape[0] == 0
    assert outcome.data.regions == ()
    ids = _svg_ids(render(outcome.data, "svg"))
    assert GID_VIOLATION_MARKERS not in ids and GID_VIOLATION_REGIONS not in ids
    assert {"reference", "test", "tube"} <= ids


def test_title_states_column_verdict_and_tolerances(demo_reference: Path,
                                                    demo_test: Path) -> None:
    data = _prepare(demo_reference, demo_test, "z", LOOSE).data
    assert data.title.startswith("z: FAIL, 338 of 1001 points outside")
    assert data.subtitle == "tolerances [loose]: x atolx=0.1  |  y atoly=0.1"
    assert (data.x_label, data.y_label) == ("time", "z")
    passing = _prepare(demo_reference, demo_test, "x", ToleranceSet(atolx=0, atoly=0.5)).data
    assert passing.title == "x: PASS, all 1001 points inside the tube"
    assert passing.subtitle == "tolerances [set1]: x 0  |  y atoly=0.5"


def test_x_range_restricts_and_zooms(demo_reference: Path, demo_test: Path) -> None:
    outcome = _prepare(demo_reference, demo_test, "z", LOOSE, XRange(lo=0.4, hi=0.6))
    assert outcome.data.view == (0.4, 0.6)
    assert outcome.record.row.points_compared == 201
    # One neighbour on each side only.
    assert outcome.data.test_x.min() >= 0.399 and outcome.data.test_x.max() <= 0.601
    _assert_every_interval_marked(outcome)


def test_widen_and_merge() -> None:
    merged = widen_and_merge([(1.0, 1.0), (1.05, 1.05), (5.0, 6.0)], 0.2)
    assert len(merged) == 2
    assert merged[0] == pytest.approx((0.9, 1.15))
    assert merged[1] == (5.0, 6.0)
    assert widen_and_merge([], 1.0) == ()


@pytest.mark.parametrize("column", ["*", "y?", "[xy]"])
def test_glob_column_is_refused(demo_reference: Path, demo_test: Path, column: str) -> None:
    with pytest.raises(ValueError, match="one exact column"):
        _prepare(demo_reference, demo_test, column, None)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def demo_fail_data() -> PlotData:
    from conftest import DEMO_DIR

    return _prepare(DEMO_DIR / "reference.csv", DEMO_DIR / "test.csv", "z", LOOSE).data


def test_svg_is_well_formed_and_deterministic(demo_fail_data: PlotData) -> None:
    first = render(demo_fail_data, "svg")
    second = render(demo_fail_data, "svg")
    assert first == second
    root = ET.fromstring(first)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert b"<dc:date>" not in first


def test_png_is_well_formed_and_deterministic(demo_fail_data: PlotData) -> None:
    png = render(demo_fail_data, "png", 100)
    assert png[:8] == PNG_SIGNATURE
    assert png_size(png) == (800, 450)
    assert render(demo_fail_data, "png", 100) == png
    assert png_size(render(demo_fail_data, "png", 200)) == (1600, 900)


def test_large_tube_band_is_rasterized_in_svg(spike_files: tuple[Path, Path]) -> None:
    data = _prepare(*spike_files, "y", ToleranceSet(atolx=0.01, atoly=0.05)).data
    assert data.lower_x.shape[0] > 100_000  # the library's bounds are not compact here
    svg = render(data, "svg")
    assert len(svg) < 300_000
    assert b"<image" in svg
    ET.fromstring(svg)


def test_png_size_rejects_other_data() -> None:
    with pytest.raises(ValueError):
        png_size(b"GIF89a" + b"\0" * 30)


# --------------------------------------------------------------------------
# Output paths
# --------------------------------------------------------------------------


def test_output_path_inside_roots(tmp_path: Path) -> None:
    target, fmt = resolve_output_path("plots.SVG", [tmp_path.resolve()], False)
    assert target == tmp_path.resolve() / "plots.SVG" and fmt == "svg"
    assert resolve_output_path(str(tmp_path / "a.png"), [tmp_path], False)[1] == "png"


def test_output_path_outside_roots(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ToolError, match="outside the client's workspace roots"):
        resolve_output_path(str(tmp_path / "a.svg"), [root.resolve()], False)
    with pytest.raises(ToolError, match="outside"):
        resolve_output_path(str(root / ".." / "a.svg"), [root.resolve()], False)


def test_output_path_without_roots_must_be_under_cwd(tmp_path: Path, monkeypatch: Any) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert resolve_output_path("a.svg", [], False)[0] == cwd.resolve() / "a.svg"
    with pytest.raises(ToolError, match="outside the server's working directory"):
        resolve_output_path(str(tmp_path / "a.svg"), [], False)


def test_output_path_missing_directory_is_not_created(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="does not exist; the server does not create"):
        resolve_output_path(str(tmp_path / "new" / "dir" / "a.svg"), [tmp_path], False)
    assert not (tmp_path / "new").exists()


@pytest.mark.parametrize("name", ["a.pdf", "a.svgz", "a", "a.svg.txt"])
def test_output_path_wrong_extension(tmp_path: Path, name: str) -> None:
    with pytest.raises(ToolError, match=r"must end in \.svg or \.png"):
        resolve_output_path(str(tmp_path / name), [tmp_path], False)


def test_output_path_existing_file_and_directory(tmp_path: Path) -> None:
    existing = tmp_path / "a.svg"
    existing.write_text("keep")
    with pytest.raises(ToolError, match="already exists; pass overwrite=true"):
        resolve_output_path(str(existing), [tmp_path], False)
    assert resolve_output_path(str(existing), [tmp_path], True)[0] == existing.resolve()
    (tmp_path / "d.svg").mkdir()
    with pytest.raises(ToolError, match="not a regular file"):
        resolve_output_path(str(tmp_path / "d.svg"), [tmp_path], True)


def test_output_path_symlink_to_other_extension(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("keep")
    os.symlink(tmp_path / "notes.txt", tmp_path / "plot.svg")
    with pytest.raises(ToolError, match="not a .svg file"):
        resolve_output_path(str(tmp_path / "plot.svg"), [tmp_path], True)


def test_output_path_empty() -> None:
    with pytest.raises(ToolError, match="empty"):
        resolve_output_path("  ", [], False)


# --------------------------------------------------------------------------
# The tool
# --------------------------------------------------------------------------


def _plot(demo_reference: Path, demo_test: Path, roots: list[Path], **kw: Any) -> Any:
    return plot_signals_impl(str(demo_reference), str(demo_test), roots, **kw)


def test_plot_result_matches_compare_row(demo_reference: Path, demo_test: Path) -> None:
    root = demo_reference.parent.resolve()
    compared = structured(compare_signals_impl(
        str(demo_reference), str(demo_test), [root], columns=["z"], tolerances=[LOOSE],
    ))
    plotted = _plot(demo_reference, demo_test, [root], column="z", tolerance=LOOSE)
    d = structured(plotted)
    assert d["row"] == compared["rows"][0]
    assert d["tolerance_set"] == compared["tolerance_sets"][0]
    assert d["reference"] == compared["reference"]
    assert "file" not in d
    text, image = plotted.content
    assert text.type == "text" and image.type == "image"
    assert image.mime_type == "image/png"
    preview = base64.b64decode(image.data)
    assert preview[:8] == PNG_SIGNATURE and png_size(preview) == (800, 450)
    assert d["preview"] == {"format": "png", "width_px": 800, "height_px": 450,
                            "bytes": len(preview)}
    assert "FAIL z [loose]: 338/1001 points outside" in text.text
    assert "no file written" in text.text


def test_plot_writes_svg_and_png_files(demo_reference: Path, demo_test: Path,
                                       tmp_path: Path) -> None:
    roots = [demo_reference.parent.resolve(), tmp_path.resolve()]
    before = set(tmp_path.iterdir())
    svg = _plot(demo_reference, demo_test, roots, column="z", tolerance=LOOSE,
                output_path=str(tmp_path / "z.svg"))
    d = structured(svg)
    written = tmp_path / "z.svg"
    assert d["file"] == {"path": str(written.resolve()), "format": "svg",
                         "bytes": written.stat().st_size}
    ET.fromstring(written.read_bytes())
    assert f"plot written: {written.resolve()} (SVG," in svg.content[0].text
    # Same call again with overwrite: byte-identical file.
    first = written.read_bytes()
    _plot(demo_reference, demo_test, roots, column="z", tolerance=LOOSE,
          output_path=str(written), overwrite=True)
    assert written.read_bytes() == first

    png = structured(_plot(demo_reference, demo_test, roots, column="z", tolerance=LOOSE,
                           output_path=str(tmp_path / "z.png")))
    data = (tmp_path / "z.png").read_bytes()
    assert data[:8] == PNG_SIGNATURE and png_size(data) == (1600, 900)
    assert png["file"]["width_px"] == 1600 and png["file"]["height_px"] == 900
    # Exactly the requested files, nothing else.
    assert set(tmp_path.iterdir()) - before == {written, tmp_path / "z.png"}


def test_existing_file_is_kept_without_overwrite(demo_reference: Path, demo_test: Path,
                                                 tmp_path: Path) -> None:
    target = tmp_path / "z.svg"
    target.write_text("keep")
    with pytest.raises(ToolError, match="overwrite=true"):
        _plot(demo_reference, demo_test, [tmp_path], column="z", output_path=str(target))
    assert target.read_text() == "keep"


def test_error_statuses_write_nothing(write_csv: WriteCsv, tmp_path: Path) -> None:
    ref = write_csv("ref.csv", "time,a,q\n0,0,0\n1,1,1\n")
    tst = write_csv("tst.csv", "time,a\n0,0\n1.1,1\n")
    target = tmp_path / "out.svg"
    with pytest.raises(ToolError, match="absent from the test file"):
        _plot(ref, tst, [tmp_path], column="q", output_path=str(target))
    with pytest.raises(ToolError, match=r'MISSING_REFERENCE.*"hi": 1\.0'):
        _plot(ref, tst, [tmp_path], column="a", output_path=str(target))
    bad = write_csv("bad.csv", "time,a\n0,x\n1,1\n")
    with pytest.raises(ToolError, match="non-numeric"):
        _plot(ref, bad, [tmp_path], column="a", output_path=str(target))
    with pytest.raises(ToolError, match="time column"):
        _plot(ref, tst, [tmp_path], column="time", output_path=str(target))
    assert not target.exists()


def test_bad_output_path_fails_before_reading(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="must end in"):
        plot_signals_impl(str(tmp_path / "missing.csv"), str(tmp_path / "missing.csv"),
                          [tmp_path], column="a", output_path=str(tmp_path / "a.jpg"))


def test_large_input_structured_result_stays_small(spike_files: tuple[Path, Path],
                                                   tmp_path: Path) -> None:
    ref, tst = spike_files
    result = plot_signals_impl(
        str(ref), str(tst), [ref.parent, tmp_path], column="y",
        tolerance=ToleranceSet(atolx=0.01, atoly=0.05), output_path=str(tmp_path / "y.svg"),
    )
    d = structured(result)
    dumped = json.dumps(d)
    assert len(dumped) < 4_000
    text = result.content[0]
    assert isinstance(text, TextContent) and len(text.text) < 2_000

    def longest_list(v: object) -> int:
        if isinstance(v, list):
            return max([len(v), *(longest_list(x) for x in v)])
        if isinstance(v, dict):
            return max([0, *(longest_list(x) for x in v.values())])
        return 0

    assert longest_list(d) <= 5  # intervals capped; no sample arrays
    assert d["drawn"]["test"] <= 2 * d["drawn"]["buckets"] + 3
    assert d["drawn"]["violation_markers"] >= 1
