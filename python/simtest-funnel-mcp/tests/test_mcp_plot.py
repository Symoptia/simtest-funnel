"""plot_signals: preparation, rendering, output paths and results."""

from __future__ import annotations

import base64
import errno
import json
import os
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from conftest import OPEN_METEO_REF, WriteCsv, open_meteo_column, structured
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import TextContent
from numpy.typing import NDArray

import simtest.funnel as funnel
from simtest_funnel_mcp import server
from simtest_funnel_mcp.csvio import load_csv
from simtest_funnel_mcp.models import ToleranceSet, XRange
from simtest_funnel_mcp.plot import (
    DEFAULT_BUCKETS,
    GID_VIOLATION_MARKERS,
    GID_VIOLATION_REGIONS,
    PlotData,
    PlotOutcome,
    bound_at,
    date_labels,
    date_ticks,
    png_size,
    prepare_plot,
    render,
    widen_and_merge,
)
from simtest_funnel_mcp.server import (
    NO_WRITE_LOCATION,
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


@pytest.fixture(scope="module")
def noisy_files(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """50 000 noisy samples: tube bounds with ~30k-67k zig-zag vertices."""
    d = tmp_path_factory.mktemp("noisy")
    n = 50_000
    t = np.linspace(0.0, 100.0, n)
    rng = np.random.default_rng(7)
    y = np.sin(t / 5.0) + 0.05 * rng.standard_normal(n)
    yt = y + 0.03 * rng.standard_normal(n)
    return _write_signal(d / "ref.csv", t, y), _write_signal(d / "test.csv", t, yt)


def _prepare(ref: Path, tst: Path, column: str, tol: ToleranceSet | None,
             x_range: XRange | None = None, buckets: int = DEFAULT_BUCKETS) -> PlotOutcome:
    return prepare_plot(load_csv(ref), load_csv(tst), column=column, tolerance=tol,
                        x_range=x_range, max_intervals=5, buckets=buckets)


def _drawn_extent(px: NDArray[np.float64], py: NDArray[np.float64],
                  x: float) -> tuple[float, float] | None:
    """Range of the drawn polyline at ``x`` (all vertices at x, else linear
    interpolation between the neighbouring vertices); None if not covered.
    Deliberately naive, independent of the implementation."""
    at = py[px == x]
    if at.shape[0]:
        return float(at.min()), float(at.max())
    left = np.flatnonzero(px < x)
    right = np.flatnonzero(px > x)
    if not left.shape[0] or not right.shape[0]:
        return None
    i, k = int(left[-1]), int(right[0])
    v = float(py[i] + (py[k] - py[i]) * (x - px[i]) / (px[k] - px[i]))
    return v, v


def _outside_drawn_tube(data: PlotData, x: float, y: float) -> bool:
    """True when (x, y) lies outside the drawn tube polygon at x."""
    lower = _drawn_extent(data.lower_x, data.lower_y, x)
    upper = _drawn_extent(data.upper_x, data.upper_y, x)
    if lower is None or upper is None:
        return True
    return y > upper[1] or y < lower[0]


def _judged_drawn_test_points(outcome: PlotOutcome) -> NDArray[np.bool_]:
    """Drawn test points the comparison judges (x_range ∩ reference span)."""
    data = outcome.data
    lo, hi = outcome.compare.x_range
    ref = outcome.compare.result.reference
    assert ref.time_start is not None and ref.time_end is not None
    eff_lo = max(-np.inf if lo is None else lo, ref.time_start)
    eff_hi = min(np.inf if hi is None else hi, ref.time_end)
    return (data.test_x >= eff_lo) & (data.test_x <= eff_hi)


def _assert_drawn_tube_agrees(outcome: PlotOutcome) -> None:
    """Every marker lies outside the drawn tube; every other judged drawn
    test point lies inside it."""
    data = outcome.data
    for x, y in zip(data.marker_x, data.marker_y, strict=True):
        assert _outside_drawn_tube(data, float(x), float(y)), (x, y)
    marked = set(zip(data.marker_x.tolist(), data.marker_y.tolist(), strict=True))
    judged = _judged_drawn_test_points(outcome)
    for x, y, j in zip(data.test_x, data.test_y, judged, strict=True):
        if j and (float(x), float(y)) not in marked:
            assert not _outside_drawn_tube(data, float(x), float(y)), (x, y)


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


# --------------------------------------------------------------------------
# Tube bounds reduced for drawing, never contradicting the verdict
# --------------------------------------------------------------------------


def test_bound_at_reproduces_the_library_judgement(spike_files: tuple[Path, Path],
                                                   noisy_files: tuple[Path, Path]) -> None:
    # bound_at must give bit-identical bounds: same points outside, same deviations.
    for (ref_p, tst_p), tol in ((spike_files, funnel.Tolerances(atolx=0.01, atoly=0.05)),
                                (noisy_files, funnel.Tolerances(atolx=0.005, atoly=0.08))):
        ref, tst = load_csv(ref_p), load_csv(tst_p)
        res = funnel.compare(ref.time, ref.values["y"], tst.time, tst.values["y"],
                             funnel.Options(tolerances=tol))
        lo, _ = bound_at(*res.lower, tst.time)
        up, _ = bound_at(*res.upper, tst.time)
        y = tst.values["y"]
        dev = np.where(y > up, y - up, np.where(y < lo, y - lo, 0.0))
        assert np.count_nonzero(dev) > 0
        assert np.array_equal(dev, res.errors[1])


@pytest.mark.parametrize(
    ("case", "column", "tol", "buckets"),
    [
        ("spike", "y", ToleranceSet(atolx=0.01, atoly=0.05), DEFAULT_BUCKETS),
        ("edge", "y", ToleranceSet(atolx=0.01, atoly=0.05), DEFAULT_BUCKETS),
        ("noisy", "y", ToleranceSet(atolx=0.005, atoly=0.08), DEFAULT_BUCKETS),
        ("noisy", "y", ToleranceSet(atolx=0, atoly=0.08), DEFAULT_BUCKETS),
        ("demo", "z", LOOSE, DEFAULT_BUCKETS),
        ("demo", "y", ToleranceSet(atolx=0, atoly=0.01), DEFAULT_BUCKETS),
        ("demo", "y", ToleranceSet(atolx=0, atoly=0.01), 5),  # hard reduction
        ("demo", "z", LOOSE, 5),
    ],
)
def test_failing_markers_lie_outside_the_drawn_tube(
    request: pytest.FixtureRequest, case: str, column: str, tol: ToleranceSet, buckets: int,
) -> None:
    files: tuple[Path, Path] = (
        (request.getfixturevalue("demo_reference"), request.getfixturevalue("demo_test"))
        if case == "demo" else request.getfixturevalue(f"{case}_files")
    )
    outcome = _prepare(files[0], files[1], column, tol, buckets=buckets)
    assert outcome.record.row.verdict == "fail"
    assert outcome.data.marker_x.shape[0] >= len(outcome.data.regions) >= 1
    _assert_every_interval_marked(outcome)
    _assert_drawn_tube_agrees(outcome)


@pytest.mark.parametrize(
    ("case", "column", "tol", "buckets"),
    [
        ("spike", "y", ToleranceSet(atolx=0.01, atoly=3.5), DEFAULT_BUCKETS),
        ("noisy", "y", ToleranceSet(atolx=0.005, atoly=0.12), DEFAULT_BUCKETS),
        ("noisy", "y", ToleranceSet(atolx=0, atoly=0.2), DEFAULT_BUCKETS),
        ("noisy", "y", ToleranceSet(atolx=0, atoly=0.2), 50),
        ("demo", "x", LOOSE, DEFAULT_BUCKETS),
        ("demo", "x", LOOSE, 5),
    ],
)
def test_passing_points_lie_inside_the_drawn_tube(
    request: pytest.FixtureRequest, case: str, column: str, tol: ToleranceSet, buckets: int,
) -> None:
    files: tuple[Path, Path] = (
        (request.getfixturevalue("demo_reference"), request.getfixturevalue("demo_test"))
        if case == "demo" else request.getfixturevalue(f"{case}_files")
    )
    outcome = _prepare(files[0], files[1], column, tol, buckets=buckets)
    assert outcome.record.row.verdict == "pass"
    assert outcome.data.marker_x.shape[0] == 0
    _assert_drawn_tube_agrees(outcome)


def test_tube_bounds_are_reduced(spike_files: tuple[Path, Path],
                                 noisy_files: tuple[Path, Path]) -> None:
    for files, tol in ((spike_files, ToleranceSet(atolx=0.01, atoly=0.05)),
                       (noisy_files, ToleranceSet(atolx=0, atoly=0.08))):
        outcome = _prepare(*files, "y", tol)
        assert outcome.record.library is not None
        full = outcome.record.library[0]
        assert full.lower[0].shape[0] > 40_000  # the library's bounds are long here
        data = outcome.data
        # min/max of 1000 buckets (+ first/last) plus exact points where needed,
        # which are at most one per drawn test point.
        for n in (data.lower_x.shape[0], data.upper_x.shape[0]):
            assert n <= 2 * data.buckets + 2 + data.test_x.shape[0]
            assert n < 3_000
        assert np.all(np.diff(data.lower_x) >= 0) and np.all(np.diff(data.upper_x) >= 0)


def test_short_bounds_are_drawn_unchanged(demo_reference: Path, demo_test: Path) -> None:
    # Fewer vertices than 2 * buckets: the drawn bounds are the library's
    # vertices in the view plus one neighbour on each side, nothing added.
    outcome = _prepare(demo_reference, demo_test, "z", LOOSE)
    assert outcome.record.library is not None
    data = outcome.data
    lib = outcome.record.library[0]
    for (bx, by), (dx, dy) in ((lib.lower, (data.lower_x, data.lower_y)),
                               (lib.upper, (data.upper_x, data.upper_y))):
        inside = np.flatnonzero((bx >= data.view[0]) & (bx <= data.view[1]))
        i0, i1 = max(inside[0] - 1, 0), min(inside[-1] + 2, bx.shape[0])
        assert np.array_equal(dx, bx[i0:i1]) and np.array_equal(dy, by[i0:i1])


def test_zoom_between_bound_vertices_still_draws_the_tube(edge_files: tuple[Path, Path]) -> None:
    # The step's bounds have 4 vertices; none lies in this window.
    outcome = _prepare(*edge_files, "y", ToleranceSet(atolx=0.01, atoly=0.05),
                       XRange(lo=0.2, hi=0.3))
    data = outcome.data
    assert outcome.record.row.verdict == "pass"
    assert data.lower_x.min() <= 0.2 and data.lower_x.max() >= 0.3
    assert data.upper_x.min() <= 0.2 and data.upper_x.max() >= 0.3
    _assert_drawn_tube_agrees(outcome)


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


def test_large_tube_svg_is_vector_and_small(spike_files: tuple[Path, Path]) -> None:
    data = _prepare(*spike_files, "y", ToleranceSet(atolx=0.01, atoly=0.05)).data
    svg = render(data, "svg")
    assert len(svg) < 250_000
    assert b"<image" not in svg  # fully vector, no raster fallback
    ET.fromstring(svg)
    assert render(data, "svg") == svg


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


def test_output_path_without_roots_or_output_dir_is_refused(tmp_path: Path,
                                                            monkeypatch: Any) -> None:
    # Not even inside the working directory: launched from "/" that would be anywhere.
    monkeypatch.chdir(tmp_path)
    for raw in ("a.svg", str(tmp_path / "a.svg")):
        with pytest.raises(ToolError) as info:
            resolve_output_path(raw, [], False)
        message = str(info.value)
        assert message == NO_WRITE_LOCATION
        assert "workspace roots" in message and "--output-dir" in message
        assert "SIMTEST_FUNNEL_MCP_OUTPUT_DIR" in message and "Omit output_path" in message
    assert not (tmp_path / "a.svg").exists()


def test_output_path_inside_configured_output_dir(tmp_path: Path) -> None:
    out = (tmp_path / "plots").resolve()
    out.mkdir()
    assert resolve_output_path("a.svg", [], False, [out]) == (out / "a.svg", "svg")
    assert resolve_output_path(str(out / "b.png"), [], False, [out])[0] == out / "b.png"
    with pytest.raises(ToolError, match=r"outside the configured output directories"):
        resolve_output_path(str(tmp_path / "a.svg"), [], False, [out])
    with pytest.raises(ToolError, match="outside"):
        resolve_output_path(str(out / ".." / "a.svg"), [], False, [out])
    # Symlink escape out of the output directory.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    os.symlink(elsewhere, out / "link")
    with pytest.raises(ToolError, match="outside"):
        resolve_output_path(str(out / "link" / "a.svg"), [], False, [out])


def test_output_path_roots_and_output_dir(tmp_path: Path) -> None:
    root = (tmp_path / "root").resolve()
    out = (tmp_path / "out").resolve()
    root.mkdir()
    out.mkdir()
    # Inside either is allowed; relative paths go to the first root.
    assert resolve_output_path("a.svg", [root], False, [out])[0] == root / "a.svg"
    assert resolve_output_path(str(out / "a.svg"), [root], False, [out])[0] == out / "a.svg"
    with pytest.raises(ToolError) as info:
        resolve_output_path(str(tmp_path / "a.svg"), [root], False, [out])
    assert "outside the client's workspace roots" in str(info.value)
    assert "and the configured output directories" in str(info.value)


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


def test_output_path_empty(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="empty"):
        resolve_output_path("  ", [], False)
    with pytest.raises(ToolError, match="empty"):
        resolve_output_path("  ", [tmp_path], False, [tmp_path])


# --------------------------------------------------------------------------
# The tool
# --------------------------------------------------------------------------


def _plot(demo_reference: Path, demo_test: Path, roots: list[Path], **kw: Any) -> Any:
    return plot_signals_impl(str(demo_reference), str(demo_test), roots, **kw)


def test_plot_notes_missing_x_tolerance_on_failure(edge_files: tuple[Path, Path]) -> None:
    ref, tst = edge_files
    failed = structured(plot_signals_impl(
        str(ref), str(tst), [], column="y", tolerance=ToleranceSet(atoly=0.05)
    ))
    assert failed["row"]["verdict"] == "fail"
    assert any("had no x (time) tolerance" in n for n in failed["notes"])
    # An x tolerance given (even one too small to pass) means no hint.
    given = structured(plot_signals_impl(
        str(ref), str(tst), [], column="y", tolerance=ToleranceSet(atolx=0.01, atoly=0.05)
    ))
    assert given["row"]["verdict"] == "fail"
    assert not any("had no x (time) tolerance" in n for n in given["notes"])


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
    with pytest.raises(ToolError, match="cannot write output_path"):
        plot_signals_impl(str(tmp_path / "missing.csv"), str(tmp_path / "missing.csv"),
                          [], column="a", output_path=str(tmp_path / "a.svg"))


def test_without_write_location_preview_still_works(demo_reference: Path, demo_test: Path,
                                                    tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ToolError, match="--output-dir"):
        _plot(demo_reference, demo_test, [], column="z", output_path="z.svg")
    assert list(tmp_path.iterdir()) == []
    result = _plot(demo_reference, demo_test, [], column="z")
    assert "file" not in structured(result)
    assert result.content[1].mime_type == "image/png"


def test_plot_writes_into_configured_output_dir(demo_reference: Path, demo_test: Path,
                                                tmp_path: Path) -> None:
    out = tmp_path.resolve()
    d = structured(_plot(demo_reference, demo_test, [], column="z", output_path="z.svg",
                         output_dirs=[out]))
    assert d["file"]["path"] == str(out / "z.svg")
    assert (out / "z.svg").read_bytes().startswith(b"<?xml")


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


# --------------------------------------------------------------------------
# Writing: the checked path is not trusted at write time
# --------------------------------------------------------------------------


@pytest.fixture
def swap_during_work(monkeypatch: pytest.MonkeyPatch) -> list[Callable[[], None]]:
    """Actions run after the comparison, i.e. between the output path check
    and the write (where a concurrent process could change the tree)."""
    actions: list[Callable[[], None]] = []
    real = prepare_plot

    def prepare_then_swap(*args: Any, **kwargs: Any) -> PlotOutcome:
        out = real(*args, **kwargs)
        for action in actions:
            action()
        return out

    monkeypatch.setattr("simtest_funnel_mcp.server.prepare_plot", prepare_then_swap)
    return actions


def _dir_to_symlink(directory: Path, target: Path) -> Callable[[], None]:
    def swap() -> None:
        shutil.rmtree(directory)
        os.symlink(target, directory)

    return swap


@pytest.fixture(params=["dir_fd", "by_path"])
def write_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test with the dir_fd writer and with the Windows fallback."""
    if request.param == "dir_fd" and not server._DIR_FD_WRITES:
        pytest.skip("no dir_fd writes on this platform")
    monkeypatch.setattr(server, "_DIR_FD_WRITES", request.param == "dir_fd")
    return str(request.param)


def test_directory_swapped_for_symlink_is_refused(
    demo_reference: Path, demo_test: Path, tmp_path: Path,
    swap_during_work: list[Callable[[], None]], write_mode: str,
) -> None:
    ws, outside = tmp_path / "ws", tmp_path / "outside"
    (ws / "sub").mkdir(parents=True)
    outside.mkdir()
    swap_during_work.append(_dir_to_symlink(ws / "sub", outside))
    with pytest.raises(ToolError, match="not written|cannot write"):
        _plot(demo_reference, demo_test, [ws, demo_reference.parent], column="z",
              output_path=str(ws / "sub" / "z.svg"))
    assert list(outside.iterdir()) == []


def test_intermediate_directory_swapped_for_symlink_is_refused(
    demo_reference: Path, demo_test: Path, tmp_path: Path,
    swap_during_work: list[Callable[[], None]], write_mode: str,
) -> None:
    ws, outside = tmp_path / "ws", tmp_path / "outside"
    (ws / "sub" / "deep").mkdir(parents=True)
    (outside / "deep").mkdir(parents=True)
    swap_during_work.append(_dir_to_symlink(ws / "sub", outside))
    with pytest.raises(ToolError, match="outside"):
        _plot(demo_reference, demo_test, [ws, demo_reference.parent], column="z",
              output_path=str(ws / "sub" / "deep" / "z.svg"))
    assert list((outside / "deep").iterdir()) == []


def test_overwrite_replaces_a_swapped_in_symlink_instead_of_following_it(
    demo_reference: Path, demo_test: Path, tmp_path: Path,
    swap_during_work: list[Callable[[], None]], write_mode: str,
) -> None:
    ws, outside = tmp_path / "ws", tmp_path / "outside"
    ws.mkdir()
    outside.mkdir()
    target = ws / "z.svg"
    target.write_text("old plot")
    victim = outside / "victim.svg"
    victim.write_text("precious")

    def swap() -> None:
        target.unlink()
        os.symlink(victim, target)

    swap_during_work.append(swap)
    d = structured(_plot(demo_reference, demo_test, [ws, demo_reference.parent], column="z",
                         output_path=str(target), overwrite=True))
    assert victim.read_text() == "precious"
    assert not target.is_symlink()
    assert target.read_bytes().startswith(b"<?xml")
    assert d["file"]["path"] == str(target.resolve())
    assert sorted(p.name for p in ws.iterdir()) == ["z.svg"]  # no temporary file left


def test_file_created_during_the_call_is_kept_without_overwrite(
    demo_reference: Path, demo_test: Path, tmp_path: Path,
    swap_during_work: list[Callable[[], None]], write_mode: str,
) -> None:
    target = tmp_path / "z.svg"

    def create() -> None:
        target.write_text("theirs")

    swap_during_work.append(create)
    with pytest.raises(ToolError, match="already exists; pass overwrite=true"):
        _plot(demo_reference, demo_test, [tmp_path, demo_reference.parent], column="z",
              output_path=str(target))
    assert target.read_text() == "theirs"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["z.svg"]


def test_write_without_hard_links_still_creates_exclusively(
    demo_reference: Path, demo_test: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    write_mode: str,
) -> None:
    def no_links(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EPERM, "hard links not supported")

    monkeypatch.setattr(os, "link", no_links)  # the os module server uses
    target = tmp_path / "z.svg"
    d = structured(_plot(demo_reference, demo_test, [tmp_path, demo_reference.parent],
                         column="z", output_path=str(target)))
    assert d["file"]["path"] == str(target.resolve())
    assert target.read_bytes().startswith(b"<?xml")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["z.svg"]
    with pytest.raises(ToolError, match="already exists"):
        _plot(demo_reference, demo_test, [tmp_path, demo_reference.parent], column="z",
              output_path=str(target))


# --------------------------------------------------------------------------
# Column pairs and date-time axes
# --------------------------------------------------------------------------

DAY1 = open_meteo_column(1)
TOL_2C_3H = ToleranceSet(label="2C_3h", atoly=2, atolx=10800)


def _svg_texts(svg: bytes) -> list[str]:
    """Texts of the SVG (drawn as paths; matplotlib keeps them as comments)."""
    import re

    return re.findall(r"<!-- (.*?) -->", svg.decode("utf-8"))


def test_day1_pair_plot_equals_the_compare_pair_row(open_meteo: Path) -> None:
    from simtest_funnel_mcp.models import ColumnPair

    p = structured(plot_signals_impl(
        str(open_meteo), None, [], column=OPEN_METEO_REF, test_column=DAY1, header_line=4,
        tolerance=ToleranceSet(label="2C", atoly=2), max_intervals=50,
    ))
    c = structured(compare_signals_impl(
        str(open_meteo), None, [], header_line=4, max_intervals=50,
        pairs=[ColumnPair(reference=OPEN_METEO_REF, test=DAY1)],
        tolerances=[ToleranceSet(label="2C", atoly=2)],
    ))
    assert p["row"] == c["rows"][0]
    assert p["row"]["reference_column"] == OPEN_METEO_REF and p["row"]["test_column"] == DAY1
    assert p["test"]["path"] == p["reference"]["path"] == str(open_meteo)
    outcome = prepare_plot(
        load_csv(open_meteo, 4), load_csv(open_meteo, 4), column=OPEN_METEO_REF,
        test_column=DAY1, tolerance=TOL_2C_3H, x_range=None, max_intervals=5,
    )
    data = outcome.data
    assert data.title.startswith(f"{DAY1} vs {OPEN_METEO_REF}\n")
    assert (data.legend_reference, data.legend_test) == (
        f"reference: {OPEN_METEO_REF}", f"test: {DAY1}"
    )
    assert data.y_label == OPEN_METEO_REF
    texts = _svg_texts(render(data, "svg"))
    assert f"reference: {OPEN_METEO_REF}" in texts and f"test: {DAY1}" in texts


def test_test_column_omitted_or_equal_behaves_as_before(
    demo_reference: Path, demo_test: Path
) -> None:
    a = _prepare(demo_reference, demo_test, "z", LOOSE)
    b = prepare_plot(load_csv(demo_reference), load_csv(demo_test), column="z",
                     test_column="z", tolerance=LOOSE, x_range=None, max_intervals=5)
    assert (a.data.title, a.data.subtitle, a.data.x_label) == (
        b.data.title, b.data.subtitle, b.data.x_label)
    np.testing.assert_array_equal(a.data.test_y, b.data.test_y)
    assert a.record.row == b.record.row
    assert (a.data.legend_reference, a.data.legend_test) == ("reference", "test")
    assert a.data.title.startswith("z: FAIL") and not a.data.date_axis


def test_glob_test_column_is_refused(open_meteo: Path) -> None:
    with pytest.raises(ToolError, match="one exact column name"):
        plot_signals_impl(str(open_meteo), None, [], column=OPEN_METEO_REF,
                          test_column="temperature_2m_previous_day*", header_line=4)


def test_plot_of_hourly_open_meteo_data(open_meteo: Path) -> None:
    result = plot_signals_impl(str(open_meteo), None, [], column=OPEN_METEO_REF,
                               test_column=DAY1, header_line=4, tolerance=TOL_2C_3H)
    p = structured(result)
    assert p["view"] == {
        "lo": 1793836800.0, "lo_iso": "2026-11-05T00:00:00",
        "hi": 1795129200.0, "hi_iso": "2026-11-19T23:00:00",
    }
    assert p["tolerance_set"]["time_tolerance"] == {"seconds": 10800.0, "duration": "PT3H"}
    text = result.content[0].text  # type: ignore[union-attr]
    assert "time 2026-11-05T00:00:00 .. 2026-11-19T23:00:00" in text
    outcome = prepare_plot(load_csv(open_meteo, 4), load_csv(open_meteo, 4),
                           column=OPEN_METEO_REF, test_column=DAY1, tolerance=TOL_2C_3H,
                           x_range=None, max_intervals=5)
    data = outcome.data
    assert data.date_axis and data.x_label == "time (no time zone)"
    assert data.subtitle == "tolerances [2C_3h]: x \u00b1PT3H  |  y atoly=2"
    texts = _svg_texts(render(data, "svg"))
    assert texts[:8] == ["2026-11-05", "11-07", "11-09", "11-11", "11-13", "11-15",
                         "11-17", "11-19"]
    assert "time (no time zone)" in texts
    # Deterministic, and the drawn tube agrees with the comparison.
    assert render(data, "svg") == render(data, "svg")
    assert render(data, "png") == render(data, "png")
    _assert_drawn_tube_agrees(outcome)


def test_failing_date_axis_plot_marks_every_interval(open_meteo: Path) -> None:
    outcome = prepare_plot(load_csv(open_meteo, 4), load_csv(open_meteo, 4),
                           column=OPEN_METEO_REF, test_column=open_meteo_column(5),
                           tolerance=TOL_2C_3H, x_range=None, max_intervals=5)
    assert outcome.record.row.verdict == "fail"
    _assert_every_interval_marked(outcome)
    _assert_drawn_tube_agrees(outcome)


def test_zoom_with_iso_bounds(open_meteo: Path) -> None:
    x_range = XRange(lo="2026-11-10T00:00", hi="2026-11-12T00:00")
    p = structured(plot_signals_impl(str(open_meteo), None, [], column=OPEN_METEO_REF,
                                     test_column=DAY1, header_line=4, x_range=x_range))
    assert p["view"]["lo_iso"] == "2026-11-10T00:00:00"
    assert p["view"]["hi_iso"] == "2026-11-12T00:00:00"
    assert p["x_range"]["lo_iso"] == "2026-11-10T00:00:00"
    assert p["row"]["points_compared"] == 49
    outcome = prepare_plot(load_csv(open_meteo, 4), load_csv(open_meteo, 4),
                           column=OPEN_METEO_REF, test_column=DAY1, tolerance=None,
                           x_range=x_range, max_intervals=5)
    texts = _svg_texts(render(outcome.data, "svg"))
    assert texts[:5] == ["2026-11-10 00:00", "11-10 12:00", "11-11 00:00", "11-11 12:00",
                         "11-12 00:00"]


def test_offset_axis_is_labelled_utc(write_csv: WriteCsv) -> None:
    rows = "".join(f"2026-11-20T{h:02d}:00Z,{h % 3}\n" for h in range(24))
    p = write_csv("a.csv", "time,y\n" + rows)
    outcome = prepare_plot(load_csv(p), load_csv(p), column="y", tolerance=None,
                           x_range=None, max_intervals=5)
    assert outcome.data.x_label == "time (UTC)"
    assert outcome.data.subtitle.startswith("tolerances [default]: x 0  |")


@pytest.mark.parametrize(
    ("lo", "hi", "labels"),
    [
        (0.0, 3600.0, ["1970-01-01 00:00", "01-01 00:10", "01-01 00:20", "01-01 00:30",
                       "01-01 00:40", "01-01 00:50", "01-01 01:00"]),
        (0.0, 30.0, ["1970-01-01 00:00:00", "00:00:05", "00:00:10", "00:00:15", "00:00:20",
                     "00:00:25", "00:00:30"]),
        (0.0, 1.0, ["1970-01-01 00:00:00.0", "00:00:00.2", "00:00:00.4", "00:00:00.6",
                    "00:00:00.8", "00:00:01.0"]),
        (1798761600.0 - 2 * 86400, 1798761600.0 + 2 * 86400,  # around 2027-01-01
         ["2026-12-30", "12-31", "2027-01-01", "01-02", "01-03"]),
    ],
)
def test_date_ticks_and_labels(lo: float, hi: float, labels: list[str]) -> None:
    ticks, step = date_ticks(lo, hi)
    assert date_labels(ticks, step) == labels
    assert all(lo <= t <= hi for t in ticks)
