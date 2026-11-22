"""Reproducible pytest snippet for a ``compare_signals`` result."""

from __future__ import annotations

import hashlib
import inspect
import math
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from simtest_funnel_mcp import reader
from simtest_funnel_mcp.compare import CompareOutcome
from simtest_funnel_mcp.models import COEFFICIENTS, FileInfo, SourceInfo
from simtest_funnel_mcp.timeaxis import format_iso

#: Hard cap on the snippet size (characters). Cases that do not fit are
#: replaced by a comment stating how many were left out.
MAX_SNIPPET_CHARS = 64_000

_HEADER = '''\
"""Funnel comparison reproduced from simtest-funnel-mcp {version}.

Requires: pip install "simtest-funnel>={funnel_version}" pandas pytest
Each case asserts the status the server observed. To use this as a CI gate,
set every expected status to funnel.Status.PASS.
"""

import functools
import os
from pathlib import Path

import pytest

import simtest.funnel as funnel

# Data files are resolved against SIMTEST_FUNNEL_DATA_ROOT, defaulting to the
# current working directory. Paths below are relative to {base!r}, the
# directory the server resolved them against; run pytest from there (or from
# the same place in a CI checkout), or set SIMTEST_FUNNEL_DATA_ROOT.
DATA_ROOT = Path(os.environ.get("SIMTEST_FUNNEL_DATA_ROOT", Path.cwd()))
{reference_line}
{test_line}
REFERENCE_HEADER_LINE = {reference_header_line!r}
TEST_HEADER_LINE = {test_header_line!r}
REFERENCE_TIME = {reference_time!r}
TEST_TIME = {test_time!r}
{x_range_comment}X_RANGE = funnel.Range(lo={lo}, hi={hi})

'''

_CASES_HEAD = '''
# (row key, reference column, test column, tolerance set, tolerances as given,
#  expected status)
CASES = [
'''

_FOOTER = '''\
]


@functools.lru_cache(maxsize=None)
def _columns(path: Path, header_line: int) -> dict:
    return read_signal_columns(str(path), header_line).values


@pytest.mark.parametrize(
    ("key", "reference_column", "test_column", "label", "tolerances", "expected"),
    CASES,
    ids=[f"{c[0]}-{c[3]}" for c in CASES],
)
def test_funnel(
    key: str,
    reference_column: str,
    test_column: str,
    label: str,
    tolerances: funnel.Tolerances,
    expected: int,
) -> None:
    ref = _columns(REFERENCE, REFERENCE_HEADER_LINE)
    tst = _columns(TEST, TEST_HEADER_LINE)
    result = funnel.compare(
        ref[REFERENCE_TIME],
        ref[reference_column],
        tst[TEST_TIME],
        tst[test_column],
        funnel.Options(tolerances=tolerances, x_range=X_RANGE),
    )
    assert result.status == expected, funnel.status_message(result.status)
'''


def _bound(value: float | None, unbounded: str) -> str:
    if value is None:
        return unbounded
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"x_range bound must be finite, got {v}")
    return repr(v)


def _path_line(name: str, path: Path, base: Path) -> str:
    try:
        rel = path.relative_to(base)
    except ValueError:
        return (
            f"# {name} lies outside {str(base)!r}; this absolute path will not "
            f"resolve on another machine.\n{name} = Path({str(path)!r})"
        )
    return f"{name} = DATA_ROOT / {rel.as_posix()!r}"


# --------------------------------------------------------------------------
# URL inputs (design.md §11): the snippet reads a verified local copy and
# never uses the network, unless the developer opts in with DOWNLOAD_ENV,
# which downloads a missing copy once. Kept together here so the policy can
# change in one place.
# --------------------------------------------------------------------------

#: Environment variable that lets a snippet download a missing local copy.
DOWNLOAD_ENV = "SIMTEST_FUNNEL_DOWNLOAD"

_URL_BLOCK = """\
# {name} was fetched by the server from
#   {url}
# on {fetched_at} ({size} bytes). The tests read a local copy, {local!r} under
# DATA_ROOT, and check its SHA-256; they never use the network unless
# {env}=1 is set, which downloads a missing copy once (then commit it).
{name} = DATA_ROOT / {local!r}
{name}_URL = {url!r}{download_comment}
{name}_DOWNLOAD_URL = {download_url!r}
{name}_SHA256 = {sha256!r}
{name}_SIZE = {size!r}"""

