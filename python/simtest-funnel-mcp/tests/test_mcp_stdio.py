"""End to end: the server as a stdio subprocess driven by the MCP SDK client."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import OPEN_METEO_REF, REPO_ROOT, open_meteo_column
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
    # Raw samples never cross the wire (the snippet embeds the ~11 kB CSV reader).
    assert len(json.dumps(d)) < 18_000

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


def test_stdio_pairs_and_date_axis_plot(open_meteo: Path, tmp_path: Path) -> None:
    """One-file pair comparison and a date-axis plot of an Open-Meteo-shaped file."""
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "simtest_funnel_mcp"], cwd=str(tmp_path)
    )
    pairs = [
        {"reference": OPEN_METEO_REF, "test": open_meteo_column(d), "label": f"day{d}"}
        for d in (1, 3, 5)
    ]

    async def script(client: Client) -> dict[str, Any]:
        return {
            "describe": await client.call_tool(
                "describe_signals", {"path": str(open_meteo)}
            ),
            "compare": await client.call_tool(
                "compare_signals",
                {
                    "reference_path": str(open_meteo),
                    "header_line": 4,
                    "pairs": pairs,
                    "tolerances": [{"label": "2C_3h", "atoly": 2, "atolx": 10800}],
                    "include_snippet": True,
                },
            ),
            "plot": await client.call_tool(
                "plot_signals",
                {
                    "reference_path": str(open_meteo),
                    "header_line": 4,
                    "column": OPEN_METEO_REF,
                    "test_column": open_meteo_column(3),
                    "tolerance": {"label": "2C_3h", "atoly": 2, "atolx": 10800},
                    "x_range": {"lo": "2026-11-10T00:00", "hi": "2026-11-12T00:00"},
                    "output_path": str(tmp_path / "day3.svg"),
                },
            ),
        }

    out = _session(params, (open_meteo.parent,), script)
    describe = out["describe"]
    assert not describe.is_error, describe.content
    assert "pass header_line=4" in describe.structured_content["problems"][0]

    compare = out["compare"]
    assert not compare.is_error, compare.content
    d = compare.structured_content
    assert d["totals"]["rows"] == 3
    assert {r["column"] for r in d["rows"]} == {"day1", "day3", "day5"}
    assert d["tolerance_sets"][0]["time_tolerance"] == {"seconds": 10800.0, "duration": "PT3H"}
    assert "TEST = REFERENCE" in d["snippet"]
    assert "day5 (temperature_2m (°C) -> temperature_2m_previous_day5 (°C))" in (
        compare.content[0].text
    )

    plot = out["plot"]
    assert not plot.is_error, plot.content
    text, image = plot.content
    p = plot.structured_content
    assert p["view"]["lo_iso"] == "2026-11-10T00:00:00"
    assert p["view"]["hi_iso"] == "2026-11-12T00:00:00"
    assert p["row"]["test_column"] == open_meteo_column(3)
    assert "time 2026-11-10T00:00:00 .. 2026-11-12T00:00:00" in text.text
    preview = base64.b64decode(image.data)
    assert preview[:8] == b"\x89PNG\r\n\x1a\n"
    svg = (tmp_path / "day3.svg").read_text()
    assert "<!-- 2026-11-10 00:00 -->" in svg and "<!-- time (no time zone) -->" in svg
    keep = os.environ.get("SIMTEST_FUNNEL_KEEP_PREVIEW")
    if keep:  # for looking at the preview by hand
        Path(keep).write_bytes(preview)


def test_stdio_output_dir_without_roots(demo_reference: Path, demo_test: Path,
                                        tmp_path: Path) -> None:
    """A client without roots: writing needs --output-dir or the env variable."""
    cli_dir = tmp_path / "cli"
    env_dir = tmp_path / "env"
    cli_dir.mkdir()
    env_dir.mkdir()
    args = {
        "reference_path": str(demo_reference),
        "test_path": str(demo_test),
        "column": "z",
    }

    async def script(client: Client) -> dict[str, Any]:
        return {
            "relative": await client.call_tool("plot_signals", {**args, "output_path": "z.svg"}),
            "env": await client.call_tool(
                "plot_signals", {**args, "output_path": str(env_dir / "z.svg")}
            ),
            "outside": await client.call_tool(
                "plot_signals", {**args, "output_path": str(tmp_path / "z.svg")}
            ),
        }

    env = {**os.environ, "SIMTEST_FUNNEL_MCP_OUTPUT_DIR": str(env_dir)}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "simtest_funnel_mcp", "--output-dir", str(cli_dir)],
        cwd=str(tmp_path),
        env=env,
    )
    out = _session(params, None, script)
    assert not out["relative"].is_error, out["relative"].content
    assert out["relative"].structured_content["file"]["path"] == str((cli_dir / "z.svg").resolve())
    assert not out["env"].is_error, out["env"].content
    assert (env_dir / "z.svg").read_bytes().startswith(b"<?xml")
    assert out["outside"].is_error
    assert "outside the configured output directories" in out["outside"].content[0].text
    assert not (tmp_path / "z.svg").exists()

    # Neither roots nor an output directory: no file, but the preview works.
    env.pop("SIMTEST_FUNNEL_MCP_OUTPUT_DIR")
    bare = StdioServerParameters(
        command=sys.executable, args=["-m", "simtest_funnel_mcp"], cwd=str(tmp_path), env=env
    )

    async def bare_script(client: Client) -> dict[str, Any]:
        return {
            "write": await client.call_tool("plot_signals", {**args, "output_path": "y.svg"}),
            "preview": await client.call_tool("plot_signals", args),
        }

    out = _session(bare, None, bare_script)
    assert out["write"].is_error
    assert "--output-dir" in out["write"].content[0].text
    assert not (tmp_path / "y.svg").exists()
    assert not out["preview"].is_error
    assert out["preview"].content[1].mime_type == "image/png"


def test_stdio_start_up_rejects_missing_output_dir(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "simtest_funnel_mcp", "--output-dir", str(tmp_path / "nope")],
        capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
    )
    assert proc.returncode == 2
    assert "does not exist" in proc.stderr and "--output-dir" in proc.stderr


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
