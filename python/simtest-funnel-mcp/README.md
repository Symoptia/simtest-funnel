# simtest-funnel-mcp

A local [MCP](https://modelcontextprotocol.io) server that lets AI agents
(Claude Code, Claude Desktop, any MCP client) compare signals stored in
local CSV files with the funnel (tolerance-tube) algorithm of
[simtest-funnel](https://github.com/Symoptia/simtest-funnel), a port of
[LBNL Funnel](https://github.com/lbl-srg/funnel).

The server reads the files itself, so raw samples never enter the model's
context. It is read-only and stateless: every call names the files it
reads; nothing is written and no network connection is opened. Transport:
stdio.

> **Platform note:** `simtest-funnel` is currently published to PyPI only
> as a Linux x86-64 / CPython 3.12 wheel, so `uvx simtest-funnel-mcp`
> works only there until cross-platform wheels are published. From a
> checkout of this repository it works wherever the Rust extension builds.

## Tools

### `describe_signals(path)`

Time column (and how it was chosen), row count, time start/end/span,
sampling (uniform or not; min/median/max step), per-column min/max/range
and data problems (non-numeric or empty cells, time not non-decreasing).
Use it to choose columns and tolerances.

### `compare_signals(reference_path, test_path, ...)`

| Argument | Default | Meaning |
| --- | --- | --- |
| `columns` | all common columns | Signal columns to compare |
| `tolerances` | one set, library default | List of sets: optional unique `label` plus any of the six coefficients |
| `column_tolerances` | none | `{column: coefficients}` overrides, applied per axis |
| `x_range` | unbounded | `{"lo": .., "hi": ..}` time window |
| `max_intervals` | 5 | Violation intervals listed per failing row (largest deviation first) |
| `max_rows` | 100 | Rows returned (errors, then failures, then passes); totals always cover all rows |
| `include_snippet` | false | Add a pytest file reproducing the comparison (for CI) |

The result has one row per (column, tolerance set) with verdict
(`pass` / `fail` / `error`), the library status code, points outside the
tube, fractions of points and span outside, the worst deviation and, for
failures only, the violation intervals. Missing columns, bad data and
other per-column problems are reported in their rows instead of failing
the call. Both structured content and a short text rendering are returned.

## CSV dialect

Comma-separated, one header row, lines starting with `#` ignored. The time
column is the first column named `time` (case-insensitive), otherwise the
first column; the choice is echoed back.

## Tolerances

Six coefficients, x = time axis, y = signal value. At each reference sample
the tube half-widths are

```text
half_x = max(atolx, rtolx * time_span_ref, ltolx * |t|)
half_y = max(atoly, rtoly * value_range_ref, ltoly * |y_ref|)
```

- `atol*`: absolute (time units / signal units)
- `rtol*`: fraction of the reference time span / value range
- `ltol*`: fraction of the local `|t|` / `|y_ref|`

Omitted coefficients are resolved by the library, per axis: an axis with no
coefficient given gets `rtol = 0.002`; an axis with any coefficient given
uses `0` for its others; an explicit `0` counts as given. The six resolved
values are always echoed back.

**Tolerance in x** widens the tube along time, so a test signal shifted or
delayed by up to `half_x` still passes; steep edges and small timing
offsets then do not cause false failures.

"1 % in y, 0.5 s in x" is `{"rtoly": 0.01, "atolx": 0.5}` (or `ltoly` for
1 % of the local value).

## Registering the server

### Claude Code

Once published to PyPI:

```bash
claude mcp add simtest-funnel -- uvx simtest-funnel-mcp
```

From a checkout of this repository (use `--scope user` to make it available
in every project):

```bash
claude mcp add simtest-funnel -- uv run --directory /path/to/simtest-funnel --quiet simtest-funnel-mcp
```

Inside this repository nothing needs to be registered: the checked-in
[`.mcp.json`](../../.mcp.json) starts the server with `uv run` from the
workspace (Claude Code asks for approval the first time).

### Claude Desktop

Add to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uvx",
      "args": ["simtest-funnel-mcp"]
    }
  }
}
```

or, from a checkout:

```json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/simtest-funnel", "--quiet", "simtest-funnel-mcp"]
    }
  }
}
```

Use absolute paths in tool calls. When the client declares workspace roots,
the server refuses paths outside them and resolves relative paths against
the first root.

## Development

```bash
make build          # builds the native simtest-funnel module
make test-python    # includes python/simtest-funnel-mcp/tests (incl. stdio end-to-end)
make lint-python    # mypy --strict
uv run simtest-funnel-mcp   # start the server on stdio
```
