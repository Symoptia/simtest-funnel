"""URL inputs through the tools (in-process client, local HTTPS server)."""

from __future__ import annotations

import asyncio
import json
import socket
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import anyio
import pytest
from conftest import OPEN_METEO_REF, open_meteo_column, open_meteo_text, structured
from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ListRootsResult, Root
from urlserver import Certs, TestServer, body, slow, test_fetcher

from simtest_funnel_mcp import server as server_module
from simtest_funnel_mcp.fetch import FetchConfig
from simtest_funnel_mcp.server import (
    Network,
    build_server,
    compare_signals_impl,
    describe_signals_impl,
    mcp,
)
from simtest_funnel_mcp.urlcache import UrlCache

CSV = b"time,a,b\n0,1,2\n1,2,3\n2,3,4\n"
PAIRS = [
    {"reference": OPEN_METEO_REF, "test": open_meteo_column(d), "label": f"day{d}"}
    for d in (1, 3)
]


def _network(certs: Certs, **config: Any) -> Network:
    cfg = FetchConfig(allow_network=True, **config)
    return Network(cfg, UrlCache(test_fetcher(certs, cfg)))


@pytest.fixture
def net(certs: Certs) -> Any:
    n = _network(certs)
    yield n
    assert n.cache is not None
    n.cache.cleanup()


def _call(
    srv: MCPServer, name: str, args: dict[str, Any], roots: tuple[Path, ...] | None = None
) -> Any:
    async def callback(context: object) -> ListRootsResult:
        assert roots is not None
        return ListRootsResult(roots=[Root(uri=r.resolve().as_uri()) for r in roots])  # type: ignore[arg-type]

    async def run() -> Any:
        kwargs: dict[str, Any] = {}
        if roots is not None:
            kwargs["list_roots_callback"] = callback
        async with Client(srv, **kwargs) as client:
            return await client.call_tool(name, args)

    return asyncio.run(run())


def _tools(srv: MCPServer) -> dict[str, Any]:
    async def run() -> Any:
        async with Client(srv) as client:
            return await client.list_tools()

    return {t.name: t for t in asyncio.run(run()).tools}


# --------------------------------------------------------------------------
# 4.2 Input loading
# --------------------------------------------------------------------------


def test_describe_a_url_equals_describing_the_local_file(
    https_server: TestServer, net: Network, tmp_path: Path
) -> None:
    https_server.routes.routes["/run.csv"] = body(CSV)
    local = tmp_path / "run.csv"
    local.write_bytes(CSV)
    srv = build_server(net)
    url = https_server.url("/run.csv")
    remote = _call(srv, "describe_signals", {"path": url})
    assert not remote.is_error, remote.content
    here = _call(srv, "describe_signals", {"path": str(local)})
    r, h = structured(remote), structured(here)
    source = r.pop("source")
    assert r.pop("path") == url and h.pop("path") == str(local.resolve())
    assert r == h
    assert source["url"] == url and source["size"] == len(CSV) and source["reused"] is False
    assert len(source["sha256"]) == 64 and source["fetched_at"].endswith("Z")
    assert "final_url" not in source
    text = remote.content[0].text
    assert text.startswith(f"{url}: 3 rows")
    assert f"fetched {source['fetched_at']}, {len(CSV)} bytes, sha256 {source['sha256'][:12]}…" in text


