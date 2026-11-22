"""The MCP server: tool registration, workspace roots and path resolution."""

from __future__ import annotations

import argparse
import base64
import contextlib
import errno
import io
import os
import secrets
import stat
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated, Literal, TypeVar
from urllib.parse import urlparse
from urllib.request import url2pathname

import anyio
import anyio.to_thread
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
    DEFAULT_TIME_LIMIT,
    CompareArgumentError,
    TimeLimit,
    run_compare,
)
from simtest_funnel_mcp.csvio import SignalFile, SignalFileError, load_csv
from simtest_funnel_mcp.describe import DEFAULT_MAX_COLUMNS, describe
from simtest_funnel_mcp.models import (
    ColumnPair,
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
from simtest_funnel_mcp.timeaxis import format_iso

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]

SERVER_NAME = "simtest-funnel"

INSTRUCTIONS = """\
Funnel (tolerance-tube) comparison of signals stored in local CSV files
(comma-separated, header row, '#' comment lines, one shared time column,
numeric or ISO 8601 date-times). The server reads the files itself; never
paste sample values into a call. If a file starts with a preamble (metadata
lines before the real header, as in Open-Meteo CSV), pass header_line; errors
and describe_signals problems suggest the likely value. Reference and test
may be differently named columns of one file: compare_signals 'pairs' (no
test_path needed), plot_signals 'test_column'. On a date-time time axis,
times and x tolerances are seconds ("3 hours" = atolx 10800).
Typical flow: describe_signals on the reference to see columns, time span,
sampling and value ranges; choose tolerances (there is no time tolerance
unless you give one, e.g. atolx); compare_signals; plot_signals to look at
one column (inline PNG preview) and optionally save the plot as an SVG or
PNG file for a document. Use absolute paths. Stateless: pass the
paths on every call. Only plot_signals writes, and only the output_path
it is given (never an existing file unless overwrite=true), which must lie
inside a workspace root declared by the client or an output directory
configured when the server was started; with neither, omit output_path
and use the inline preview. compare_signals and plot_signals stop
time_limit seconds (default 60) after the call started, reading the files
included: compare_signals then returns the finished rows and lists the
comparisons not completed; plot_signals fails and writes nothing. Raise
time_limit for very long signals."""

CSV_HELP = (
    "CSV dialect: comma-separated, one header row, lines whose first non-blank character "
    "is '#' ignored ('#' elsewhere is data); a data row with more fields than the header "
    "is an error. "
    "HEADER LINE: header_line (1-based physical file line, default 1) skips the lines "
    "before it unread; the header is the first non-blank, non-comment line at or after "
    "it. It is never detected automatically, but when a read fails or looks wrong and the "
    "file seems to start with a preamble (a blank line, then a line that looks like a "
    "header row), the error or a problem says so and suggests the header_line to pass. "
    "Time column: the first column named 'time' (case-insensitive), otherwise the first "
    "column; the choice is echoed back. It may be numeric or ISO 8601 date-times "
    "(YYYY-MM-DD, optionally T or space and hh:mm, optional seconds and fraction, optional "
    "Z or offset such as +01:00; detected when every non-empty cell is one). DATE-TIME "
    "AXIS: times become seconds since 1970-01-01 UTC, so x tolerances and numeric x_range "
    "bounds are in seconds; a timestamp without offset is read as UTC (describe_signals "
    "flags it as having no time zone); reference and test must both be numeric, both "
    "without time zone or both with offsets. Results echo times as numbers and as ISO "
    "8601 strings (*_iso fields)."
)

