"""``plot_signals``: draw one funnel comparison (SVG / PNG).

The comparison itself is :func:`simtest_funnel_mcp.compare.run_compare` on
the full-resolution data, so the verdict and the summary row are exactly
those of ``compare_signals`` with the same arguments. Only the drawing is
reduced: reference and test with :func:`simtest.funnel.downsample_min_max`
(the ``worst_x`` of every violation interval pinned), tube bounds as the
library returns them.

matplotlib is imported lazily inside :func:`render` so that it does not
slow down server start-up.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

import simtest.funnel as funnel
from simtest_funnel_mcp.compare import CompareOutcome, RowRecord, run_compare
from simtest_funnel_mcp.csvio import SignalFile
from simtest_funnel_mcp.models import COEFFICIENTS, Coefficients, ToleranceSet, XRange
from simtest_funnel_mcp.selection import is_pattern

#: Min/max buckets for reference and test: at most ~2 points per bucket, so
#: about 2000 points per series, more than the horizontal pixels of any
#: rendering (1600 px PNG file) while keeping the SVG small.
DEFAULT_BUCKETS = 1000
#: Figure size in inches (SVG document size 576 x 324 pt).
FIGURE_SIZE_IN = (8.0, 4.5)
#: Inline preview: 800 x 450 px.
PREVIEW_DPI = 100
#: PNG file output: 1600 x 900 px.
PNG_FILE_DPI = 200
#: Violation regions narrower than this fraction of the view are widened
#: (centred) so a single-sample violation stays visible (~3 px at 800 px).
MIN_REGION_FRACTION = 0.004

#: Above this many tube points (lower + upper) the grey band between the
#: bounds is rasterized in SVG output (at :data:`SVG_RASTER_DPI`): a filled
#: polygon is never simplified by the renderer, so a 200k-point tube would
#: otherwise make a ~10 MB SVG. The bound lines themselves stay vector.
TUBE_VECTOR_MAX_POINTS = 20_000
#: Resolution of rasterized parts of an SVG (the tube band only).
SVG_RASTER_DPI = 200

#: SVG ``id`` of the artists; tests and users can find them in the file.
GID_REFERENCE = "reference"
GID_TEST = "test"
GID_TUBE = "tube"
GID_VIOLATION_REGIONS = "violation-regions"
GID_VIOLATION_MARKERS = "violation-markers"

# Colours (validated categorical slots on a white surface) and inks.
_INK = "#0b0b0b"
_INK_2 = "#52514e"
_GRID = "#e4e4e0"
_REFERENCE = "#3d3d3a"
_TEST = "#2a78d6"
_TUBE = "#8a8984"
_VIOLATION = "#e34948"
_VIOLATION_MARK = "#c62f2e"

#: rcParams for every rendering (``Any`` keys: matplotlib types them as literals).
_RC: dict[Any, Any] = {
    # Determinism: fixed hash salt for SVG ids, bundled font only.
    "svg.hashsalt": "simtest-funnel",
    "svg.fonttype": "path",
    "font.family": "DejaVu Sans",
    "font.size": 9.0,
    "axes.titlesize": 10.0,
    "axes.titlelocation": "left",
    "axes.labelsize": 9.0,
    "axes.edgecolor": _TUBE,
    "axes.labelcolor": _INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": _GRID,
    "grid.linewidth": 0.6,
    "xtick.color": _INK_2,
    "ytick.color": _INK_2,
    "text.color": _INK,
    "legend.fontsize": 8.5,
    "path.simplify": True,
    "agg.path.chunksize": 20000,
}


class PlotArgumentError(ValueError):
    """Invalid ``plot_signals`` arguments, or a comparison that cannot be drawn."""


@dataclass(frozen=True)
class PlotData:
    """Everything the renderer draws (already reduced)."""

    title: str
    subtitle: str
    x_label: str
    y_label: str
    view: tuple[float, float]
    ref_x: NDArray[np.float64]
    ref_y: NDArray[np.float64]
    test_x: NDArray[np.float64]
    test_y: NDArray[np.float64]
    lower_x: NDArray[np.float64]
    lower_y: NDArray[np.float64]
    upper_x: NDArray[np.float64]
    upper_y: NDArray[np.float64]
    #: Test points drawn that lie outside the tube (judged and deviation != 0).
    marker_x: NDArray[np.float64]
    marker_y: NDArray[np.float64]
    #: Shaded x-intervals (widened and merged violation intervals).
    regions: tuple[tuple[float, float], ...]
    buckets: int


@dataclass
class PlotOutcome:
    compare: CompareOutcome
    record: RowRecord
    data: PlotData


def _fmt(v: float) -> str:
    return f"{v:.4g}"


def tolerance_text(label: str, c: Coefficients) -> str:
    """``tolerances [label]: x atolx=0.1 | y rtoly=0.01`` (zero coefficients omitted)."""

    def axis(suffix: str) -> str:
        values = {k: float(getattr(c, k)) for k in COEFFICIENTS if k.endswith(suffix)}
        nonzero = [f"{k}={_fmt(v)}" for k, v in values.items() if v != 0]
        return " ".join(nonzero) if nonzero else "0"

    return f"tolerances [{label}]: x {axis('x')}  |  y {axis('y')}"


def _index_window(x: NDArray[np.float64], lo: float, hi: float) -> tuple[int, int]:
    """Contiguous index range covering every sample in ``[lo, hi]`` plus one
    neighbour on each side (so lines run to the axes edges)."""
    inside = np.flatnonzero((x >= lo) & (x <= hi))
    if inside.shape[0] == 0:
        return 0, 0
    i0 = max(int(inside[0]) - 1, 0)
    i1 = min(int(inside[-1]) + 2, x.shape[0])
    return i0, i1


def widen_and_merge(
    intervals: list[tuple[float, float]], min_width: float
) -> tuple[tuple[float, float], ...]:
    """Widen intervals narrower than ``min_width`` (centred) and merge overlaps."""
    out: list[tuple[float, float]] = []
    for a, b in sorted(intervals):
        if b - a < min_width:
            mid = 0.5 * (a + b)
            a, b = mid - 0.5 * min_width, mid + 0.5 * min_width
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return tuple(out)


def prepare_plot(
    ref: SignalFile,
    tst: SignalFile,
    *,
    column: str,
    tolerance: ToleranceSet | None,
    x_range: XRange | None,
    max_intervals: int,
    buckets: int = DEFAULT_BUCKETS,
) -> PlotOutcome:
    """Compare one column on the full data and reduce it for drawing."""
    if not column.strip():
        raise PlotArgumentError("column is empty")
    known = set(ref.signal_columns) | set(tst.signal_columns)
    if column not in known and is_pattern(column):
        raise PlotArgumentError(
            f"column {column!r} is not a column name; plot_signals takes one exact column "
            "name (no glob patterns)"
        )
    outcome = run_compare(
        ref,
        tst,
        columns=[column],
        tolerances=[tolerance if tolerance is not None else ToleranceSet(label="default")],
        x_range=x_range,
        max_intervals=max_intervals,
        max_rows=1,
    )
    record = outcome.records[0]
    row = record.row
    if row.verdict == "error" or record.library is None:
        status = f" ({row.status_name})" if row.status_name else ""
        notes = "".join(f"; note: {n}" for n in outcome.result.notes)
        raise PlotArgumentError(
            f"cannot plot column {column!r}: verdict error{status}: {row.problem}{notes}. "
            "No file was written."
        )
    res, summary = record.library
    lo_req, hi_req = outcome.x_range

    # View: the requested x_range, clipped to the data of both files.
    t_ref = ref.time
    t_tst = tst.time
    data_lo = float(min(t_ref[0], t_tst[0]))
    data_hi = float(max(t_ref[-1], t_tst[-1]))
    v_lo = data_lo if lo_req is None else max(lo_req, data_lo)
    v_hi = data_hi if hi_req is None else min(hi_req, data_hi)

    y_ref = ref.values[column]
    y_tst = tst.values[column]
    r0, r1 = _index_window(t_ref, v_lo, v_hi)
    ref_ds = funnel.downsample_min_max(t_ref[r0:r1], y_ref[r0:r1], buckets)
    pins = np.array([iv.worst_x for iv in summary.intervals], dtype=np.float64)
    t0, t1 = _index_window(t_tst, v_lo, v_hi)
    tst_ds = funnel.downsample_min_max(t_tst[t0:t1], y_tst[t0:t1], buckets, pins)

    # Violating test points on the full data, judged exactly as summarize
    # does (deviation != 0 within x_range intersected with the reference span).
    err_x, err_y = res.errors
    if err_x.shape[0] != t_tst.shape[0]:  # pragma: no cover - library invariant
        raise PlotArgumentError("library returned deviations on an unexpected grid")
    eff_lo = max(float("-inf") if lo_req is None else lo_req, float(t_ref[0]))
    eff_hi = min(float("inf") if hi_req is None else hi_req, float(t_ref[-1]))
    violating = (err_y != 0.0) & (err_x >= eff_lo) & (err_x <= eff_hi)
    drawn_violating = violating[t0 + tst_ds.indices]

    (lx, ly), (ux, uy) = res.lower, res.upper
    l0, l1 = _index_window(lx, v_lo, v_hi)
    u0, u1 = _index_window(ux, v_lo, v_hi)

    span = v_hi - v_lo
    regions = widen_and_merge(
        [(iv.start_x, iv.end_x) for iv in summary.intervals],
        MIN_REGION_FRACTION * span if span > 0 else 0.0,
    )

    label = row.tolerance_set
    resolved = outcome.result.tolerance_sets[0].resolved
    if row.verdict == "fail":
        headline = (
            f"{column}: FAIL, {summary.points_outside} of {summary.points_compared} points "
            f"outside the tube, {len(summary.intervals)} violation interval(s)"
        )
    else:
        headline = f"{column}: PASS, all {summary.points_compared} points inside the tube"
    data = PlotData(
        title=headline,
        subtitle=tolerance_text(label, resolved),
        x_label=ref.time_column,
        y_label=column,
        view=(v_lo, v_hi),
        ref_x=ref_ds.x,
        ref_y=ref_ds.y,
        test_x=tst_ds.x,
        test_y=tst_ds.y,
        lower_x=lx[l0:l1],
        lower_y=ly[l0:l1],
        upper_x=ux[u0:u1],
        upper_y=uy[u0:u1],
        marker_x=tst_ds.x[drawn_violating],
        marker_y=tst_ds.y[drawn_violating],
        regions=regions,
        buckets=buckets,
    )
    return PlotOutcome(compare=outcome, record=record, data=data)


def render(data: PlotData, fmt: Literal["svg", "png"], dpi: float = PREVIEW_DPI) -> bytes:
    """Render ``data`` to SVG or PNG bytes (deterministic for equal input)."""
    import matplotlib
    from matplotlib.artist import Artist
    from matplotlib.collections import PolyCollection
    from matplotlib.figure import Figure
    from matplotlib.legend_handler import HandlerTuple
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from matplotlib.transforms import blended_transform_factory

    with matplotlib.rc_context(_RC):
        fig = Figure(figsize=FIGURE_SIZE_IN, facecolor="white", layout="constrained")
        ax = fig.add_subplot()
        ax.set_facecolor("white")
        ax.set_axisbelow(True)

        if data.regions:
            trans = blended_transform_factory(ax.transData, ax.transAxes)
            rects = [[(a, 0.0), (b, 0.0), (b, 1.0), (a, 1.0)] for a, b in data.regions]
            regions = PolyCollection(
                rects,
                transform=trans,
                facecolors=_VIOLATION,
                alpha=0.16,
                edgecolors="none",
                zorder=0.5,
            )
            regions.set_gid(GID_VIOLATION_REGIONS)
            ax.add_collection(regions, autolim=False)

        # Tube: band (lower forward, upper backward) plus thin bound lines.
        band_x = np.concatenate([data.lower_x, data.upper_x[::-1]])
        band_y = np.concatenate([data.lower_y, data.upper_y[::-1]])
        if band_x.shape[0]:
            # A collection, not ax.fill: patch limits iterate Bezier segments
            # in Python (seconds for 400k vertices).
            band = PolyCollection(
                [np.column_stack([band_x, band_y])],
                facecolors=_TUBE,
                alpha=0.22,
                edgecolors="none",
                zorder=1,
            )
            band.set_gid(GID_TUBE)
            band.set_rasterized(band_x.shape[0] > TUBE_VECTOR_MAX_POINTS)
            ax.add_collection(band, autolim=True)
        ax.plot(data.lower_x, data.lower_y, color=_TUBE, linewidth=0.8, zorder=1.1)
        ax.plot(data.upper_x, data.upper_y, color=_TUBE, linewidth=0.8, zorder=1.1)

        ax.plot(
            data.ref_x, data.ref_y, color=_REFERENCE, linewidth=1.3,
            linestyle=(0, (5.0, 2.5)), zorder=3, gid=GID_REFERENCE,
        )
        ax.plot(
            data.test_x, data.test_y, color=_TEST, linewidth=1.3, zorder=2, gid=GID_TEST,
        )
        if data.marker_x.shape[0]:
            ax.plot(
                data.marker_x, data.marker_y, linestyle="none", marker="x", markersize=4.5,
                markeredgewidth=1.2, color=_VIOLATION_MARK, zorder=4,
                gid=GID_VIOLATION_MARKERS,
            )

        lo, hi = data.view
        if hi > lo:
            ax.set_xlim(lo, hi)
        ax.set_xlabel(data.x_label)
        ax.set_ylabel(data.y_label)
        ax.set_title(f"{data.title}\n{data.subtitle}", loc="left", fontsize=9.5)

        handles: list[Artist | tuple[Artist, ...]] = [
            Line2D([], [], color=_REFERENCE, linewidth=1.3, linestyle=(0, (5.0, 2.5))),
            Line2D([], [], color=_TEST, linewidth=1.3),
            Patch(facecolor=_TUBE, alpha=0.35, edgecolor=_TUBE, linewidth=0.8),
        ]
        labels = ["reference", "test", "tolerance tube"]
        if data.regions or data.marker_x.shape[0]:
            handles.append(
                (
                    Patch(facecolor=_VIOLATION, alpha=0.25, edgecolor="none"),
                    Line2D([], [], linestyle="none", marker="x", markersize=4.5,
                           markeredgewidth=1.2, color=_VIOLATION_MARK),
                )
            )
            labels.append("outside the tube")
        ax.legend(
            handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=len(labels),
            frameon=False, handler_map={tuple: HandlerTuple(ndivide=None, pad=0.0)},
            handlelength=2.6,
        )

        buf = io.BytesIO()
        if fmt == "svg":
            fig.savefig(
                buf, format="svg", dpi=SVG_RASTER_DPI,
                metadata={"Date": None, "Creator": "simtest-funnel-mcp"},
            )
        else:
            fig.savefig(buf, format="png", dpi=dpi, metadata={"Software": None})
        return buf.getvalue()


def png_size(data: bytes) -> tuple[int, int]:
    """``(width, height)`` from a PNG's IHDR chunk."""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)