def test_open_meteo_shaped_url_with_pairs_is_fetched_once(
    https_server: TestServer, net: Network
) -> None:
    https_server.routes.routes["/v1/forecast?x=1"] = body(
        open_meteo_text().encode(), gzipped=True
    )
    url = https_server.url("/v1/forecast?x=1")
    srv = build_server(net)
    result = _call(srv, "compare_signals", {
        "reference_path": url, "header_line": 4, "pairs": PAIRS,
        "tolerances": [{"label": "2C_3h", "atoly": 2, "atolx": 10800}],
    })
    assert not result.is_error, result.content
    d = structured(result)
    assert {r["column"] for r in d["rows"]} == {"day1", "day3"}
    assert d["reference"]["path"] == d["test"]["path"] == url
    assert d["reference"]["source"] == d["test"]["source"]
    assert d["reference"]["time_kind"] == "datetime"
    assert https_server.routes.count("/v1/forecast?x=1") == 1
    # A later call reuses the copy: same hash and fetch time, no request.
    again = structured(_call(srv, "describe_signals", {"path": url, "header_line": 4}))
    assert again["source"]["reused"] is True
    assert again["source"]["sha256"] == d["reference"]["source"]["sha256"]
    assert again["source"]["fetched_at"] == d["reference"]["source"]["fetched_at"]
    assert https_server.routes.count("/v1/forecast?x=1") == 1


def test_local_reference_against_a_url_test(
    https_server: TestServer, net: Network, tmp_path: Path
) -> None:
    https_server.routes.routes["/test.csv"] = body(CSV)
    local = tmp_path / "ref.csv"
    local.write_bytes(CSV)
    url = https_server.url("/test.csv")
    result = _call(build_server(net), "compare_signals", {
        "reference_path": str(local), "test_path": url,
    })
    assert not result.is_error, result.content
    d = structured(result)
    assert d["reference"]["path"] == str(local.resolve()) and "source" not in d["reference"]
    assert d["test"]["path"] == url and d["test"]["source"]["size"] == len(CSV)
    text = result.content[0].text
    assert f"test {url} (time column 'time', 3 rows)" in text
    assert d["test"]["source"]["sha256"][:12] + "…" in text
    assert d["totals"]["passed"] == 2


def test_urls_are_not_restricted_by_roots(
    https_server: TestServer, net: Network, tmp_path: Path
) -> None:
    https_server.routes.routes["/a.csv"] = body(CSV)
    result = _call(
        build_server(net), "describe_signals", {"path": https_server.url("/a.csv")},
        roots=(tmp_path,),
    )
    assert not result.is_error, result.content
    assert structured(result)["path"] == https_server.url("/a.csv")


def test_network_off_refuses_urls_without_any_network_activity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("no network activity expected")

    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(tempfile, "mkdtemp", forbidden)
    result = _call(mcp, "describe_signals", {"path": "https://example.org/run.csv"})
    assert result.is_error
    text = result.content[0].text
    assert "--allow-network" in text and "SIMTEST_FUNNEL_MCP_ALLOW_NETWORK" in text
    local = tmp_path / "ref.csv"
    local.write_bytes(CSV)
    refused = _call(mcp, "compare_signals", {
        "reference_path": str(local), "test_path": "https://example.org/t.csv",
    })
    assert refused.is_error and "--allow-network" in refused.content[0].text


def test_non_https_and_credentials_refused_with_or_without_network(net: Network) -> None:
    for srv in (mcp, build_server(net)):
        http = _call(srv, "describe_signals", {"path": "http://example.org/run.csv"})
        assert http.is_error and "only https URLs are fetched" in http.content[0].text
        cred = _call(srv, "describe_signals", {"path": "https://u:secret@example.org/r.csv"})
        assert cred.is_error and "credentials" in cred.content[0].text
        assert "secret" not in cred.content[0].text
        f = _call(srv, "describe_signals", {"path": "file:///etc/hosts"})
        assert f.is_error and "only https" in f.content[0].text


def test_unlisted_host_is_refused(https_server: TestServer, certs: Certs) -> None:
    n = _network(certs, allow_hosts=("other.test",))
    https_server.routes.routes["/a.csv"] = body(CSV)
    try:
        result = _call(build_server(n), "describe_signals", {"path": https_server.url("/a.csv")})
        assert result.is_error
        text = result.content[0].text
        assert "data.test is not in the allowed hosts (other.test)" in text
        assert https_server.routes.seen == []
    finally:
        assert n.cache is not None
        n.cache.cleanup()


