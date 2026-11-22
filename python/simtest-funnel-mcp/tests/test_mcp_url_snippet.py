"""Pytest snippets for URL inputs: a verified local copy, no network by
default, and the opt-in download (SIMTEST_FUNNEL_DOWNLOAD=1)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import OPEN_METEO_REF, open_meteo_column, open_meteo_text, structured
from urlserver import Certs, TestServer, body, test_fetcher

from simtest_funnel_mcp.fetch import FetchConfig
from simtest_funnel_mcp.models import ColumnPair, ToleranceSet
from simtest_funnel_mcp.server import Network, compare_signals_impl
from simtest_funnel_mcp.snippet import DOWNLOAD_ENV, url_local_name
from simtest_funnel_mcp.urlcache import UrlCache

OM = open_meteo_text().encode()
PAIRS = [
    ColumnPair(reference=OPEN_METEO_REF, test=open_meteo_column(d), label=f"day{d}")
    for d in (1, 3)
]
TOL = [ToleranceSet(label="2C_3h", atoly=2, atolx=10800), ToleranceSet(label="tight", atoly=0.1)]

#: Loaded by pytest in the snippet's directory: any IPv4/IPv6 connection fails.
NO_SOCKETS = '''
import socket

def _blocked(*args, **kwargs):
    raise AssertionError("the snippet must not use the network")

socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked
socket.getaddrinfo = _blocked
'''


@pytest.fixture
def net(certs: Certs) -> Any:
    cfg = FetchConfig(allow_network=True)
    n = Network(cfg, UrlCache(test_fetcher(certs, cfg)))
    yield n
    assert n.cache is not None
    n.cache.cleanup()


def _snippet(reference: str, test: str | None, net: Network) -> tuple[str, dict[str, Any]]:
    result = compare_signals_impl(
        reference, test, [], pairs=PAIRS, header_line=4, tolerances=TOL,
        include_snippet=True, network=net,
    )
    d = structured(result)
    return d["snippet"], d


def _run(
    snippet: str, where: Path, data_root: Path, *, block: bool, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    where.mkdir(parents=True, exist_ok=True)
    (where / "test_reproduced.py").write_text(snippet)
    if block:
        (where / "conftest.py").write_text(NO_SOCKETS)
    full = {k: v for k, v in os.environ.items() if k != DOWNLOAD_ENV}
    full.update({"SIMTEST_FUNNEL_DATA_ROOT": str(data_root), **(env or {})})
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_reproduced.py"],
        capture_output=True, text=True, cwd=where, env=full, check=False,
    )


def test_url_local_name() -> None:
    assert url_local_name("https://previous-runs-api.open-meteo.com/v1/forecast?x=1") == (
        "forecast.csv"
    )
    assert url_local_name("https://e.org/data/run%201.csv") == "run_201.csv"
    assert url_local_name("https://e.org/").startswith("url-")
    assert url_local_name("https://e.org/a.tsv") == "a.tsv"


def test_snippet_with_the_vendored_copy_passes_without_network(
    https_server: TestServer, net: Network, tmp_path: Path
) -> None:
    https_server.routes.routes["/v1/forecast?a=1"] = body(OM, gzipped=True)
    url = https_server.url("/v1/forecast?a=1")
    snippet, d = _snippet(url, None, net)
    sha = hashlib.sha256(OM).hexdigest()
    assert f"REFERENCE_SHA256 = {sha!r}" in snippet
    assert f"REFERENCE_URL = {url!r}" in snippet
    assert "REFERENCE = DATA_ROOT / 'forecast.csv'" in snippet
    assert f"#   {url}\n" in snippet and d["reference"]["source"]["fetched_at"] in snippet
    assert "TEST = REFERENCE" in snippet
    assert "SIMTEST_FUNNEL_DOWNLOAD=1" in snippet
    data = tmp_path / "data"
    data.mkdir()
    (data / "forecast.csv").write_bytes(OM)
    proc = _run(snippet, tmp_path / "ci", data, block=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{d['totals']['rows']} passed" in proc.stdout


def test_snippet_fails_when_the_copy_is_missing(
    https_server: TestServer, net: Network, tmp_path: Path
) -> None:
    https_server.routes.routes["/v1/forecast"] = body(OM)
    url = https_server.url("/v1/forecast")
    snippet, _ = _snippet(url, None, net)
    data = tmp_path / "data"
    data.mkdir()
    proc = _run(snippet, tmp_path / "ci", data, block=True)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert f"local copy of {url} is missing" in out
    assert str(data / "forecast.csv") in out
    assert hashlib.sha256(OM).hexdigest() in out
    assert "SIMTEST_FUNNEL_DOWNLOAD=1" in out
    assert "must not use the network" not in out


def test_snippet_fails_when_the_copy_differs(
    https_server: TestServer, net: Network, tmp_path: Path
) -> None:
    https_server.routes.routes["/v1/forecast"] = body(OM)
    snippet, _ = _snippet(https_server.url("/v1/forecast"), None, net)
    data = tmp_path / "data"
    data.mkdir()
    changed = OM.replace(b",3.", b",4.", 1)
    (data / "forecast.csv").write_bytes(changed)
    proc = _run(snippet, tmp_path / "ci", data, block=True)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert hashlib.sha256(OM).hexdigest() in out
    assert hashlib.sha256(changed).hexdigest() in out
    assert "is not the data compared" in out


def test_colliding_names_get_distinct_suffixes(
    https_server: TestServer, net: Network, tmp_path: Path
) -> None:
    other = OM.replace(b",3.", b",3.", 1) + b"\n"
    https_server.routes.routes["/a/data.csv"] = body(OM)
    https_server.routes.routes["/b/data.csv"] = body(other)
    snippet, _ = _snippet(https_server.url("/a/data.csv"), https_server.url("/b/data.csv"), net)
    ref_name = f"data-{hashlib.sha256(OM).hexdigest()[:8]}.csv"
    tst_name = f"data-{hashlib.sha256(other).hexdigest()[:8]}.csv"
    assert f"REFERENCE = DATA_ROOT / {ref_name!r}" in snippet
    assert f"TEST = DATA_ROOT / {tst_name!r}" in snippet
    data = tmp_path / "data"
    data.mkdir()
    (data / ref_name).write_bytes(OM)
    (data / tst_name).write_bytes(other)
    proc = _run(snippet, tmp_path / "ci", data, block=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_local_reference_and_url_test(
    https_server: TestServer, net: Network, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "ref.csv").write_bytes(OM)
    https_server.routes.routes["/t.csv"] = body(OM)
    snippet, _ = _snippet(str(tmp_path / "ref.csv"), https_server.url("/t.csv"), net)
    assert "REFERENCE = DATA_ROOT / 'ref.csv'" in snippet
    assert "TEST = DATA_ROOT / 't.csv'" in snippet
    assert "URL_INPUTS = [(TEST, TEST_URL, TEST_SHA256, TEST_SIZE)]" in snippet
    (tmp_path / "t.csv").write_bytes(OM)
    proc = _run(snippet, tmp_path / "ci", tmp_path, block=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# Opt-in download (owner decision): SIMTEST_FUNNEL_DOWNLOAD=1
# --------------------------------------------------------------------------


def _download_env(certs: Certs) -> dict[str, str]:
    return {
        DOWNLOAD_ENV: "1",
        "SSL_CERT_FILE": str(certs.ca),  # urllib's default context trusts the test CA
        "NO_PROXY": "*", "no_proxy": "*",
        "HTTPS_PROXY": "", "https_proxy": "", "ALL_PROXY": "", "all_proxy": "",
    }


def test_opt_in_downloads_a_missing_copy(
    https_server: TestServer, net: Network, certs: Certs, tmp_path: Path
) -> None:
    https_server.routes.routes["/v1/forecast"] = body(OM)
    url = https_server.url("/v1/forecast", host="localhost")
    snippet, d = _snippet(url, None, net)
    data = tmp_path / "data"
    data.mkdir()
    https_server.routes.seen.clear()
    proc = _run(snippet, tmp_path / "dev", data, block=False, env=_download_env(certs))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (data / "forecast.csv").read_bytes() == OM
    assert https_server.routes.count("/v1/forecast") == 1
    assert sorted(p.name for p in data.iterdir()) == ["forecast.csv"]
    # The copy now exists: no further request, also with the variable set.
    proc = _run(snippet, tmp_path / "dev", data, block=False, env=_download_env(certs))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert https_server.routes.count("/v1/forecast") == 1
    assert f"{d['totals']['rows']} passed" in proc.stdout


def test_opt_in_with_changed_upstream_content_fails_and_saves_nothing(
    https_server: TestServer, net: Network, certs: Certs, tmp_path: Path
) -> None:
    https_server.routes.routes["/v1/forecast"] = body(OM)
    url = https_server.url("/v1/forecast", host="localhost")
    snippet, _ = _snippet(url, None, net)
    changed = OM.replace(b",3.", b",4.", 1)
    https_server.routes.routes["/v1/forecast"] = body(changed)
    data = tmp_path / "data"
    data.mkdir()
    proc = _run(snippet, tmp_path / "dev", data, block=False, env=_download_env(certs))
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert f"the data behind {url} differs from what was compared" in out
    assert hashlib.sha256(OM).hexdigest() in out and hashlib.sha256(changed).hexdigest() in out
    assert list(data.iterdir()) == []  # no wrong file, no leftover part file
    # Larger than the recorded size: stopped at the size, nothing saved.
    https_server.routes.routes["/v1/forecast"] = body(OM + b"x" * 100)
    proc = _run(snippet, tmp_path / "dev", data, block=False, env=_download_env(certs))
    assert proc.returncode == 1 and "larger than the" in proc.stdout + proc.stderr
    assert list(data.iterdir()) == []


def test_opt_in_never_replaces_an_existing_copy(
    https_server: TestServer, net: Network, certs: Certs, tmp_path: Path
) -> None:
    https_server.routes.routes["/v1/forecast"] = body(OM)
    url = https_server.url("/v1/forecast", host="localhost")
    snippet, _ = _snippet(url, None, net)
    data = tmp_path / "data"
    data.mkdir()
    (data / "forecast.csv").write_bytes(b"time,x\n0,1\n")
    https_server.routes.seen.clear()
    proc = _run(snippet, tmp_path / "dev", data, block=False, env=_download_env(certs))
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1 and "is not the data compared" in out
    assert https_server.routes.seen == []  # no request made
    assert (data / "forecast.csv").read_bytes() == b"time,x\n0,1\n"
