"""The MCP server: tool registration, workspace roots and path resolution."""

from __future__ import annotations

import argparse
import base64
import io
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse
from urllib.request import url2pathname

from mcp.server.mcpserver import Context, ListRoots, MCPServer, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import (
    CallToolResult,
    ImageContent,
    ListRootsResult,
    TextContent,
    ToolAnnotations,
)
from pydantic import Field

import simtest.funnel as funnel
from simtest_funnel_mcp import __version__
from simtest_funnel_mcp.compare import (
    DEFAULT_MAX_INTERVALS,
    DEFAULT_MAX_ROWS,
    CompareArgumentError,
    run_compare,
)
from simtest_funnel_mcp.csvio import SignalFile, SignalFileError, load_csv
from simtest_funnel_mcp.describe import DEFAULT_MAX_COLUMNS, describe
from simtest_funnel_mcp.models import (
    CompareResult,
    DescribeResult,
    DrawnPoints,
    PlotFile,
    PlotPreview,
    PlotResult,
    RangeOut,
    ToleranceSet,
    ToleranceSpec,
    XRange,
)
from simtest_funnel_mcp.plot import (
    PNG_FILE_DPI,
    PREVIEW_DPI,
    PlotArgumentError,
    PlotData,
    png_size,
    prepare_plot,
    render,
)
from simtest_funnel_mcp.render import (
    render_compare,
    render_describe,
    render_plot,
    time_digits,
)
from simtest_funnel_mcp.snippet import make_snippet

SERVER_NAME = "simtest-funnel"

INSTRUCTIONS = """\
Funnel (tolerance-tube) comparison of signals stored in local CSV files
(comma-separated, header row, '#' comment lines, one shared time column).
The server reads the files itself; never paste sample values into a call.
Typical flow: describe_signals on the reference to see columns, time span,
sampling and value ranges; choose tolerances; compare_signals; plot_signals
to look at one column (inline PNG preview) and optionally save the plot as
an SVG or PNG file for a document. Use absolute paths. Stateless: pass the
paths on every call. Only plot_signals writes, and only the output_path
it is given (never an existing file unless overwrite=true), which must lie
inside a workspace root declared by the client or an output directory
configured when the server was started; with neither, omit output_path
and use the inline preview."""

CSV_HELP = (
    "CSV dialect: comma-separated, one header row, lines whose first non-blank character "
    "is '#' ignored ('#' elsewhere is data); a data row with more fields than the header "
    "is an error. "
    "Time column: the first column named 'time' (case-insensitive), otherwise the first "
    "column; the choice is echoed back."
)

DESCRIBE_DESCRIPTION = f"""\
Describe a local CSV signal file without returning sample values: time column, row
count, time start/end/span, sampling (uniform or not; min/median/max step), and for
every signal column its min, max and range, plus data problems (non-numeric or
empty cells, time column not non-decreasing). Use it to pick columns and sensible
tolerances before compare_signals. At most max_columns columns (default
{DEFAULT_MAX_COLUMNS}) and as many problems are listed; the result states the totals and
how many were omitted. 'columns' filters by exact name or glob pattern ('*', '?',
'[...]'), e.g. ["*.port.signal", "time_*"]. {CSV_HELP}"""