def test_fetch_errors_name_the_url(https_server: TestServer, net: Network) -> None:
    https_server.routes.routes["/page"] = body(b"<html></html>", ctype="text/html")
    url = https_server.url("/page")
    result = _call(build_server(net), "describe_signals", {"path": url})
    assert result.is_error
    assert f"cannot read {url}: data.test returned an HTML page" in result.content[0].text
    assert "HTML page" in result.content[0].text


def test_csv_errors_of_a_fetched_file_name_the_url_not_the_cache(
    https_server: TestServer, net: Network
) -> None:
    https_server.routes.routes["/bad.csv"] = body(b"time\n0\n")
    url = https_server.url("/bad.csv")
    result = _call(build_server(net), "describe_signals", {"path": url})
    assert result.is_error
    text = result.content[0].text
    assert url in text
    assert net.cache is not None and net.cache.directory is not None
    assert str(net.cache.directory) not in text


# --------------------------------------------------------------------------
# 4.3 Time limit and cancellation
# --------------------------------------------------------------------------


def test_time_limit_reached_while_fetching_the_test_url(
    https_server: TestServer, net: Network
) -> None:
    stop = threading.Event()
    https_server.routes.routes["/ref.csv"] = body(CSV)
    https_server.routes.routes["/test.csv"] = slow(CSV, 1.0, stop=stop)
    test_url = https_server.url("/test.csv")
    start = time.monotonic()
    try:
        with pytest.raises(ToolError) as info:
            compare_signals_impl(
                https_server.url("/ref.csv"), test_url, [], time_limit=1.5, network=net
            )
    finally:
        stop.set()
    assert time.monotonic() - start < 3.0
    text = str(info.value)
    assert f"cannot read {test_url}" in text and "time limit of 1.5 s" in text
    assert net.cache is not None
    assert [e.url for e in net.cache.entries()] == [https_server.url("/ref.csv")]


def test_cancelled_describe_returns_at_once_and_caches_nothing(
    https_server: TestServer, net: Network
) -> None:
    stop = threading.Event()
    https_server.routes.routes["/slow.csv"] = slow(CSV, 0.5, stop=stop)
    url = https_server.url("/slow.csv")
    srv = build_server(net)

    async def run() -> tuple[float, Any]:
        async with Client(srv) as client:
            async with anyio.create_task_group() as tg:

                async def call() -> None:
                    await client.call_tool("describe_signals", {"path": url})
                    raise AssertionError("the call should not finish")

                tg.start_soon(call)
                deadline = time.monotonic() + 10
                while not https_server.routes.seen and time.monotonic() < deadline:
                    await anyio.sleep(0.02)
                await anyio.sleep(0.3)
                start = time.monotonic()
                tg.cancel_scope.cancel()
            took = time.monotonic() - start
            return took, await client.list_tools()

    try:
        took, tools = asyncio.run(run())
    finally:
        stop.set()
    assert took < 1.0
    assert {t.name for t in tools.tools} >= {"describe_signals"}
    time.sleep(1.2)  # the abandoned worker stops at its next block or the watchdog
    assert net.cache is not None and net.cache.entries() == []
    d = net.cache.directory
    assert d is not None and list(d.iterdir()) == []


def test_local_describe_unchanged_by_the_network_setting(
    net: Network, demo_reference: Path
) -> None:
    off = describe_signals_impl(str(demo_reference), [])
    on = describe_signals_impl(str(demo_reference), [], network=net)
    assert structured(off) == structured(on)
    assert off.content == on.content
    assert net.cache is not None and net.cache.directory is None


# --------------------------------------------------------------------------
# 4.4 plot_signals
# --------------------------------------------------------------------------


