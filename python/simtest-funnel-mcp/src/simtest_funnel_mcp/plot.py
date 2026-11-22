"""``plot_signals``: draw one funnel comparison (SVG / PNG).

The comparison itself is :func:`simtest_funnel_mcp.compare.run_compare` on
the full-resolution data, so the verdict and the summary row are exactly
those of ``compare_signals`` with the same arguments. Only the drawing is
reduced, with :func:`simtest.funnel.downsample_min_max`: reference and test
(the ``worst_x`` of every violation interval pinned) and the tube bounds,
to which the exact bound value is added at the x of drawn test points where
needed (see :func:`reduce_bound`), so every drawn test point lies inside or
outside the drawn tube exactly as the comparison judged it.

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

#: Min/max buckets for reference, test and tube bounds: at most ~2 points
#: per bucket, so about 2000 points per series, more than the horizontal
#: pixels of any rendering (1600 px PNG file) while keeping the SVG small.
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

#: Bound segments shorter than this in x are evaluated as their left end,
#: exactly as the library's interpolation does (``errors.rs``).
_LIBRARY_DEGENERATE_DX = 1e-10

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


def bound_at(
    bx: NDArray[np.float64], by: NDArray[np.float64], x: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Evaluate a tube bound at ``x`` exactly as the library does.

    Same arithmetic as ``interpolate_clamped`` in the core's ``errors.rs``
    (linear interpolation on the segment ending at the first vertex with
    ``bx >= x``, left value on segments shorter than 1e-10, clamped to the
    end values outside the bound), so the values are bit-identical to the
    bounds the comparison judged each test point against. ``bx`` must be
    non-decreasing.

    Returns ``(values, keys)``: ``keys`` is a fractional vertex index
    (``j - 0.5`` for a point on the segment ``(j - 1, j)``), used to merge
    the points into the bound polyline in order.
    """
    n = bx.shape[0]
    if n == 1:
        return np.full(x.shape, by[0]), np.where(x <= bx[0], -0.5, 0.5)
    j = np.clip(np.searchsorted(bx, x, side="left"), 1, n - 1)
    x0, x1, y0, y1 = bx[j - 1], bx[j], by[j - 1], by[j]
    dx = x1 - x0
    degenerate = np.abs(dx) < _LIBRARY_DEGENERATE_DX
    with np.errstate(divide="ignore", invalid="ignore"):
        val = y0 + (y1 - y0) * (x - x0) / np.where(degenerate, 1.0, dx)
    val = np.where(degenerate, y0, val)
    key = j.astype(np.float64) - 0.5
    after, before = x >= bx[-1], x <= bx[0]
    val = np.where(after, by[-1], val)
    key = np.where(after, n - 0.5, key)
    val = np.where(before, by[0], val)
    key = np.where(before, -0.5, key)
    return val, key