_URL_CHECK = '''

# Local copies of URL inputs: (path, URL, download URL, SHA-256, size).
DOWNLOAD_ENV = {env!r}
# Seconds a whole opt-in download may take.
DOWNLOAD_DEADLINE = 300
URL_INPUTS = [{inputs}]


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(path: Path, url: str, sha256: str, size: int) -> None:
    """Opt-in ({env}=1): download a missing copy from ``url`` (the address the
    server finally read) and keep it only when it is exactly the data the
    server compared. Redirects are not followed (checking where they lead is
    more than a few standard-library lines); the whole download must finish
    within DOWNLOAD_DEADLINE seconds; the body is asked for uncompressed, so
    the hash is of the bytes received; the copy is put in place with an
    exclusive hard link (or exclusive create), never replacing a file."""
    import hashlib
    import shutil
    import tempfile
    import time
    import urllib.request

    class NoRedirects(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
            raise AssertionError(
                f"{{url}} redirects to {{newurl}}; redirects are not followed. Download "
                f"the file yourself and save it as {{path}}"
            )

    if not url.startswith("https://"):
        raise AssertionError(f"not downloading {{url}}: only https URLs are downloaded")
    deadline = time.monotonic() + DOWNLOAD_DEADLINE
    opener = urllib.request.build_opener(NoRedirects)
    headers = {{"User-Agent": "simtest-funnel-snippet", "Accept-Encoding": "identity"}}
    request = urllib.request.Request(url, headers=headers)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".download-", suffix=".part")
    try:
        digest = hashlib.sha256()
        got = 0
        with os.fdopen(fd, "wb") as out, opener.open(request, timeout=30) as response:
            encoding = (response.headers.get("Content-Encoding") or "identity").strip().lower()
            if encoding != "identity":
                raise AssertionError(f"{{url}} sent Content-Encoding {{encoding}}; not saved")
            while block := response.read1(1 << 16):  # what has arrived, so the deadline is checked
                if time.monotonic() > deadline:
                    raise AssertionError(
                        f"downloading {{url}} took over {{DOWNLOAD_DEADLINE}} s; not saved"
                    )
                got += len(block)
                if got > size:
                    raise AssertionError(
                        f"the data behind {{url}} differs from what was compared: it is "
                        f"larger than the {{size}} bytes compared; not saved"
                    )
                digest.update(block)
                out.write(block)
        if digest.hexdigest() != sha256:
            raise AssertionError(
                f"the data behind {{url}} differs from what was compared (sha256 "
                f"{{sha256}} expected, {{digest.hexdigest()}} downloaded); not saved"
            )
        appeared = f"{{path}} appeared during the download; not replaced"
        try:
            os.link(tmp, path)  # fails if path exists
        except FileExistsError:
            raise AssertionError(appeared) from None
        except OSError:  # no hard links on this file system: exclusive create
            try:
                with open(tmp, "rb") as src, open(path, "xb") as dst:
                    shutil.copyfileobj(src, dst)
            except FileExistsError:
                raise AssertionError(appeared) from None
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@functools.lru_cache(maxsize=None)
def _check_copies() -> None:
    for path, url, download_url, sha256, size in URL_INPUTS:
        if not path.is_file() and os.environ.get(DOWNLOAD_ENV) == "1":
            _download(path, download_url, sha256, size)
        if not path.is_file():
            pytest.fail(
                f"local copy of {{url}} is missing: expected {{path}} (sha256 {{sha256}}, "
                f"{{size}} bytes). Save that file there and commit it, or run the tests once "
                f"with {{DOWNLOAD_ENV}}=1 to download it.",
                pytrace=False,
            )
        actual = _sha256(path)
        if actual != sha256:
            pytest.fail(
                f"{{path}} is not the data compared from {{url}}: sha256 {{sha256}} "
                f"expected, {{actual}} found. The data behind the URL may have changed "
                "since the comparison; restore the original copy or compare again.",
                pytrace=False,
            )
'''


def url_local_name(url: str) -> str:
    """Local file name for a URL input: the URL's last path segment reduced
    to ``[A-Za-z0-9._-]`` (``.csv`` added without an extension), or
    ``url-<8 hex of the URL hash>.csv`` when nothing is left."""
    segment = PurePosixPath(urlsplit(url).path).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", segment).strip("._")
    if not name:
        return f"url-{hashlib.sha256(url.encode()).hexdigest()[:8]}.csv"
    return name if "." in name else name + ".csv"


def _with_suffix(name: str, sha256: str) -> str:
    stem, dot, ext = name.rpartition(".")
    return f"{stem}-{sha256[:8]}.{ext}" if dot else f"{name}-{sha256[:8]}"


def _local_names(ref: FileInfo, tst: FileInfo) -> dict[str, str]:
    """Local name per URL; different URLs never share a name."""
    sources = [f.source for f in (ref, tst) if f.source is not None]
    names = {src.url: url_local_name(src.url) for src in sources}
    if len(names) == 2 and len(set(names.values())) == 1:
        by_url = {src.url: src for src in sources}
        names = {u: _with_suffix(n, by_url[u].sha256) for u, n in names.items()}
    return names