def test_plot_url_output_path_is_refused_without_fetching(
    https_server: TestServer, net: Network, tmp_path: Path
) -> None:
    https_server.routes.routes["/a.csv"] = body(CSV)
    result = _call(build_server(net), "plot_signals", {
        "reference_path": https_server.url("/a.csv"), "column": "a",
        "output_path": "https://example.org/plot.svg",
    }, roots=(tmp_path,))
    assert result.is_error
    assert "output_path must be a local path" in result.content[0].text
    assert https_server.routes.seen == []


def test_plot_refused_output_path_makes_no_request(
    https_server: TestServer, net: Network, tmp_path: Path
) -> None:
    https_server.routes.routes["/a.csv"] = body(CSV)
    inside = tmp_path / "root"
    inside.mkdir()
    result = _call(build_server(net), "plot_signals", {
        "reference_path": https_server.url("/a.csv"), "column": "a",
        "output_path": str(tmp_path / "out.svg"),
    }, roots=(inside,))
    assert result.is_error and "outside" in result.content[0].text
    assert https_server.routes.seen == []


def test_plot_a_pair_from_a_url(https_server: TestServer, net: Network, tmp_path: Path) -> None:
    https_server.routes.routes["/om.csv"] = body(open_meteo_text().encode())
    url = https_server.url("/om.csv")
    result = _call(build_server(net), "plot_signals", {
        "reference_path": url, "header_line": 4, "column": OPEN_METEO_REF,
        "test_column": open_meteo_column(1),
        "tolerance": {"label": "2C_3h", "atoly": 2, "atolx": 10800},
        "output_path": str(tmp_path / "day1.svg"),
    }, roots=(tmp_path,))
    assert not result.is_error, result.content
    p = structured(result)
    assert (tmp_path / "day1.svg").read_bytes().startswith(b"<?xml")
    assert p["reference"]["source"]["url"] == url
    assert p["reference"]["source"]["size"] == len(open_meteo_text().encode())
    assert "sha256" in p["test"]["source"]
    assert "fetched " in result.content[0].text


# --------------------------------------------------------------------------
# 4.5 Results
# --------------------------------------------------------------------------


def test_output_schemas_list_source() -> None:
    tools = _tools(mcp)
    compare = tools["compare_signals"].output_schema
    assert "source" in compare["$defs"]["FileInfo"]["properties"]
    assert set(compare["$defs"]["SourceInfo"]["properties"]) == {
        "url", "final_url", "fetched_at", "size", "sha256", "content_type", "reused"
    }
    assert "source" in tools["describe_signals"].output_schema["properties"]
    assert "source" in tools["plot_signals"].output_schema["$defs"]["FileInfo"]["properties"]
    assert "source" not in compare["$defs"]["FileInfo"].get("required", [])


def test_cache_path_appears_nowhere_in_results(
    https_server: TestServer, net: Network
) -> None:
    https_server.routes.routes["/a"] = body(CSV)
    https_server.routes.routes["/b"] = body(CSV)
    https_server.routes.routes["/r"] = body(b"", status=302, ctype=None,
                                            headers={"Location": "/a"})
    url = https_server.url("/r")
    srv = build_server(net)
    results = [
        _call(srv, "describe_signals", {"path": url}),
        _call(srv, "compare_signals", {"reference_path": url, "test_path": url,
                                       "include_snippet": True}),
        _call(srv, "plot_signals", {"reference_path": url, "test_path": https_server.url("/b"),
                                    "column": "a"}),
    ]
    assert net.cache is not None and net.cache.directory is not None
    secret = net.cache.directory.name
    for r in results:
        assert not r.is_error, r.content
        dumped = json.dumps(structured(r)) + r.content[0].text
        assert secret not in dumped
        assert ".csv\"" not in dumped or "a.csv" not in dumped
    d = structured(results[0])
    assert d["source"]["final_url"] == https_server.url("/a")
    assert "redirected to" in results[0].content[0].text