COMPARE_DESCRIPTION = f"""\
Compare signals of a test CSV file against a reference CSV file with the funnel
(tolerance tube) algorithm of LBNL Funnel. A tube is built around the reference
curve. A column passes when every test point inside the compared time range
(x_range intersected with the reference time span) lies inside the tube and, within
x_range, both files cover the same time span. If one file covers more time than the
other within x_range, the row is an error (MISSING_REFERENCE: test extends beyond
the reference; MISSING_TEST: the reverse) whose problem text gives both time spans
and the x_range that compares the overlap. Returns one row per (column, tolerance set) with verdict
(pass/fail/error), status code, points outside, worst deviation and, for failures
only, the violation intervals (largest deviation first, capped by max_intervals).
{CSV_HELP}

TOLERANCES - six coefficients, x = time axis, y = signal value. At each reference
sample the tube half-widths are
  half_x = max(atolx, rtolx * time_span_ref, ltolx * |t|)
  half_y = max(atoly, rtoly * value_range_ref, ltoly * |y_ref|)
where time_span_ref and value_range_ref are max - min of the reference time and
of the reference column within the compared range. If a half-width comes out
effectively zero (< 1e-10), e.g. rtoly alone on a constant reference, it falls back
to rtol * max|reference value| on that axis (when rtol > 0), then to 1e-10; for
constant or near-constant signals give atoly explicitly.
  atolx/atoly: absolute (time units / signal units)
  rtolx/rtoly: fraction of the reference time span / value range
  ltolx/ltoly: fraction of the local |t| / |y_ref|
Resolution rule (applied by the library, echoed back as six resolved values): for
each axis, if none of its three coefficients is given that axis gets the default
rtol = 0.002 (0.2 % of the range); if any is given, the axis's other coefficients
are 0. An explicit 0 counts as given (atolx=0 means no time tolerance).

TOLERANCE IN X: the tube is also widened along time. A test curve that is shifted
or delayed by up to half_x still passes, so small timing offsets and steep edges
(steps, switching events) do not cause false failures. A pure value tolerance
(x axis given as 0) flags every slightly shifted edge.

Example "1 % in y, 0.5 s in x": {{"rtoly": 0.01, "atolx": 0.5}} (1 % of the reference
value range). For 1 % of the local value use "ltoly": 0.01; to allow both use
"rtoly"/"ltoly" together (the max applies). Example "within 0.05 units, no time
tolerance": {{"atoly": 0.05, "atolx": 0}}.

Pass several labelled sets in 'tolerances' to try e.g. strict and loose in one
call. 'column_tolerances' overrides the sets per column, axis by axis: an axis for
which the override gives any coefficient is taken entirely from the override.
'columns' accepts exact names and glob patterns ('*', '?', '[...]').
Columns missing from a file or with bad data are reported per row (verdict
'error'), not as a failed call. Set include_snippet=true to get a pytest file that
reproduces the returned rows in CI; it is returned in the structured content field
'snippet' only. Its data paths are relative to the first workspace root (else the
server's working directory) and resolved against $SIMTEST_FUNNEL_DATA_ROOT or the
current directory, so commit the CSV files at the same relative location."""

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

PLOT_DESCRIPTION = f"""\
Plot ONE funnel comparison - one signal column, one tolerance set - and return a
small PNG preview (800x450) inline as image content so you can look at it. The plot
shows the reference (dashed), the test (solid), the tolerance tube (grey band
between its lower and upper bound) and every region where the test leaves the tube
(red shading plus x markers on the violating test points). The title states the
column, the verdict and the resolved tolerances; axis labels are the time column and
the signal column. The comparison runs on the full data with exactly the semantics
of compare_signals (same tolerance resolution, same x_range meaning, same coverage
rule), so the plot never contradicts compare_signals with the same arguments; only
the drawing is reduced (min/max per bucket, the worst point of every violation kept).
The result carries the same summary row as compare_signals, never sample values.

output_path (optional): write the plot to this file - SVG (for documents; white
background, fonts embedded as paths, byte-identical for identical input) when it
ends in .svg, PNG (1600x900) when it ends in .png. The directory must already exist.
The file must lie inside a workspace root declared by the client or inside an output
directory configured when the server was started (--output-dir /
SIMTEST_FUNNEL_MCP_OUTPUT_DIR); with neither, writing is refused. A relative path is
taken relative to the first workspace root, else the first output directory. An
existing file is refused unless overwrite=true. Omit output_path to get only the
inline preview (nothing is written). SVG is never returned inline.

x_range restricts the comparison exactly as in compare_signals (rtol bases are
computed within it) and is also the time window shown, so it doubles as zoom.
A column that cannot be compared (missing, bad data, time ranges that differ,
non-monotonic time) is an error and nothing is written; use compare_signals to see
all problems. Tolerance coefficients: see compare_signals. {CSV_HELP}"""