DESCRIBE_DESCRIPTION = f"""\
Describe a local CSV signal file without returning sample values: header line used,
time column and its kind (numeric or datetime, with time zone or not), row count, time
start/end/span (on a date-time axis also as ISO 8601 strings and durations), sampling
(uniform or not; min/median/max step), and for
every signal column its min, max and range, plus data problems (non-numeric or
empty cells, time column not non-decreasing, no time zone, preamble hints with the
header_line to pass). Use it to pick columns and sensible
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
each axis, if none of its three coefficients is given that axis gets its default -
x: all 0 (NO time tolerance); y: rtoly = 0.002 (0.2 % of the value range). If any
coefficient of an axis is given, that axis's other coefficients are 0. An explicit 0
counts as given.

TOLERANCE IN X: there is none unless you give one. With x tolerance 0 the tube has
no width in time (half_x is the 1e-10 floor): each test point is checked only
against the y band around the reference at the same time, so a test curve that is
shifted or delayed even slightly fails at steep edges (steps, switching events).
Give an x tolerance when such shifts are acceptable: a test curve shifted by up to
half_x then still passes. Prefer atolx (time units); rtolx is a fraction of the
whole time span, so it grows with the length of the record (rtolx = 0.002 allows
43 min on 15 days of data). A failed row with no x coefficient given gets a note
suggesting an x tolerance.

Example "1 % in y, 0.5 s in x": {{"rtoly": 0.01, "atolx": 0.5}} (1 % of the reference
value range). For 1 % of the local value use "ltoly": 0.01; to allow both use
"rtoly"/"ltoly" together (the max applies). Example "within 0.05 units, no time
tolerance": {{"atoly": 0.05, "atolx": 0}}.

DATE-TIME AXIS (ISO 8601 time column): x is seconds since 1970-01-01 UTC, so x
tolerances are seconds. Example "within 2 °C and 3 hours": {{"atoly": 2, "atolx":
10800}} (atoly in the column's unit, atolx = 3 * 3600 s). A non-zero ltolx is refused
there (it would scale with ~1.8e9 s); rtolx is allowed. Every tolerance set (and row
with an x override) echoes its non-zero time half-width as time_tolerance {{seconds,
duration}}, e.g. {{"seconds": 10800, "duration": "PT3H"}}. x_range bounds may be ISO
8601 strings, e.g. {{"lo": "2026-11-05T00:00", "hi": "2026-11-10T00:00"}}, with 'Z' or
an offset exactly when the time columns have one.

COLUMNS AND PAIRS: by default every signal column present in both files is compared
with the same-named column. 'columns' accepts exact names and glob patterns ('*',
'?', '[...]'). 'pairs' instead compares a reference column with a differently named
test column: [{{"reference": "temperature_2m (°C)", "test":
"temperature_2m_previous_day1 (°C)", "label": "day1"}}, ...] (exact names only, units
in names are part of the name; one reference column may appear in several pairs).
pairs and columns cannot be combined. A pair's row key ('column' in each row, also the
key for column_tolerances) is its label, else its test column; keys must be unique.
Pair rows also carry reference_column and test_column. test_path is optional with
pairs: omitted, both columns come from the reference file (one file is read once);
without pairs a test_path is required. test_header_line (default: header_line) is the
header line of the test file.

Pass several labelled sets in 'tolerances' to try e.g. strict and loose in one
call. 'column_tolerances' overrides the sets per column, axis by axis: an axis for
which the override gives any coefficient is taken entirely from the override.
Columns missing from a file or with bad data are reported per row (verdict
'error'), not as a failed call. Set include_snippet=true to get a pytest file that
reproduces the returned rows in CI; it is returned in the structured content field
'snippet' only. Its data paths are relative to the first workspace root (else the
server's working directory) and resolved against $SIMTEST_FUNNEL_DATA_ROOT or the
current directory, so commit the CSV files at the same relative location.

TIME LIMIT: time_limit (seconds, default {DEFAULT_TIME_LIMIT:g}) is a deadline for the whole
call, counted from its start, so the time spent reading the files counts against it.
Comparisons are started only while time remains and a running comparison is stopped
at the deadline; reading itself is not interrupted, so a call can overrun the limit by
the time spent reading. When the limit is reached the call still succeeds: rows are
returned for the comparisons that finished, the others are listed in 'not_completed'
(totals.not_completed counts them, time_limit_reached is true) and a note suggests a
larger time_limit, fewer columns or a narrower x_range. Comparisons usually take well
under a second even for a million samples; a nearly noise-free signal with a large
time tolerance can take much longer. Cancelling the call stops the running
comparison."""

HEADER_LINE_HELP = (
    "1-based physical line where the header search starts (lines before it are skipped "
    "unread; the header is the first non-blank, non-comment line at or after it). "
    "Default 1 = first non-comment line. E.g. 4 for Open-Meteo CSV (3 preamble lines)."
)
TEST_HEADER_LINE_HELP = "header_line of the test file (default: header_line)."

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

