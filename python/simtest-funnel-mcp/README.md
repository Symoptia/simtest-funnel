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

### `describe_signals(path, columns=None, max_columns=100)`

Time column (and how it was chosen), row count, time start/end/span,
sampling (uniform or not; min/median/max step), per-column min/max/range
and data problems (non-numeric or empty cells, time not non-decreasing).
Use it to choose columns and tolerances. At most `max_columns` columns and
as many problems are listed; `columns_total`, `columns_selected`,
`columns_omitted` and `problems_omitted` state the rest. `columns` filters
by exact name or glob pattern (`*`, `?`, `[...]`), e.g.
`["*.port.signal"]`.

### `compare_signals(reference_path, test_path, ...)`

| Argument | Default | Meaning |
| --- | --- | --- |
| `columns` | all common columns | Signal columns to compare: exact names or glob patterns (`*`, `?`, `[...]`, matched against the columns of both files) |
| `tolerances` | one set, library default | List of sets: optional unique `label` plus any of the six coefficients |
| `column_tolerances` | none | `{column: coefficients}` overrides, applied per axis |
| `x_range` | unbounded | `{"lo": .., "hi": ..}` time window; finite bounds, omit one for unbounded |
| `max_intervals` | 5 | Violation intervals listed per failing row (largest deviation first) |
| `max_rows` | 100 | Rows returned (errors, then failures, then passes); totals always cover all rows |
| `include_snippet` | false | Add a pytest file reproducing the returned rows (for CI), in the structured field `snippet` |

The result has one row per (column, tolerance set) with verdict
(`pass` / `fail` / `error`), the library status code, points outside the
tube, fractions of points and span outside, the worst deviation and, for
failures only, the violation intervals. Missing columns, bad data and
other per-column problems are reported in their rows instead of failing
the call. Both structured content and a short text rendering are returned.
Time values are never rounded in the structured content; the text prints
them with enough digits to tell adjacent samples apart.

A column passes when every test point inside the compared time range
(`x_range` intersected with the reference time span) lies inside the tube
and, within `x_range`, both files cover the same time span. If one file
covers more time than the other within `x_range`, the row has verdict
`error` with status `MISSING_REFERENCE` (test extends beyond the
reference) or `MISSING_TEST` (the reverse), still reports
`points_compared` / `points_outside`, and its `problem` text names both
time spans and the exact `x_range` that compares the overlap.

### Pytest snippet

With `include_snippet=true` the result carries a self-contained pytest
module (structured field `snippet`, sent once; the text rendering only
points to it) that asserts the observed status of every returned row; rows
omitted by `max_rows` are listed as a comment, and the snippet is capped
at 64 kB. It embeds the server's CSV reader verbatim. Data paths under the
first workspace root (else the server's working directory) are written
relative to it and resolved at run time against
`$SIMTEST_FUNNEL_DATA_ROOT`, defaulting to the current directory, so run
pytest from the same place in a CI checkout. Files outside that base keep
their absolute path, with a comment that they will not resolve elsewhere.

## CSV dialect

Comma-separated, one header row (UTF-8, optional BOM). Lines whose first
non-blank character is `#` and blank lines are ignored; a `#` anywhere
else is data (e.g. a column `a#1`). A data row with more fields than the
header is an error naming the row and line; a trailing delimiter on every
line, header included, is accepted (the empty last column is dropped).
Short rows count as empty cells. The time column is the first column named
`time` (case-insensitive), otherwise the first column; the choice is
echoed back. Other columns whose name differs from `time` only by case are
ordinary signal columns.

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

If a half-width comes out effectively zero (`< 1e-10`), e.g. `rtoly` alone
on a constant reference (value range 0), it falls back to
`rtol * max|reference value|` on that axis (when `rtol > 0`), and finally
to `1e-10`. For constant or near-constant signals give `atoly` explicitly.

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
the first root. Only local `file://` roots (empty host or `localhost`)
are used; other roots are ignored with a note in the result.

## Development

```bash
make build          # builds the native simtest-funnel module
make test-python    # includes python/simtest-funnel-mcp/tests (incl. stdio end-to-end)
make lint-python    # mypy --strict
uv run simtest-funnel-mcp   # start the server on stdio
```