PLOT = ToolAnnotations(
    read_only_hint=False,
    # Replaces an existing file when (and only when) overwrite=true.
    destructive_hint=True,
    # Same arguments give the same file (deterministic) or the same refusal.
    idempotent_hint=True,
    open_world_hint=False,
)

#: Allowed output file extensions and their formats.
_PLOT_FORMATS: dict[str, Literal["svg", "png"]] = {".svg": "svg", ".png": "png"}
#: Colours kept in the inline preview (visually identical, ~1/3 of the bytes).
PREVIEW_COLORS = 128

mcp = MCPServer(
    SERVER_NAME,
    instructions=INSTRUCTIONS,
    version=__version__,
)


# --------------------------------------------------------------------------
# Workspace roots and paths
# --------------------------------------------------------------------------


def workspace_roots(ctx: Context) -> ListRoots | ListRootsResult:
    """Ask the client for its roots if it declared the capability."""
    caps = ctx.client_capabilities
    if caps is not None and caps.roots is not None:
        return ListRoots()
    return ListRootsResult(roots=[])


Roots = Annotated[ListRootsResult, Resolve(workspace_roots)]


def root_paths(roots: ListRootsResult, ignored: list[str] | None = None) -> list[Path]:
    """Resolved local directories of the client's ``file://`` roots.

    Only local roots (empty host or ``localhost``) are used; others, and
    non-``file`` URIs, are skipped and described in ``ignored`` if given.
    """
    out: list[Path] = []
    for root in roots.roots:
        uri = str(root.uri)
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            if ignored is not None:
                ignored.append(f"workspace root {uri} ignored: not a file:// URI")
            continue
        if parsed.netloc not in ("", "localhost"):
            if ignored is not None:
                ignored.append(f"workspace root {uri} ignored: host {parsed.netloc!r} is not local")
            continue
        out.append(Path(url2pathname(parsed.path)).resolve())
    return out


def resolve_path(raw: str, roots: list[Path]) -> Path:
    """Resolve ``raw`` and enforce the roots (if any)."""
    if not raw.strip():
        raise ToolError("path is empty")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (roots[0] if roots else Path.cwd()) / p
    resolved = p.resolve()
    if roots and not any(resolved.is_relative_to(r) for r in roots):
        listed = ", ".join(str(r) for r in roots)
        raise ToolError(f"{resolved} is outside the client's workspace roots ({listed})")
    return resolved


#: Environment variable naming output directories for plot files (several
#: separated by ``os.pathsep``), in addition to ``--output-dir``.
OUTPUT_DIR_ENV = "SIMTEST_FUNNEL_MCP_OUTPUT_DIR"

#: Output directories configured at start-up (:func:`main`); empty unless
#: the user configured one explicitly.
_output_dirs: list[Path] = []


def configured_output_dirs() -> list[Path]:
    """The output directories configured when the server was started."""
    return list(_output_dirs)


NO_WRITE_LOCATION = (
    "plot_signals cannot write output_path: the client declared no workspace roots "
    "and the server was started without an output directory. To enable writing, "
    "either use a client that declares workspace roots (e.g. Claude Code), or start "
    "the server with --output-dir DIR (or the environment variable "
    f"{OUTPUT_DIR_ENV}=DIR) naming an existing directory. Omit output_path to get "
    "only the inline preview."
)