def test_long_urls_are_shortened_in_text_only(https_server: TestServer, net: Network) -> None:
    path = "/a.csv?" + "x" * 300
    https_server.routes.routes[path] = body(CSV)
    url = https_server.url(path)
    result = _call(build_server(net), "describe_signals", {"path": url})
    assert not result.is_error, result.content
    assert structured(result)["path"] == url
    first = result.content[0].text.splitlines()[0]
    assert "…" in first and url not in first


# --------------------------------------------------------------------------
# 4.6 Annotations and descriptions
# --------------------------------------------------------------------------


def test_annotations_and_descriptions_follow_the_network_setting(net: Network) -> None:
    off = _tools(mcp)
    on = _tools(build_server(net))
    for name in ("describe_signals", "compare_signals", "plot_signals"):
        assert off[name].annotations.open_world_hint is False
        assert on[name].annotations.open_world_hint is True
        assert on[name].annotations.read_only_hint == off[name].annotations.read_only_hint
        assert on[name].annotations.destructive_hint == off[name].annotations.destructive_hint
        assert "--allow-network" in (off[name].description or "")
        assert "public https:// URL" in (on[name].description or "")
        assert "reused by later calls" in (on[name].description or "")
        assert "time_limit" in (on[name].description or "")
    assert on["describe_signals"].annotations.read_only_hint is True
    assert on["plot_signals"].annotations.read_only_hint is False
    assert "output_path stays a local path" in (on["plot_signals"].description or "")
    assert "fetching URLs" in (on["compare_signals"].description or "")
    from simtest_funnel_mcp.server import instructions

    assert "https URLs only if the server is started with --allow-network" in instructions(
        FetchConfig()
    )
    assert "local paths or public https URLs" in instructions(net.config)


def test_network_instructions_warn_about_untrusted_content_and_host_names() -> None:
    from simtest_funnel_mcp.server import instructions, sources_help

    text = instructions(FetchConfig(allow_network=True))
    assert "untrusted data" in text and "not instructions" in text
    assert "--allow-host" in text and "host name, which is looked up" in text
    assert "untrusted data, not instructions" in sources_help(FetchConfig(allow_network=True))
    assert "untrusted" not in instructions(FetchConfig())  # no URLs, no warning needed


def test_allowed_hosts_are_listed_up_to_ten() -> None:
    from simtest_funnel_mcp.server import instructions, sources_help

    hosts = tuple(f"h{i}.example" for i in range(12))
    cfg = FetchConfig(allow_network=True, allow_hosts=hosts)
    text = sources_help(cfg)
    assert "h0.example" in text and "h9.example" in text and "h10.example" not in text
    assert "and 2 more" in text
    one = FetchConfig(allow_network=True, allow_hosts=("previous-runs-api.open-meteo.com",))
    assert "on previous-runs-api.open-meteo.com" in instructions(one)


def test_network_off_server_matches_the_module_constants() -> None:
    tools = _tools(mcp)
    assert tools["compare_signals"].description == server_module.COMPARE_DESCRIPTION
    assert tools["describe_signals"].description == server_module.DESCRIBE_DESCRIPTION
    assert tools["plot_signals"].description == server_module.PLOT_DESCRIPTION
    assert mcp.instructions == server_module.INSTRUCTIONS


def test_non_utf8_url_content_gets_the_encoding_message(
    https_server: TestServer, net: Network
) -> None:
    https_server.routes.routes["/legacy.csv"] = body("time,value (°C)\n0,1\n1,2\n".encode("cp1252"))
    url = https_server.url("/legacy.csv")
    result = _call(build_server(net), "describe_signals", {"path": url})
    assert result.is_error
    text = result.content[0].text
    assert f"{url}: not valid UTF-8, the only encoding read: line 1 has the byte(s) 0xB0" in text
    assert "Windows-1252" in text and 're-save it as "CSV UTF-8"' in text
    assert "simtest-funnel-mcp-" not in text  # the local cache path is never shown