PLOT_DESCRIPTION = f"""\
Plot ONE funnel comparison - one signal column (or one reference column against a
differently named test_column), one tolerance set - and return a
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
test_path is optional (default: the reference file; then give test_column), and
test_column (default: column) plots column of the reference against test_column of the
test like the corresponding compare_signals pair; legend and title then name both. On
a date-time time axis the x ticks are dates and times, the x label says "(UTC)" or "(no
time zone)", the subtitle shows the time tolerance as a duration (x ±PT3H), x_range
accepts ISO 8601 strings and the result echoes the view also as ISO 8601 strings.

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
all problems. Tolerance coefficients: see compare_signals.

time_limit (seconds, default {DEFAULT_TIME_LIMIT:g}) is a deadline for the whole call,
counted from its start: reading the files, the comparison and rendering. The comparison
is stopped at the deadline; reading and rendering are not interrupted, but the deadline
is checked before rendering and again immediately before the file is written. When the
limit is reached, or the call is cancelled, the call fails and nothing is written: the
file is written under a temporary name and moved into place only while the call is
still live, so no partial or late file appears. {CSV_HELP}"""

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


#: Whether the platform can write relative to a directory file descriptor
#: without following symbolic links (Linux, macOS and other POSIX systems;
#: not Windows). See :func:`_publish_plot`.
_DIR_FD_WRITES = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and {os.open, os.stat, os.unlink, os.rename, os.link} <= os.supports_dir_fd
)

#: ``errno`` values with which ``link`` fails on file systems without hard
#: links; :func:`_publish_plot` then creates the file exclusively instead.
_NO_HARD_LINKS = frozenset(
    e
    for e in (
        getattr(errno, "EPERM", None),
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "EMLINK", None),
    )
    if e is not None
)