def _url_block(name: str, src: SourceInfo, local: str) -> str:
    final = src.final_url or src.url
    note = "" if final == src.url else (
        "\n# The server was redirected; the opt-in download uses the final URL and "
        "follows no redirect."
    )
    return _URL_BLOCK.format(
        name=name, url=src.url, fetched_at=src.fetched_at, size=src.size,
        sha256=src.sha256, local=local, env=DOWNLOAD_ENV, download_url=final,
        download_comment=note,
    )


def _url_check(names: list[str]) -> str:
    inputs = ", ".join(f"({n}, {n}_URL, {n}_DOWNLOAD_URL, {n}_SHA256, {n}_SIZE)" for n in names)
    return _URL_CHECK.format(env=DOWNLOAD_ENV, inputs=inputs)


def _tolerance_args(given: dict[str, float]) -> str:
    parts = []
    for k in COEFFICIENTS:
        if k in given:
            v = float(given[k])
            if not math.isfinite(v):
                raise ValueError(f"tolerance {k} must be finite, got {v}")
            parts.append(f"{k}={v!r}")
    return ", ".join(parts)


def make_snippet(
    outcome: CompareOutcome, version: str, funnel_version: str, base: Path
) -> str:
    """Return a self-contained pytest module reproducing the returned rows.

    Only the rows returned in the result (``max_rows``) become cases; paths
    under ``base`` are written relative to it.
    """
    res = outcome.result
    lo, hi = outcome.x_range
    same_path = res.reference.path == res.test.path
    local = _local_names(res.reference, res.test)

    def input_line(name: str, info: FileInfo) -> str:
        if info.source is not None:
            return _url_block(name, info.source, local[info.source.url])
        return _path_line(name, Path(info.path), base)

    url_names = [
        n for n, f in (("REFERENCE", res.reference), ("TEST", res.test))
        if f.source is not None and not (n == "TEST" and same_path)
    ]
    comment = ""
    if outcome.datetime_axis and (lo is not None or hi is not None):
        iso = [format_iso(v, outcome.time_zone) or "unbounded" for v in (lo, hi)]
        comment = f"# x_range in seconds since 1970-01-01 UTC: lo = {iso[0]}, hi = {iso[1]}\n"
    out = _HEADER.format(
        version=version,
        funnel_version=funnel_version,
        base=str(base),
        reference_line=input_line("REFERENCE", res.reference),
        test_line="TEST = REFERENCE" if same_path else input_line("TEST", res.test),
        reference_header_line=res.reference.header_line or 1,
        test_header_line=res.test.header_line or 1,
        reference_time=res.reference.time_column,
        test_time=res.test.time_column,
        x_range_comment=comment,
        lo=_bound(lo, 'float("-inf")'),
        hi=_bound(hi, 'float("inf")'),
    )
    if url_names:
        out += _url_check(url_names) + "\n"
    out += inspect.getsource(reader) + _CASES_HEAD
    shown = outcome.records[: len(res.rows)]
    budget = MAX_SNIPPET_CHARS - len(out) - len(_FOOTER) - 400
    cases: list[str] = []
    skipped: list[str] = []
    dropped = 0
    for rec in shown:
        row = rec.row
        if not rec.from_library or row.status is None or row.status_name is None:
            line = f"    #   {row.column} [{row.tolerance_set}]: {row.problem}\n"
            target = skipped
        else:
            ref_col, test_col = rec.columns
            line = (
                f"    ({row.column!r}, {ref_col!r}, {test_col!r}, {row.tolerance_set!r}, "
                f"funnel.Tolerances({_tolerance_args(rec.given)}), "
                f"funnel.Status.{row.status_name}),\n"
            )
            target = cases
        if len(line) > budget:
            dropped += 1
            continue
        budget -= len(line)
        target.append(line)
    out += "".join(cases)
    if skipped:
        out += "    # Not reproduced (not decided by the library):\n" + "".join(skipped)
    if res.rows_omitted:
        out += (
            f"    # {res.rows_omitted} row(s) not returned by the server (max_rows) "
            "are not included.\n"
        )
    if res.totals.not_completed:
        out += (
            f"    # {res.totals.not_completed} comparison(s) not completed within the "
            "server's time limit are not included.\n"
        )
    if dropped:
        out += f"    # {dropped} row(s) left out to keep this snippet under the size cap.\n"
    footer = _FOOTER
    if url_names:
        footer = footer.replace(
            "    ref = _columns(REFERENCE,", "    _check_copies()\n    ref = _columns(REFERENCE,"
        )
    return out + footer
