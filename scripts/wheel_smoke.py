"""Smoke test of installed simtest-funnel (and simtest-funnel-mcp) wheels.

Run with the interpreter of a clean environment into which the freshly built
wheels were installed, from a directory outside the source tree:

    python wheel_smoke.py          # simtest-funnel: import, one comparison
    python wheel_smoke.py --mcp    # also start the MCP server over stdio

Standard library only (plus the installed packages under test), so it runs
unchanged on Linux, macOS and Windows. Used by
.github/workflows/python-wheels.yml.
"""

from __future__ import annotations

import argparse
import json
import queue
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

TIMEOUT = 120.0
EXPECTED_TOOLS = {"describe_signals", "compare_signals", "plot_signals"}


def smoke_library() -> None:
    import numpy as np

    import simtest.funnel as funnel
    from simtest.funnel import Options, Tolerances, compare

    location = Path(funnel.__file__).resolve()
    print(f"simtest.funnel {funnel._simtest_funnel.version()} from {location}")
    if "site-packages" not in location.parts:
        sys.exit(f"simtest.funnel imported from the source tree, not the wheel: {location}")
    print(f"extension module: {Path(funnel._simtest_funnel.__file__).name}")

    t = np.linspace(0.0, 1.0, 101)
    y = np.sin(2 * np.pi * t)
    opts = Options(tolerances=Tolerances(atoly=0.05))
    passed = compare(t, y, t, y + 0.01, opts)
    failed = compare(t, y, t, y + 0.1, opts)
    if passed.status != 0 or failed.status != -1:
        sys.exit(f"unexpected statuses: pass case {passed.status}, fail case {failed.status}")
    print(f"compare: pass case status {passed.status}, fail case status {failed.status}")


class StdioClient:
    """Minimal newline-delimited JSON-RPC client for an MCP stdio server."""

    def __init__(self, cwd: Path) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "simtest_funnel_mcp"],
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            encoding="utf-8",
        )
        self.lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.next_id = 0

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def send(self, message: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        while True:
            try:
                line = self.lines.get(timeout=TIMEOUT)
            except queue.Empty:
                sys.exit(f"no answer to {method} within {TIMEOUT} s")
            if line is None:
                sys.exit(f"server exited (code {self.proc.wait()}) before answering {method}")
            message = json.loads(line)
            if message.get("id") == self.next_id and "method" not in message:
                if "error" in message:
                    sys.exit(f"{method} failed: {message['error']}")
                result: dict[str, Any] = message["result"]
                return result

    def close(self) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        try:
            code = self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            sys.exit("server did not exit after stdin was closed")
        if code != 0:
            sys.exit(f"server exited with code {code}")


def smoke_mcp() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "reference.csv").write_text("time,x\n0,0\n1,1\n2,2\n3,3\n", encoding="utf-8")
        (work / "test.csv").write_text("time,x\n0,0\n1,1.5\n2,2\n3,3\n", encoding="utf-8")
        client = StdioClient(work)
        init = client.request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "wheel-smoke", "version": "0"},
            },
        )
        print(f"server: {init['serverInfo']}, protocol {init['protocolVersion']}")
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools = {t["name"] for t in client.request("tools/list", {})["tools"]}
        print(f"tools/list: {sorted(tools)}")
        if not EXPECTED_TOOLS <= tools:
            sys.exit(f"missing tools: {sorted(EXPECTED_TOOLS - tools)}")
        result = client.request(
            "tools/call",
            {
                "name": "compare_signals",
                "arguments": {
                    "reference_path": str(work / "reference.csv"),
                    "test_path": str(work / "test.csv"),
                    "tolerances": [{"atoly": 0.1}],
                },
            },
        )
        rows = result.get("structuredContent", {}).get("rows", [])
        verdicts = [r.get("verdict") for r in rows]
        print(f"compare_signals verdicts: {verdicts}")
        if result.get("isError") or verdicts != ["fail"]:
            sys.exit(f"unexpected compare_signals result: {json.dumps(result)[:2000]}")
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mcp", action="store_true", help="also smoke-test the MCP server")
    args = parser.parse_args()
    print(f"Python {sys.version.split()[0]} on {sys.platform}")
    smoke_library()
    if args.mcp:
        smoke_mcp()
    print("smoke test passed")


if __name__ == "__main__":
    main()
