"""The MCP server: tool registration, workspace roots and path resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse
from urllib.request import url2pathname

from mcp.server.mcpserver import Context, ListRoots, MCPServer, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ListRootsResult, TextContent, ToolAnnotations
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
    ToleranceSet,
    ToleranceSpec,
    XRange,
)
from simtest_funnel_mcp.render import render_compare, render_describe, time_digits
from simtest_funnel_mcp.snippet import make_snippet

SERVER_NAME = "simtest-funnel"

INSTRUCTIONS = """\
Funnel (tolerance-tube) comparison of signals stored in local CSV files
(comma-separated, header row, '#' comment lines, one shared time column).
The server reads the files itself; never paste sample values into a call.
Typical flow: describe_signals on the reference to see columns, time span,
sampling and value ranges; choose tolerances; compare_signals. Use absolute
paths. Read-only and stateless: pass the paths on every call."""

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


def _dump(model: DescribeResult | CompareResult) -> dict[str, object]:
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


def main() -> None:
    """Console-script entry point: serve over stdio."""
    mcp.run("stdio")


if __name__ == "__main__":
    main()