def resolve_output_path(
    raw: str,
    roots: list[Path],
    overwrite: bool,
    output_dirs: Sequence[Path] = (),
) -> tuple[Path, Literal["svg", "png"]]:
    """Check a plot output path (a write) and return ``(resolved path, format)``.

    Stricter than :func:`resolve_path`: the file must lie inside a workspace
    root or a configured output directory (``output_dirs``); with neither,
    writing is refused. A relative path is taken relative to the first root,
    else the first output directory. The extension must be ``.svg`` or
    ``.png`` (also after following a symbolic link) and the directory must
    already exist. An existing file is refused unless ``overwrite``; a
    directory or other non-regular file always is.
    """
    if not raw.strip():
        raise ToolError("output_path is empty")
    allowed = [*roots, *output_dirs]
    if not allowed:
        raise ToolError(NO_WRITE_LOCATION)
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = allowed[0] / p
    fmt = _PLOT_FORMATS.get(p.suffix.lower())
    if fmt is None:
        raise ToolError(f"output_path {p} must end in .svg or .png")
    parent = p.parent
    if not parent.is_dir():
        what = "is not a directory" if parent.exists() else "does not exist"
        raise ToolError(
            f"directory {parent} {what}; the server does not create directories"
        )
    target = (parent.resolve(strict=True) / p.name).resolve()
    if not any(target.is_relative_to(r) for r in allowed):
        scopes = []
        if roots:
            scopes.append(f"the client's workspace roots ({', '.join(map(str, roots))})")
        if output_dirs:
            scopes.append(
                f"the configured output directories ({', '.join(map(str, output_dirs))})"
            )
        raise ToolError(f"{target} is outside {' and '.join(scopes)}; not written")
    if _PLOT_FORMATS.get(target.suffix.lower()) != fmt:
        raise ToolError(f"output_path {p} resolves to {target}, which is not a .{fmt} file")
    if target.exists():
        if not target.is_file():
            raise ToolError(f"{target} exists and is not a regular file; not written")
        if not overwrite:
            raise ToolError(f"{target} already exists; pass overwrite=true to replace it")
    return target, fmt


def _write_plot(target: Path, data: bytes, overwrite: bool) -> None:
    """Write ``data``; without ``overwrite`` the file is created exclusively."""
    try:
        with open(target, "wb" if overwrite else "xb") as fh:
            fh.write(data)
    except FileExistsError as exc:
        raise ToolError(f"{target} already exists; pass overwrite=true to replace it") from exc
    except OSError as exc:
        raise ToolError(f"cannot write {target}: {exc}") from exc