def polyline_extent_at(
    px: NDArray[np.float64], py: NDArray[np.float64], x: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Lowest and highest value of the drawn polyline ``(px, py)`` at ``x``.

    ``px`` must be non-decreasing. At an x with vertices (possibly several,
    a vertical segment) the extent covers all of them; between vertices it
    is the linear interpolation; outside the polyline it is empty
    (``lo = +inf``, ``hi = -inf``).
    """
    n = px.shape[0]
    lo = np.full(x.shape, np.inf)
    hi = np.full(x.shape, -np.inf)
    if n == 0:
        return lo, hi
    a = np.searchsorted(px, x, side="left")
    b = np.searchsorted(px, x, side="right")
    at = b > a
    if at.any():
        start = np.ones(n, dtype=bool)
        start[1:] = px[1:] != px[:-1]
        starts = np.flatnonzero(start)
        run = np.cumsum(start) - 1
        r = run[a[at]]
        lo[at] = np.minimum.reduceat(py, starts)[r]
        hi[at] = np.maximum.reduceat(py, starts)[r]
    mid = ~at & (a > 0) & (a < n)
    i = a[mid]
    x0, x1, y0, y1 = px[i - 1], px[i], py[i - 1], py[i]
    val = y0 + (y1 - y0) * (x[mid] - x0) / (x1 - x0)
    lo[mid] = val
    hi[mid] = val
    return lo, hi


def reduce_bound(
    bx: NDArray[np.float64],
    by: NDArray[np.float64],
    *,
    upper: bool,
    view: tuple[float, float],
    buckets: int,
    test_x: NDArray[np.float64],
    test_y: NDArray[np.float64],
    judged: NDArray[np.bool_],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """The tube bound to draw: min/max reduction plus exact points.

    The bound vertices in the view (plus one neighbour on each side) are
    reduced with :func:`simtest.funnel.downsample_min_max`, which keeps the
    bound's lowest and highest vertex per bucket (outward and inward
    excursions alike). Then, for every drawn test point ``(test_x, test_y)``
    the comparison judges (``judged``), the drawn bound must agree with the
    library's bound value ``b`` at that x (:func:`bound_at`):

    * a point on the inner side (``y <= b`` for the upper bound, ``y >= b``
      for the lower) must also be on the inner side of the whole drawn bound
      at that x (:func:`polyline_extent_at`);
    * a point outside the bound must be at least as far outside the drawn
      bound as outside the true one (drawn bound at that x not wider than
      ``b``).

    Where a point fails (or the drawn polyline does not reach its x), the
    exact point ``(x, b)`` is inserted into the
    drawn polyline; this repeats until no point fails (an exact point
    satisfies both rules, so at most one insertion per drawn test point).
    A bound whose x decreases somewhere (not produced by the library in
    practice) cannot be reduced and is drawn with all its points in the
    view.
    """
    if bx.shape[0] == 0:
        return bx, by
    if np.any(np.diff(bx) < 0):  # pragma: no cover - library returns monotonic bounds
        w0, w1 = _index_window(bx, *view)
        return bx[w0:w1], by[w0:w1]
    w0 = max(int(np.searchsorted(bx, view[0], side="left")) - 1, 0)
    w1 = min(int(np.searchsorted(bx, view[1], side="right")) + 1, bx.shape[0])
    ds = funnel.downsample_min_max(bx[w0:w1], by[w0:w1], buckets)
    xs, ys = ds.x, ds.y
    keys = (ds.indices + w0).astype(np.float64)

    tx, ty = test_x[judged], test_y[judged]
    true_y, true_key = bound_at(bx, by, tx)
    # Signed so that "inner side" is <= 0 for both bounds.
    sign = 1.0 if upper else -1.0
    inner = sign * (ty - true_y) <= 0.0
    inserted = np.zeros(tx.shape[0], dtype=bool)
    while True:
        lo, hi = polyline_extent_at(xs, ys, tx)
        drawn = hi if upper else lo  # the outermost drawn value at x
        # Not covered by the drawn polyline at all also counts as failing.
        bad = (
            np.where(inner, sign * (ty - drawn) > 0.0, sign * (drawn - true_y) > 0.0)
            | ~np.isfinite(drawn)
        ) & ~inserted
        if not bad.any():
            break
        inserted |= bad
        xs = np.concatenate([xs, tx[bad]])
        ys = np.concatenate([ys, true_y[bad]])
        keys = np.concatenate([keys, true_key[bad]])
        order = np.lexsort((xs, keys))
        xs, ys, keys = xs[order], ys[order], keys[order]
    keep = np.ones(xs.shape[0], dtype=bool)
    keep[1:] = (xs[1:] != xs[:-1]) | (ys[1:] != ys[:-1])
    return xs[keep], ys[keep]


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
    lx, ly, ux, uy = (np.asarray(a, dtype=np.float64) for a in (lx, ly, ux, uy))
    drawn_judged = ((tst_ds.x >= eff_lo) & (tst_ds.x <= eff_hi))
    bound_args: dict[str, Any] = {
        "view": (v_lo, v_hi), "buckets": buckets, "test_x": tst_ds.x, "test_y": tst_ds.y,
        "judged": drawn_judged,
    }
    lower_x, lower_y = reduce_bound(lx, ly, upper=False, **bound_args)
    upper_x, upper_y = reduce_bound(ux, uy, upper=True, **bound_args)

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
        lower_x=lower_x,
        lower_y=lower_y,
        upper_x=upper_x,
        upper_y=upper_y,
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
            # in Python (slow for long bounds).
            band = PolyCollection(
                [np.column_stack([band_x, band_y])],
                facecolors=_TUBE,
                alpha=0.22,
                edgecolors="none",
                zorder=1,
            )
            band.set_gid(GID_TUBE)
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
                buf, format="svg",
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
