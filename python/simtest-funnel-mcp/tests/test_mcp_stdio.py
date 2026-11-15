"""End to end: the server as a stdio subprocess driven by the MCP SDK client."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import REPO_ROOT
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp_types import ListRootsResult, Root


def _session(
    params: StdioServerParameters, roots: tuple[Path, ...] | None, script: Any
) -> Any:
    async def list_roots(context: object) -> ListRootsResult:
        assert roots is not None
        return ListRootsResult(
            roots=[Root(uri=r.resolve().as_uri()) for r in roots]  # type: ignore[arg-type]
        )

    async def run() -> Any:
        kwargs: dict[str, Any] = {"read_timeout_seconds": 60}
        if roots is not None:
            kwargs["list_roots_callback"] = list_roots
        async with Client(params, **kwargs) as client:
            return await script(client)

    return asyncio.run(run())


def test_stdio_end_to_end(demo_reference: Path, demo_test: Path, tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "simtest_funnel_mcp"], cwd=str(tmp_path)
    )

    async def script(client: Client) -> dict[str, Any]:
        out: dict[str, Any] = {}
        out["server"] = client.server_info
        out["protocol"] = client.protocol_version
        out["instructions"] = client.instructions
        out["tools"] = await client.list_tools()
        out["describe"] = await client.call_tool(
            "describe_signals", {"path": "reference.csv"}
        )
        out["compare"] = await client.call_tool(
            "compare_signals",
            {
                "reference_path": str(demo_reference),
                "test_path": str(demo_test),
                "tolerances": [
                    {"label": "loose", "atolx": 0.1, "atoly": 0.1},
                    {"label": "noxtol", "atolx": 0, "atoly": 0.1},
                ],
                "max_intervals": 2,
                "include_snippet": True,
            },
        )
        out["outside"] = await client.call_tool("describe_signals", {"path": "/etc/hostname"})
        out["plot"] = await client.call_tool(
            "plot_signals",
            {
                "reference_path": str(demo_reference),
                "test_path": str(demo_test),
                "column": "z",
                "tolerance": {"label": "loose", "atolx": 0.1, "atoly": 0.1},
                "output_path": str(tmp_path / "z.svg"),
            },
        )
        out["plot_outside"] = await client.call_tool(
            "plot_signals",
            {
                "reference_path": str(demo_reference),
                "test_path": str(demo_test),
                "column": "z",
                "output_path": "/tmp/simtest-funnel-should-not-exist.svg",
            },
        )
        return out

    out = _session(params, (demo_reference.parent, tmp_path), script)
    assert out["server"].name == "simtest-funnel"
    assert out["protocol"]
    assert "CSV" in out["instructions"]
    tools = {t.name: t for t in out["tools"].tools}
    assert set(tools) == {"describe_signals", "compare_signals", "plot_signals"}
    assert tools["compare_signals"].annotations.read_only_hint is True
    assert tools["plot_signals"].annotations.read_only_hint is False
    assert "plot_signals" in out["instructions"]

    describe = out["describe"]
    assert not describe.is_error, describe.content
    assert describe.structured_content["row_count"] == 1001
    assert "1001 rows" in describe.content[0].text

    compare = out["compare"]
    assert not compare.is_error, compare.content
    d = compare.structured_content
    assert d["totals"] == {"rows": 6, "passed": 3, "failed": 3, "errors": 0}
    fails = [r for r in d["rows"] if r["verdict"] == "fail"]
    assert {(r["column"], r["tolerance_set"]) for r in fails} == {
        ("z", "loose"), ("y", "noxtol"), ("z", "noxtol")
    }
    assert all(len(r["intervals"]) <= 2 for r in fails)
    assert d["snippet"].startswith('"""Funnel comparison reproduced')
    assert "PASS [loose]: x, y" in compare.content[0].text
    # Raw samples never cross the wire (the snippet embeds the ~4 kB CSV reader).
    assert len(json.dumps(d)) < 12_000

    assert out["outside"].is_error
    assert "outside the client's workspace roots" in out["outside"].content[0].text

    plot = out["plot"]
    assert not plot.is_error, plot.content
    text, image = plot.content
    assert text.type == "text" and "FAIL z [loose]" in text.text
    assert image.type == "image" and image.mime_type == "image/png"
    preview = base64.b64decode(image.data)
    assert preview[:8] == b"\x89PNG\r\n\x1a\n"
    assert preview[16:24] == (800).to_bytes(4, "big") + (450).to_bytes(4, "big")
    p = plot.structured_content
    assert p["row"]["verdict"] == "fail" and p["preview"]["bytes"] == len(preview)
    assert p["file"]["path"] == str((tmp_path / "z.svg").resolve())
    assert (tmp_path / "z.svg").read_bytes().startswith(b"<?xml")
    assert len(json.dumps(p)) < 4_000

    assert out["plot_outside"].is_error
    assert "outside the client's workspace roots" in out["plot_outside"].content[0].text
    assert not Path("/tmp/simtest-funnel-should-not-exist.svg").exists()


def test_checked_in_mcp_json_starts_the_server() -> None:
    config = json.loads((REPO_ROOT / ".mcp.json").read_text())
    server = config["mcpServers"]["simtest-funnel"]
    if shutil.which(server["command"]) is None:
        pytest.skip(f"{server['command']} not on PATH")
    params = StdioServerParameters(
        command=server["command"],
        args=server["args"],
        cwd=str(REPO_ROOT),
        env={**os.environ, **server.get("env", {})},
    )

    async def script(client: Client) -> Any:
        return await client.list_tools()

    tools = _session(params, None, script)
    assert {t.name for t in tools.tools} == {
        "describe_signals", "compare_signals", "plot_signals"
    }
