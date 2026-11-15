# Proposal

## Why

Local AI agents (Claude Code, Claude Desktop and other MCP-capable
frameworks) are regularly asked whether one signal is "close enough" to a
reference and to draw conclusions from the answer. Today they improvise a
comparison in a scripting sandbox: that costs many tokens and round
trips, yields a different ad-hoc algorithm each time, and usually ignores
tolerance along the time axis. No existing MCP server offers a
tolerance-tube (funnel) verdict. Exposing this library as a local MCP
server gives agents a cheap, deterministic, LBNL-Funnel-compatible
primitive.

## What Changes

- Add a local MCP server, written in Python on top of `simtest.funnel`,
  distributed as its own package and started over stdio (for example
  `uvx simtest-funnel-mcp`). Its two tools are read-only and stateless: files are
  addressed by path on every call; there is no load step and there are
  no handles.
- Signals are read by the server from local CSV files with a shared time
  column (comma-separated, header row, `#` comment lines — the same
  dialect as the CLI). Raw samples never pass through the model's
  context.
- Tool `describe_signals(path)`: column names, detected time column, row
  count, time span, sampling (uniform or not; min/median/max step),
  per-column min/max/range, and problems (non-numeric data, NaN,
  non-monotonic time). It gives an agent what it needs to choose
  sensible tolerances.
- Tool `compare_signals(reference_path, test_path, ...)`:
  - compares all common columns by default, or a given subset, with
    optional per-column tolerance overrides and an optional x-range;
  - takes **explicit tolerances** using the library's six coefficient
    names; several labelled tolerance sets may be passed in one call;
  - partially specified and omitted tolerances are resolved by the
    library rule from `align-default-tolerances`; the six resolved
    values are always echoed back;
  - returns one row per (column, tolerance set) with the verdict and
    headline numbers; violation-interval details (from
    `add-violation-summary`) only for failures, worst first, capped at a
    caller-adjustable maximum with the total count stated;
  - reports per-column problems (missing column, non-numeric data,
    non-monotonic time) through the library's status codes instead of
    failing the whole call;
  - returns structured content plus a short text rendering;
  - on request, includes one reproducible Python/pytest snippet (same
    files, columns and tolerances) that an agent can place in a CI
    pipeline. The server itself is not a CI component.
- Time column: a column named `time` (case-insensitive) if present,
  otherwise the first column; the choice is echoed back.
- Tool descriptions explain the six tolerance coefficients well enough
  for an agent to map a request such as "1 % in y, 0.5 s in x" onto them.
- File access: the server reads any path it is given and honours the
  client's declared workspace roots when the client provides them.
- Registration instructions for Claude Code and Claude Desktop, and a
  checked-in `.mcp.json` so the server can be used on this repository.

Explicitly out of scope (planned as later changes):

- Plots (`add-mcp-plots`).
- Fetching signals from URLs and an example-dataset gallery
  (`add-mcp-url-ingestion`).
- A Claude skill for files uploaded to claude.ai (`add-claude-skill`).
- Remote/HTTP hosting (`add-mcp-remote-deploy`).
- File formats other than CSV.
- Any tolerance-free closeness measure.

## Capabilities

### New Capabilities

- `mcp-server`: the local MCP server — transport, the two tools, CSV
  signal loading, comparison with one or several explicit tolerance
  sets, result shape and size limits, and the reproducible snippet.

### Modified Capabilities

<!-- none -->

## Impact

- New Python package in this repository (working name
  `simtest-funnel-mcp`), depending on `simtest-funnel` and an MCP SDK;
  added to the uv workspace.
- Release pipeline: one more PyPI artifact, versioned with the rest.
- Depends on `add-violation-summary` and `align-default-tolerances`
  (both implemented).
- **Prerequisite for real-world use:** `simtest-funnel` is currently
  published to PyPI only as a Linux x86-64 / CPython 3.12 wheel with no
  source distribution, so the server cannot be installed on macOS,
  Windows, ARM Linux or other Python versions until cross-platform
  wheels are published (separate change).
- Assumptions carried from exploration, to be settled in design:
  Python as implementation language; separate package rather than an
  extra of `simtest-funnel`.
