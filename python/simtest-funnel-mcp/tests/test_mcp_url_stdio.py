"""End to end over stdio with network access enabled, against the local
HTTPS test server: tools, cache cleanup on end of input and on SIGTERM,
responsiveness during a slow fetch."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import anyio
import pytest
from conftest import OPEN_METEO_REF, open_meteo_column, open_meteo_text
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from urlserver import Certs, TestServer, body, slow

LAUNCHER = Path(__file__).with_name("net_server.py")
CSV = b"time,a,b\n0,1,2\n1,2,3\n2,3,4\n"


def _env(tmpdir: Path) -> dict[str, str]:
    # The cache directory lands in TMPDIR, so the test can watch it.
    return {**os.environ, "TMPDIR": str(tmpdir), "TEMP": str(tmpdir), "TMP": str(tmpdir)}


def _cache_dirs(tmpdir: Path) -> list[Path]:
    return sorted(tmpdir.glob("simtest-funnel-mcp-*"))


def _params(certs: Certs, tmpdir: Path, cwd: Path, *options: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=[str(LAUNCHER), str(certs.ca), *options],
        cwd=str(cwd),
        env=_env(tmpdir),
    )


def _run(params: StdioServerParameters, script: Any) -> Any:
    async def run() -> Any:
        async with Client(params, read_timeout_seconds=60) as client:
            return await script(client)

    return asyncio.run(run())


def test_stdio_with_network_end_to_end(
    https_server: TestServer, certs: Certs, tmp_path: Path
) -> None:
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    https_server.routes.routes["/om.csv"] = body(open_meteo_text().encode(), gzipped=True)
    url = https_server.url("/om.csv")
    pairs = [
        {"reference": OPEN_METEO_REF, "test": open_meteo_column(d), "label": f"day{d}"}
        for d in (1, 3, 5)
    ]
    seen_dirs: list[list[Path]] = []

    async def script(client: Client) -> dict[str, Any]:
        out: dict[str, Any] = {"instructions": client.instructions}
        out["tools"] = await client.list_tools()
        out["describe"] = await client.call_tool(
            "describe_signals", {"path": url, "header_line": 4}
        )
        seen_dirs.append(_cache_dirs(tmpdir))
        out["compare"] = await client.call_tool("compare_signals", {
            "reference_path": url, "header_line": 4, "pairs": pairs,
            "tolerances": [{"label": "2C", "atoly": 2}, {"label": "2C_3h", "atoly": 2,
                                                          "atolx": 10800}],
            "include_snippet": True,
        })
        out["plot"] = await client.call_tool("plot_signals", {
            "reference_path": url, "header_line": 4, "column": OPEN_METEO_REF,
            "test_column": open_meteo_column(3),
            "tolerance": {"label": "2C_3h", "atoly": 2, "atolx": 10800},
            "output_path": str(tmp_path / "day3.png"),
        })
        out["http"] = await client.call_tool("describe_signals", {"path": "http://x.org/a"})
        return out

    roots_params = _params(certs, tmpdir, tmp_path, "--allow-host", "data.test")

    async def run() -> Any:
        from mcp_types import ListRootsResult, Root

        async def roots(context: object) -> ListRootsResult:
            return ListRootsResult(roots=[Root(uri=tmp_path.resolve().as_uri())])  # type: ignore[arg-type]

        async with Client(roots_params, read_timeout_seconds=60,
                          list_roots_callback=roots) as client:
            return await script(client)

    out = asyncio.run(run())
    tools = {t.name: t for t in out["tools"].tools}
    assert all(t.annotations.open_world_hint is True for t in tools.values())
    assert "on data.test" in out["instructions"]
    d = out["describe"]
    assert not d.is_error, d.content
    assert d.structured_content["path"] == url
    assert d.structured_content["time"]["kind"] == "datetime"
    assert d.structured_content["source"]["reused"] is False
    c = out["compare"]
    assert not c.is_error, c.content
    cd = c.structured_content
    assert cd["totals"]["rows"] == 6
    assert cd["reference"]["source"]["reused"] is True
    assert cd["reference"]["source"]["sha256"] == d.structured_content["source"]["sha256"]
    assert "REFERENCE_SHA256" in cd["snippet"] and "TEST = REFERENCE" in cd["snippet"]
    p = out["plot"]
    assert not p.is_error, p.content
    assert (tmp_path / "day3.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out["http"].is_error
    assert https_server.routes.count("/om.csv") == 1
    # The cache existed while serving and is gone after end of input.
    assert len(seen_dirs[0]) == 1
    deadline = time.monotonic() + 10
    while _cache_dirs(tmpdir) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert _cache_dirs(tmpdir) == []


def test_stdio_without_network_creates_no_directory(
    certs: Certs, tmp_path: Path, demo_reference: Path, demo_test: Path
) -> None:
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()

    async def script(client: Client) -> Any:
        tools = await client.list_tools()
        res = await client.call_tool("compare_signals", {
            "reference_path": str(demo_reference), "test_path": str(demo_test),
        })
        url = await client.call_tool("describe_signals", {"path": "https://data.test/a.csv"})
        return tools, res, url

    tools, res, url = _run(_params(certs, tmpdir, tmp_path), script)
    assert all(t.annotations.open_world_hint is False for t in tools.tools)
    assert not res.is_error
    assert url.is_error and "--allow-network" in url.content[0].text
    assert list(tmpdir.iterdir()) == []


def test_tools_list_is_answered_during_a_slow_fetch(
    https_server: TestServer, certs: Certs, tmp_path: Path
) -> None:
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    stop = threading.Event()
    https_server.routes.routes["/slow.csv"] = slow(CSV, 0.5, stop=stop)
    url = https_server.url("/slow.csv")

    async def script(client: Client) -> Any:
        async with anyio.create_task_group() as tg:

            async def call() -> None:
                await client.call_tool("describe_signals", {"path": url})

            tg.start_soon(call)
            deadline = time.monotonic() + 20
            while not https_server.routes.seen and time.monotonic() < deadline:
                await anyio.sleep(0.02)
            start = time.monotonic()
            tools = await client.list_tools()
            took = time.monotonic() - start
            tg.cancel_scope.cancel()
        return took, tools

    try:
        took, tools = _run(_params(certs, tmpdir, tmp_path, "--allow-network"), script)
    finally:
        stop.set()
    assert took < 1.0
    assert {t.name for t in tools.tools} >= {"describe_signals"}


def _rpc(proc: subprocess.Popen[bytes], message: dict[str, Any]) -> None:
    assert proc.stdin is not None
    proc.stdin.write((json.dumps(message) + "\n").encode())
    proc.stdin.flush()


def _read_response(proc: subprocess.Popen[bytes], rid: int, timeout: float = 30) -> Any:
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        msg = json.loads(line)
        if msg.get("id") == rid:
            return msg
    raise AssertionError("no response")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigterm_removes_the_cache(
    https_server: TestServer, certs: Certs, tmp_path: Path
) -> None:
    tmpdir = tmp_path / "tmp"
    tmpdir.mkdir()
    https_server.routes.routes["/a.csv"] = body(CSV)
    proc = subprocess.Popen(
        [sys.executable, str(LAUNCHER), str(certs.ca), "--allow-network"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=_env(tmpdir), cwd=str(tmp_path),
    )
    try:
        _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "t", "version": "0"}}})
        _read_response(proc, 1)
        _rpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "describe_signals", "arguments": {"path": https_server.url("/a.csv")}}})
        reply = _read_response(proc, 2)
        assert not reply["result"].get("isError"), reply
        assert len(_cache_dirs(tmpdir)) == 1
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=20)
        assert _cache_dirs(tmpdir) == []
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
