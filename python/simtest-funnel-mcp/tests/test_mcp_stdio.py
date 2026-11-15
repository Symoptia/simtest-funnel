"""End to end: the server as a stdio subprocess driven by the MCP SDK client."""

from __future__ import annotations

import asyncio
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


def _session(params: StdioServerParameters, roots: Path | None, script: Any) -> Any:
    async def list_roots(context: object) -> ListRootsResult:
        assert roots is not None
        return ListRootsResult(roots=[Root(uri=roots.resolve().as_uri())])  # type: ignore[arg-type]

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
        return out

    out = _session(params, demo_reference.parent, script)
    assert out["server"].name == "simtest-funnel"
    assert out["protocol"]
    assert "CSV" in out["instructions"]
    assert {t.name for t in out["tools"].tools} == {"describe_signals", "compare_signals"}

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
    # Raw samples never cross the wire.
    assert len(json.dumps(d)) < 10_000

    assert out["outside"].is_error
    assert "outside the client's workspace roots" in out["outside"].content[0].text


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
    assert {t.name for t in tools.tools} == {"describe_signals", "compare_signals"}