def _preview_png(data: PlotData) -> bytes:
    """The inline preview: 800x450 PNG reduced to a small palette."""
    from PIL import Image

    raw = render(data, "png", PREVIEW_DPI)
    with Image.open(io.BytesIO(raw)) as im:
        quantized = im.convert("RGB").quantize(
            colors=PREVIEW_COLORS,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
    buf = io.BytesIO()
    quantized.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _load(raw: str, roots: list[Path]) -> SignalFile:
    try:
        return load_csv(resolve_path(raw, roots))
    except SignalFileError as exc:
        raise ToolError(str(exc)) from exc


#: Value fields rounded to 10 significant digits (drops binary noise such as
#: ``0.8035000000000001``). Time/x fields and tolerances are never rounded:
#: epoch-second times need every digit to tell adjacent samples apart.
_ROUNDED_KEYS = frozenset(
    {
        "min",
        "max",
        "range",
        "deviation",
        "worst_deviation",
        "tube_half_width_y",
        "fraction_of_points_outside",
        "fraction_of_span_outside",
    }
)


def _trim(value: object, key: str | None = None) -> object:
    """Round the value fields in :data:`_ROUNDED_KEYS` throughout a JSON-like
    structure; everything else is returned unchanged."""
    if isinstance(value, float):
        return float(f"{value:.10g}") if key in _ROUNDED_KEYS else value
    if isinstance(value, dict):
        return {k: _trim(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_trim(v, key) for v in value]
    return value


def _dump(model: DescribeResult | CompareResult | PlotResult) -> dict[str, object]:
    dumped = _trim(model.model_dump(mode="json", exclude_none=True))
    assert isinstance(dumped, dict)
    return dumped


# --------------------------------------------------------------------------
# Tool implementations (plain functions, also used by in-process tests)
# --------------------------------------------------------------------------


def describe_signals_impl(
    path: str,
    roots: list[Path],
    *,
    columns: list[str] | None = None,
    max_columns: int = DEFAULT_MAX_COLUMNS,
    root_notes: list[str] | None = None,
) -> CallToolResult:
    """Describe one file; see :data:`DESCRIBE_DESCRIPTION`."""
    sf = _load(path, roots)
    try:
        result = describe(sf, columns=columns, max_columns=max_columns)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    result.notes.extend(root_notes or [])
    return CallToolResult(
        content=[TextContent(type="text", text=render_describe(result, time_digits(sf.time)))],
        structured_content=_dump(result),
    )


def compare_signals_impl(
    reference_path: str,
    test_path: str,
    roots: list[Path],
    *,
    columns: list[str] | None = None,
    tolerances: list[ToleranceSet] | None = None,
    column_tolerances: dict[str, ToleranceSpec] | None = None,
    x_range: XRange | None = None,
    max_intervals: int = DEFAULT_MAX_INTERVALS,
    max_rows: int = DEFAULT_MAX_ROWS,
    include_snippet: bool = False,
    root_notes: list[str] | None = None,
) -> CallToolResult:
    """Compare two files; see :data:`COMPARE_DESCRIPTION`."""
    ref = _load(reference_path, roots)
    tst = _load(test_path, roots)
    try:
        outcome = run_compare(
            ref,
            tst,
            columns=columns,
            tolerances=tolerances,
            column_tolerances=column_tolerances,
            x_range=x_range,
            max_intervals=max_intervals,
            max_rows=max_rows,
        )
    except CompareArgumentError as exc:
        raise ToolError(str(exc)) from exc
    result = outcome.result
    result.notes.extend(root_notes or [])
    if include_snippet:
        base = roots[0] if roots else Path.cwd().resolve()
        try:
            result.snippet = make_snippet(outcome, __version__, funnel.version(), base)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
    text = render_compare(result, time_digits(ref.time, tst.time))
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=_dump(result),
    )


def plot_signals_impl(
    reference_path: str,
    test_path: str,
    roots: list[Path],
    *,
    column: str,
    tolerance: ToleranceSet | None = None,
    x_range: XRange | None = None,
    output_path: str | None = None,
    overwrite: bool = False,
    max_intervals: int = DEFAULT_MAX_INTERVALS,
    root_notes: list[str] | None = None,
    output_dirs: Sequence[Path] = (),
) -> CallToolResult:
    """Plot one comparison; see :data:`PLOT_DESCRIPTION`.

    ``output_dirs`` are the configured output directories (the tool passes
    :func:`configured_output_dirs`).
    """
    if max_intervals < 0:
        raise ToolError("max_intervals must be >= 0")
    # Check the output path before any work, write only after rendering.
    target = (
        resolve_output_path(output_path, roots, overwrite, output_dirs)
        if output_path is not None
        else None
    )
    ref = _load(reference_path, roots)
    tst = _load(test_path, roots)
    try:
        outcome = prepare_plot(
            ref, tst, column=column, tolerance=tolerance, x_range=x_range,
            max_intervals=max_intervals,
        )
    except (PlotArgumentError, CompareArgumentError) as exc:
        raise ToolError(str(exc)) from exc
    data = outcome.data
    preview = _preview_png(data)
    pw, ph = png_size(preview)
    file_out: PlotFile | None = None
    if target is not None:
        path, fmt = target
        blob = render(data, fmt) if fmt == "svg" else render(data, fmt, PNG_FILE_DPI)
        _write_plot(path, blob, overwrite)
        size = png_size(blob) if fmt == "png" else None
        file_out = PlotFile(
            path=str(path),
            format=fmt,
            bytes=len(blob),
            width_px=size[0] if size else None,
            height_px=size[1] if size else None,
        )
    cr = outcome.compare.result
    result = PlotResult(
        reference=cr.reference,
        test=cr.test,
        x_range=cr.x_range,
        tolerance_set=cr.tolerance_sets[0],
        row=outcome.record.row,
        view=RangeOut(lo=data.view[0], hi=data.view[1]),
        file=file_out,
        preview=PlotPreview(width_px=pw, height_px=ph, bytes=len(preview)),
        drawn=DrawnPoints(
            reference=int(data.ref_x.shape[0]),
            test=int(data.test_x.shape[0]),
            tube_lower=int(data.lower_x.shape[0]),
            tube_upper=int(data.upper_x.shape[0]),
            violation_markers=int(data.marker_x.shape[0]),
            violation_regions=len(data.regions),
            buckets=data.buckets,
        ),
        notes=[*cr.notes, *(root_notes or [])],
    )
    text = render_plot(result, time_digits(ref.time, tst.time))
    return CallToolResult(
        content=[
            TextContent(type="text", text=text),
            ImageContent(
                type="image",
                data=base64.b64encode(preview).decode("ascii"),
                mime_type="image/png",
            ),
        ],
        structured_content=_dump(result),
    )


# --------------------------------------------------------------------------
# MCP tools
# --------------------------------------------------------------------------


@mcp.tool(
    name="describe_signals",
    title="Describe CSV signals",
    description=DESCRIBE_DESCRIPTION,
    annotations=READ_ONLY,
)
def describe_signals(
    path: Annotated[str, Field(description="Path of the CSV file (absolute recommended).")],
    roots: Roots,
    columns: Annotated[
        list[str] | None,
        Field(
            description=(
                "Signal columns to describe: exact names or glob patterns ('*', '?', '[...]'); "
                "omit for all."
            )
        ),
    ] = None,
    max_columns: Annotated[
        int, Field(ge=1, description="Max columns (and problems) listed.")
    ] = DEFAULT_MAX_COLUMNS,
) -> Annotated[CallToolResult, DescribeResult]:
    ignored: list[str] = []
    paths = root_paths(roots, ignored)
    return describe_signals_impl(
        path, paths, columns=columns, max_columns=max_columns, root_notes=ignored
    )


@mcp.tool(
    name="compare_signals",
    title="Compare CSV signals (funnel)",
    description=COMPARE_DESCRIPTION,
    annotations=READ_ONLY,
)
def compare_signals(
    reference_path: Annotated[str, Field(description="Path of the reference CSV file.")],
    test_path: Annotated[str, Field(description="Path of the test CSV file.")],
    roots: Roots,
    columns: Annotated[
        list[str] | None,
        Field(
            description=(
                "Signal columns to compare: exact names or glob patterns ('*', '?', '[...]'); "
                "omit for all columns present in both files."
            )
        ),
    ] = None,
    tolerances: Annotated[
        list[ToleranceSet] | None,
        Field(
            description=(
                "Tolerance sets, each with an optional unique 'label' and any of atolx, atoly, "
                "ltolx, ltoly, rtolx, rtoly. Omit for one set with the library default."
            )
        ),
    ] = None,
    column_tolerances: Annotated[
        dict[str, ToleranceSpec] | None,
        Field(description="Per-column overrides (column name -> coefficients), applied per axis."),
    ] = None,
    x_range: Annotated[
        XRange | None,
        Field(
            description=(
                "Time window {lo, hi} to compare; bounds must be finite, omit a bound for "
                "unbounded."
            )
        ),
    ] = None,
    max_intervals: Annotated[
        int, Field(ge=0, description="Max violation intervals listed per failing row.")
    ] = DEFAULT_MAX_INTERVALS,
    max_rows: Annotated[
        int, Field(ge=1, description="Max rows returned (errors, then failures, then passes).")
    ] = DEFAULT_MAX_ROWS,
    include_snippet: Annotated[
        bool,
        Field(
            description=(
                "Include a pytest file reproducing the returned rows (structured field "
                "'snippet')."
            )
        ),
    ] = False,
) -> Annotated[CallToolResult, CompareResult]:
    ignored: list[str] = []
    paths = root_paths(roots, ignored)
    return compare_signals_impl(
        reference_path,
        test_path,
        paths,
        columns=columns,
        tolerances=tolerances,
        column_tolerances=column_tolerances,
        x_range=x_range,
        max_intervals=max_intervals,
        max_rows=max_rows,
        include_snippet=include_snippet,
        root_notes=ignored,
    )


@mcp.tool(
    name="plot_signals",
    title="Plot one CSV signal comparison (funnel)",
    description=PLOT_DESCRIPTION,
    annotations=PLOT,
)
def plot_signals(
    reference_path: Annotated[str, Field(description="Path of the reference CSV file.")],
    test_path: Annotated[str, Field(description="Path of the test CSV file.")],
    column: Annotated[
        str, Field(min_length=1, description="The one signal column to plot (exact name).")
    ],
    roots: Roots,
    tolerance: Annotated[
        ToleranceSet | None,
        Field(
            description=(
                "One tolerance set: optional 'label' and any of atolx, atoly, ltolx, ltoly, "
                "rtolx, rtoly (same as one entry of compare_signals 'tolerances'). Omit for "
                "the library default."
            )
        ),
    ] = None,
    x_range: Annotated[
        XRange | None,
        Field(
            description=(
                "Time window {lo, hi} to compare and show; bounds must be finite, omit a "
                "bound for unbounded."
            )
        ),
    ] = None,
    output_path: Annotated[
        str | None,
        Field(
            description=(
                "File to write: '.svg' (document) or '.png', inside a workspace root or the "
                "server's configured output directory. The directory must exist. Omit for "
                "the inline preview only."
            )
        ),
    ] = None,
    overwrite: Annotated[
        bool, Field(description="Replace output_path if it already exists.")
    ] = False,
    max_intervals: Annotated[
        int, Field(ge=0, description="Max violation intervals listed in the result row.")
    ] = DEFAULT_MAX_INTERVALS,
) -> Annotated[CallToolResult, PlotResult]:
    ignored: list[str] = []
    paths = root_paths(roots, ignored)
    return plot_signals_impl(
        reference_path,
        test_path,
        paths,
        column=column,
        tolerance=tolerance,
        x_range=x_range,
        output_path=output_path,
        overwrite=overwrite,
        max_intervals=max_intervals,
        root_notes=ignored,
        output_dirs=configured_output_dirs(),
    )


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simtest-funnel-mcp",
        description=(
            "Local MCP server (stdio) for funnel comparison of signals in CSV files. "
            "Reads are allowed anywhere (inside the client's workspace roots when it "
            "declares any); plot_signals writes plot files only inside the client's "
            "workspace roots or an output directory given here."
        ),
    )
    parser.add_argument(
        "--output-dir",
        action="append",
        default=[],
        metavar="DIR",
        help=(
            "Existing directory in which plot_signals may write plot files (repeatable). "
            f"Also read from ${OUTPUT_DIR_ENV} (several separated by {os.pathsep!r}). "
            "Needed for writing only when the client declares no workspace roots."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def parse_output_dirs(cli: Sequence[str], env: str | None) -> list[Path]:
    """Resolve and validate the configured output directories.

    ``cli`` are the ``--output-dir`` values, ``env`` the value of
    :data:`OUTPUT_DIR_ENV`. Relative paths are resolved against the current
    directory. Raises ``ValueError`` naming the first entry that is not an
    existing directory.
    """
    raw = [*cli, *([e for e in env.split(os.pathsep) if e.strip()] if env else [])]
    out: list[Path] = []
    for entry in raw:
        if not entry.strip():
            raise ValueError("output directory is empty")
        p = Path(entry).expanduser().resolve()
        if not p.is_dir():
            what = "is not a directory" if p.exists() else "does not exist"
            raise ValueError(
                f"output directory {entry!r} ({p}) {what}; create it first or fix the "
                f"--output-dir / {OUTPUT_DIR_ENV} setting"
            )
        if p not in out:
            out.append(p)
    return out


def main(argv: Sequence[str] | None = None) -> None:
    """Console-script entry point: parse options, then serve over stdio."""
    parser = _arg_parser()
    args = parser.parse_args(argv)
    try:
        dirs = parse_output_dirs(args.output_dir, os.environ.get(OUTPUT_DIR_ENV))
    except ValueError as exc:
        parser.error(str(exc))
    _output_dirs[:] = dirs
    mcp.run("stdio")


if __name__ == "__main__":
    main()