class PublishGate:
    """Orders the cancellation of a call against the publishing of its file.

    :func:`run_off_loop` cancels the call's token while holding the gate,
    and :func:`_publish_plot` checks the token and moves the finished file
    into place while holding it. So the file either appears before the
    call is reported cancelled or never; the gate is held only for the few
    system calls of the final check and move.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> None:
        self._lock.acquire()

    def __exit__(self, *exc: object) -> None:
        self._lock.release()


def _check_live(limit: TimeLimit, when: str) -> None:
    """Raise a :class:`ToolError` if the call was cancelled or its time
    limit has passed (``when`` says at which step)."""
    if limit.cancel.cancelled:
        raise ToolError(f"plot_signals was cancelled {when}; no file was written")
    if limit.remaining() <= 0.0:
        raise ToolError(
            f"plot_signals reached its time limit of {limit.describe()} {when}; no file "
            "was written. The limit counts from the start of the call and covers reading "
            "the files, the comparison and rendering. Pass a larger time_limit or a "
            "narrower x_range."
        )


def _outside(target: Path, allowed: Sequence[Path]) -> ToolError:
    return ToolError(
        f"{target} is outside the workspace roots and configured output directories "
        f"({', '.join(map(str, allowed))}); not written"
    )


def _fd_dir_path(dir_fd: int, hint: Path) -> Path:
    """The current location of the directory open as ``dir_fd``.

    Asks the kernel where available (``F_GETPATH`` on macOS,
    ``/proc/self/fd`` on Linux), else resolves ``hint``. The caller checks
    that the result really is that directory (same device and inode).
    """
    get_path = getattr(fcntl, "F_GETPATH", None) if fcntl is not None else None
    if fcntl is not None and get_path is not None:
        raw = fcntl.fcntl(dir_fd, get_path, b"\0" * 1024)  # MAXPATHLEN
        return Path(os.fsdecode(raw.split(b"\0", 1)[0]))
    proc = Path(f"/proc/self/fd/{dir_fd}")
    if proc.is_symlink():
        return Path(os.readlink(proc))
    return Path(os.path.realpath(hint))


def _verified_dir(dir_fd: int, hint: Path, allowed: Sequence[Path]) -> Path:
    """Where the directory ``dir_fd`` is now, verified to be inside
    ``allowed``; raises :class:`ToolError` otherwise."""
    where = _fd_dir_path(dir_fd, hint)
    if not any(where.is_relative_to(os.path.realpath(r)) for r in allowed):
        raise _outside(where, allowed)
    try:
        st = os.stat(where, follow_symlinks=False)
    except OSError as exc:
        raise ToolError(f"cannot write into {hint}: {exc}") from exc
    fst = os.fstat(dir_fd)
    if (st.st_dev, st.st_ino) != (fst.st_dev, fst.st_ino):
        raise ToolError(f"directory {hint} was moved or replaced during the call; not written")
    return where


def _publish_plot(
    target: Path,
    data: bytes,
    overwrite: bool,
    allowed: Sequence[Path],
    limit: TimeLimit,
    gate: PublishGate,
) -> Path:
    """Write ``data`` to ``target`` (checked by :func:`resolve_output_path`)
    and return where the file now is.

    The data first goes to a temporary file in the target directory, which
    is moved into place only if the call is still live (not cancelled,
    time limit not reached), so no partial file and no file of a cancelled
    call ever appears under the target name: with ``overwrite`` by an
    atomic rename, otherwise by a hard link that fails if the name exists
    (or, on file systems without hard links, by an exclusive create).

    ``target`` was checked before the files were read and compared, which
    can take a minute; meanwhile a directory on the path could be replaced
    by a symbolic link pointing elsewhere. So, where the platform allows,
    everything happens relative to a file descriptor of the target
    directory, opened without following a final symbolic link and verified
    to lie inside ``allowed`` immediately before the file is moved into
    place; the temporary file is created with ``O_EXCL | O_NOFOLLOW`` and
    a symbolic link at the target name is replaced, never followed.
    """
    if not _DIR_FD_WRITES:
        return _publish_plot_by_path(target, data, overwrite, allowed, limit, gate)
    parent, name = target.parent, target.name
    cloexec = getattr(os, "O_CLOEXEC", 0)
    try:
        dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | cloexec)
    except OSError as exc:
        raise ToolError(f"cannot write {target}: directory {parent}: {exc}") from exc
    tmp = f".{name}.{secrets.token_hex(8)}.tmp"
    try:
        _verified_dir(dir_fd, parent, allowed)
        try:
            fd = os.open(
                tmp,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | cloexec,
                0o666,
                dir_fd=dir_fd,
            )
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            with gate:
                _check_live(limit, "before the file was written")
                where = _verified_dir(dir_fd, parent, allowed)
                if overwrite:
                    try:
                        st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
                    except FileNotFoundError:
                        pass
                    else:
                        if stat.S_ISDIR(st.st_mode):
                            raise ToolError(
                                f"{where / name} exists and is not a regular file; not written"
                            )
                    os.replace(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
                else:
                    try:
                        os.link(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
                    except FileExistsError:
                        raise
                    except OSError as exc:
                        if exc.errno not in _NO_HARD_LINKS:
                            raise
                        fd = os.open(
                            name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | cloexec,
                            0o666,
                            dir_fd=dir_fd,
                        )
                        try:
                            with os.fdopen(fd, "wb") as fh:
                                fh.write(data)
                        except BaseException:
                            os.unlink(name, dir_fd=dir_fd)
                            raise
            return where / name
        except FileExistsError as exc:
            raise ToolError(
                f"{parent / name} already exists; pass overwrite=true to replace it"
            ) from exc
        except OSError as exc:
            raise ToolError(f"cannot write {target}: {exc}") from exc
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _publish_plot_by_path(
    target: Path,
    data: bytes,
    overwrite: bool,
    allowed: Sequence[Path],
    limit: TimeLimit,
    gate: PublishGate,
) -> Path:
    """:func:`_publish_plot` for platforms without ``dir_fd`` writes
    (Windows).

    Not free of races: the target directory is resolved again and checked
    against ``allowed`` immediately before the file is moved into place,
    which narrows the window between check and use to a few system calls
    but cannot close it. Temporary file, liveness check and move into
    place work as in :func:`_publish_plot`.
    """
    tmp: Path | None = None
    try:
        parent = target.parent.resolve(strict=True)
        if not any(parent.is_relative_to(r) for r in allowed):
            raise _outside(parent, allowed)
        tmp = parent / f".{target.name}.{secrets.token_hex(8)}.tmp"
        with open(tmp, "xb") as fh:
            fh.write(data)
        with gate:
            _check_live(limit, "before the file was written")
            parent = target.parent.resolve(strict=True)
            if not any(parent.is_relative_to(r) for r in allowed):
                raise _outside(parent, allowed)
            where = parent / target.name
            if overwrite:
                if where.is_dir():
                    raise ToolError(f"{where} exists and is not a regular file; not written")
                os.replace(tmp, where)
            else:
                try:
                    os.link(tmp, where)
                except FileExistsError:
                    raise
                except OSError:
                    with open(where, "xb") as fh:
                        fh.write(data)
        return where
    except FileExistsError as exc:
        raise ToolError(f"{target} already exists; pass overwrite=true to replace it") from exc
    except OSError as exc:
        raise ToolError(f"cannot write {target}: {exc}") from exc
    finally:
        if tmp is not None:
            with contextlib.suppress(FileNotFoundError):
                tmp.unlink()


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


def _load(
    raw: str, roots: list[Path], header_line: int = 1, arg: str = "header_line"
) -> SignalFile:
    try:
        return load_csv(resolve_path(raw, roots), header_line, arg=arg)
    except SignalFileError as exc:
        raise ToolError(str(exc)) from exc


#: Refusal when neither a test path nor pairs are given.
NO_TEST_PATH = (
    "test_path is missing: without pairs, the reference file would be compared with "
    "itself and every column would pass trivially. Pass test_path, or pairs to compare "
    "differently named columns within the reference file"
)


def _load_pair(
    reference_path: str,
    test_path: str | None,
    roots: list[Path],
    header_line: int,
    test_header_line: int | None,
) -> tuple[SignalFile, SignalFile]:
    """Load reference and test; the test file defaults to the reference file
    and one file (same path and header line) is read only once."""
    ref = _load(reference_path, roots, header_line)
    t_line = header_line if test_header_line is None else test_header_line
    if test_path is None:
        tst_path = ref.path
    else:
        tst_path = resolve_path(test_path, roots)
    if tst_path == ref.path and t_line == header_line:
        return ref, ref
    try:
        return ref, load_csv(tst_path, t_line, arg="test_header_line")
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


def _start_limit(time_limit: float, cancel: funnel.CancelToken | None) -> TimeLimit:
    try:
        return TimeLimit.start(time_limit, cancel)
    except CompareArgumentError as exc:
        raise ToolError(str(exc)) from exc


_T = TypeVar("_T")


async def run_off_loop(
    work: Callable[[funnel.CancelToken], _T], gate: PublishGate | None = None
) -> _T:
    """Run ``work(token)`` in a worker thread, off the event loop.

    The comparison releases the GIL, so the server keeps reading and
    answering messages meanwhile. When the call is cancelled (the client's
    ``notifications/cancelled`` cancels the handler), the token is cancelled
    so the running comparison stops at its next checkpoint, and the
    cancellation propagates at once (the worker's late result is dropped).
    With a ``gate`` the token is cancelled while holding it, so a worker
    that publishes a file under the same gate (:func:`_publish_plot`)
    either has published it already or sees the cancellation and never
    does.
    """
    token = funnel.CancelToken()
    try:
        return await anyio.to_thread.run_sync(lambda: work(token), abandon_on_cancel=True)
    except anyio.get_cancelled_exc_class():
        if gate is None:
            token.cancel()
        else:
            with gate:
                token.cancel()
        raise


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
    header_line: int = 1,
) -> CallToolResult:
    """Describe one file; see :data:`DESCRIBE_DESCRIPTION`."""
    sf = _load(path, roots, header_line)
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
    test_path: str | None,
    roots: list[Path],
    *,
    columns: list[str] | None = None,
    pairs: list[ColumnPair] | None = None,
    header_line: int = 1,
    test_header_line: int | None = None,
    tolerances: list[ToleranceSet] | None = None,
    column_tolerances: dict[str, ToleranceSpec] | None = None,
    x_range: XRange | None = None,
    max_intervals: int = DEFAULT_MAX_INTERVALS,
    max_rows: int = DEFAULT_MAX_ROWS,
    include_snippet: bool = False,
    root_notes: list[str] | None = None,
    time_limit: float = DEFAULT_TIME_LIMIT,
    cancel: funnel.CancelToken | None = None,
) -> CallToolResult:
    """Compare two files; see :data:`COMPARE_DESCRIPTION`.

    ``time_limit`` counts from the start of the call; ``cancel`` (the
    call's token) stops the running comparison with
    ``funnel.ComparisonCancelled``.
    """
    limit = _start_limit(time_limit, cancel)
    if test_path is None and pairs is None:
        raise ToolError(NO_TEST_PATH)
    ref, tst = _load_pair(reference_path, test_path, roots, header_line, test_header_line)
    try:
        outcome = run_compare(
            ref,
            tst,
            columns=columns,
            pairs=pairs,
            tolerances=tolerances,
            column_tolerances=column_tolerances,
            x_range=x_range,
            max_intervals=max_intervals,
            max_rows=max_rows,
            limit=limit,
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
    test_path: str | None,
    roots: list[Path],
    *,
    column: str,
    test_column: str | None = None,
    header_line: int = 1,
    test_header_line: int | None = None,
    tolerance: ToleranceSet | None = None,
    x_range: XRange | None = None,
    output_path: str | None = None,
    overwrite: bool = False,
    max_intervals: int = DEFAULT_MAX_INTERVALS,
    root_notes: list[str] | None = None,
    output_dirs: Sequence[Path] = (),
    time_limit: float = DEFAULT_TIME_LIMIT,
    cancel: funnel.CancelToken | None = None,
    gate: PublishGate | None = None,
) -> CallToolResult:
    """Plot one comparison; see :data:`PLOT_DESCRIPTION`.

    ``output_dirs`` are the configured output directories (the tool passes
    :func:`configured_output_dirs`). ``time_limit`` / ``cancel`` as in
    :func:`compare_signals_impl`, except that the limit also covers
    rendering: it and the token are checked before rendering and
    immediately before the file is moved into place, and a call that is
    no longer live fails without writing. ``gate`` is the one given to
    :func:`run_off_loop` for the call (a private one when omitted).
    """
    limit = _start_limit(time_limit, cancel)
    if max_intervals < 0:
        raise ToolError("max_intervals must be >= 0")
    # Check the output path before any work, write only after rendering.
    target = (
        resolve_output_path(output_path, roots, overwrite, output_dirs)
        if output_path is not None
        else None
    )
    ref, tst = _load_pair(reference_path, test_path, roots, header_line, test_header_line)
    try:
        outcome = prepare_plot(
            ref, tst, column=column, tolerance=tolerance, x_range=x_range,
            max_intervals=max_intervals, limit=limit, test_column=test_column,
        )
    except (PlotArgumentError, CompareArgumentError) as exc:
        raise ToolError(str(exc)) from exc
    data = outcome.data
    _check_live(limit, "before rendering")
    preview = _preview_png(data)
    pw, ph = png_size(preview)
    file_out: PlotFile | None = None
    if target is not None:
        path, fmt = target
        _check_live(limit, "before rendering the file")
        blob = render(data, fmt) if fmt == "svg" else render(data, fmt, PNG_FILE_DPI)
        written = _publish_plot(
            path,
            blob,
            overwrite,
            [*roots, *output_dirs],
            limit,
            gate if gate is not None else PublishGate(),
        )
        size = png_size(blob) if fmt == "png" else None
        file_out = PlotFile(
            path=str(written),
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
        view=RangeOut(
            lo=data.view[0],
            hi=data.view[1],
            lo_iso=format_iso(data.view[0], ref.time_zone) if data.date_axis else None,
            hi_iso=format_iso(data.view[1], ref.time_zone) if data.date_axis else None,
        ),
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
    header_line: Annotated[int, Field(ge=1, description=HEADER_LINE_HELP)] = 1,
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
        path, paths, columns=columns, max_columns=max_columns, root_notes=ignored,
        header_line=header_line,
    )


@mcp.tool(
    name="compare_signals",
    title="Compare CSV signals (funnel)",
    description=COMPARE_DESCRIPTION,
    annotations=READ_ONLY,
)
async def compare_signals(
    reference_path: Annotated[str, Field(description="Path of the reference CSV file.")],
    roots: Roots,
    test_path: Annotated[
        str | None,
        Field(
            description=(
                "Path of the test CSV file. Optional with pairs (default: the reference "
                "file); required otherwise."
            )
        ),
    ] = None,
    pairs: Annotated[
        list[ColumnPair] | None,
        Field(
            description=(
                "Reference/test column pairs [{reference, test, label?}] of exact names; "
                "the row key is the label, else the test column. Not with columns."
            )
        ),
    ] = None,
    header_line: Annotated[int, Field(ge=1, description=HEADER_LINE_HELP)] = 1,
    test_header_line: Annotated[
        int | None, Field(ge=1, description=TEST_HEADER_LINE_HELP)
    ] = None,
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
                "ltolx, ltoly, rtolx, rtoly. Omit for one set with the library default "
                "(rtoly = 0.002, no time tolerance)."
            )
        ),
    ] = None,
    column_tolerances: Annotated[
        dict[str, ToleranceSpec] | None,
        Field(
            description=(
                "Per-column overrides (row key -> coefficients), applied per axis; the key "
                "is the column name, or for pairs the label (else the test column)."
            )
        ),
    ] = None,
    x_range: Annotated[
        XRange | None,
        Field(
            description=(
                "Time window {lo, hi} to compare; bounds must be finite numbers (seconds since "
                "1970 on a date-time axis) or, on a date-time axis, ISO 8601 strings; omit a "
                "bound for unbounded."
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
    time_limit: Annotated[
        float,
        Field(
            gt=0,
            allow_inf_nan=False,
            description=(
                "Deadline in seconds for the whole call, counted from its start and "
                "including reading the files (default 60). When reached, finished rows "
                "are returned and the rest listed in 'not_completed'."
            ),
        ),
    ] = DEFAULT_TIME_LIMIT,
) -> Annotated[CallToolResult, CompareResult]:
    ignored: list[str] = []
    paths = root_paths(roots, ignored)
    return await run_off_loop(
        lambda token: compare_signals_impl(
            reference_path,
            test_path,
            paths,
            columns=columns,
            pairs=pairs,
            header_line=header_line,
            test_header_line=test_header_line,
            tolerances=tolerances,
            column_tolerances=column_tolerances,
            x_range=x_range,
            max_intervals=max_intervals,
            max_rows=max_rows,
            include_snippet=include_snippet,
            root_notes=ignored,
            time_limit=time_limit,
            cancel=token,
        )
    )


@mcp.tool(
    name="plot_signals",
    title="Plot one CSV signal comparison (funnel)",
    description=PLOT_DESCRIPTION,
    annotations=PLOT,
)
async def plot_signals(
    reference_path: Annotated[str, Field(description="Path of the reference CSV file.")],
    column: Annotated[
        str,
        Field(
            min_length=1,
            description="The one signal column to plot (exact name; the reference column).",
        ),
    ],
    roots: Roots,
    test_path: Annotated[
        str | None,
        Field(description="Path of the test CSV file (default: the reference file)."),
    ] = None,
    test_column: Annotated[
        str | None,
        Field(
            min_length=1,
            description="Test column to plot against column (exact name; default: column).",
        ),
    ] = None,
    header_line: Annotated[int, Field(ge=1, description=HEADER_LINE_HELP)] = 1,
    test_header_line: Annotated[
        int | None, Field(ge=1, description=TEST_HEADER_LINE_HELP)
    ] = None,
    tolerance: Annotated[
        ToleranceSet | None,
        Field(
            description=(
                "One tolerance set: optional 'label' and any of atolx, atoly, ltolx, ltoly, "
                "rtolx, rtoly (same as one entry of compare_signals 'tolerances'). Omit for "
                "the library default (rtoly = 0.002, no time tolerance)."
            )
        ),
    ] = None,
    x_range: Annotated[
        XRange | None,
        Field(
            description=(
                "Time window {lo, hi} to compare and show; bounds must be finite numbers or, "
                "on a date-time axis, ISO 8601 strings; omit a bound for unbounded."
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
    time_limit: Annotated[
        float,
        Field(
            gt=0,
            allow_inf_nan=False,
            description=(
                "Deadline in seconds for the whole call, counted from its start: reading "
                "the files, the comparison and rendering (default 60). When reached, the "
                "call fails and nothing is written."
            ),
        ),
    ] = DEFAULT_TIME_LIMIT,
) -> Annotated[CallToolResult, PlotResult]:
    ignored: list[str] = []
    paths = root_paths(roots, ignored)
    output_dirs = configured_output_dirs()
    gate = PublishGate()
    return await run_off_loop(
        lambda token: plot_signals_impl(
            reference_path,
            test_path,
            paths,
            column=column,
            test_column=test_column,
            header_line=header_line,
            test_header_line=test_header_line,
            tolerance=tolerance,
            x_range=x_range,
            output_path=output_path,
            overwrite=overwrite,
            max_intervals=max_intervals,
            root_notes=ignored,
            output_dirs=output_dirs,
            time_limit=time_limit,
            cancel=token,
            gate=gate,
        ),
        gate,
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
