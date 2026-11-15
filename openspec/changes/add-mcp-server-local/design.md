# Design

## Context

See proposal.md for motivation and specs/mcp-server/spec.md for the required
behaviour. Relevant current state:

- `simtest.funnel` (distribution `simtest-funnel`, built by maturin from
  `crates/simtest-funnel-python/`) is a regular package inside the `simtest`
  namespace package. It provides `compare`, `compare_dataframes`,
  `summarize` (violation intervals, worst deviation, resolved tolerances)
  and `Tolerances` with `float | None` fields resolved by the Rust core.
- The repository's Python tooling is uv (workspace in the root
  `pyproject.toml`), pytest under `tests/python/` and `mypy --strict`
  (configured in the root `pyproject.toml`, not yet wired into `make lint`).
  There is no other Python linter.
- The official MCP Python SDK is at version 2.x (`mcp==2.3.0` at the time of
  writing). In 2.x `FastMCP` is renamed `MCPServer`
  (`mcp.server.mcpserver`); tools are plain type-annotated functions,
  `Annotated[CallToolResult, Model]` lets a tool return its own content
  blocks while still publishing an output schema, client roots are obtained
  through a `Resolve(...)` resolver returning the `ListRoots` marker, and
  `mcp.Client` can launch a stdio server from `StdioServerParameters`.
- Library observation: `compare` silently passes a test column containing
  NaN (deviation NaN is not counted as outside) while NaN in a time column is
  reported as `NON_MONOTONIC`. The server therefore has to detect bad cells in
  signal columns itself.

## Goals / Non-Goals

**Goals:**

- A small, dependency-light, pure-Python server that is a thin adapter over
  `simtest.funnel`: CSV loading, argument shaping, result shaping. All
  numerics (comparison, tolerance resolution, interval extraction) come from
  the library.
- Output whose size is bounded independently of the number of samples and
  bounded by caller-adjustable caps in the number of columns.

**Non-Goals:**

- No tolerance defaulting or validation beyond schema checks (non-negative
  floats, known keys); the library decides.
- No caching between calls, no file watching, no writes.
- No pandas-free CSV parser; pandas is already a workspace dependency.

## Decisions

### Package location, names and build backend

- Location `python/simtest-funnel-mcp/` (src layout:
  `src/simtest_funnel_mcp/`, tests in `python/simtest-funnel-mcp/tests/`).
  `crates/` is for Cargo crates and `packages/` / `examples/` are pnpm
  workspace globs, so a new top-level `python/` directory for pure-Python
  distributions avoids confusing either tool.
- Distribution `simtest-funnel-mcp`, console script `simtest-funnel-mcp`
  (also `python -m simtest_funnel_mcp`).
- Import name `simtest_funnel_mcp`, a top-level regular package. Alternatives:
  `simtest.funnel.mcp` is impossible (`simtest.funnel` is a regular package
  owned by another distribution); `simtest.funnel_mcp` / `simtest.mcp` as
  namespace portions would work but put a second distribution into the
  shared `simtest` namespace and invite future collisions. A distinct
  top-level name cannot collide.
- Build backend hatchling (pure Python, static `version = "..."` line that
  the existing semantic-release `sed` can rewrite). `uv_build` was the
  alternative; hatchling is more widely known and does not need the uv
  version pin that `uv_build` requires.
- uv workspace: added to `[tool.uv.workspace].members`, with
  `simtest-funnel-mcp = { workspace = true, editable = true }` in
  `[tool.uv.sources]` and as a root dependency so `uv sync` installs it.
  Inside the package `simtest-funnel` resolves to the workspace member.

### Dependencies

- `mcp>=2.3,<3` (MCPServer API, roots resolver, client used by tests),
  `simtest-funnel>=1.0.0b11,<2` (first version with `summarize` and nullable
  tolerances), `pandas>=2`, `numpy>=1.26`. The version of
  `simtest-funnel-mcp` itself follows the repository version via
  semantic-release; the dependency on `simtest-funnel` is a lower bound
  rather than an exact pin to keep the release `sed` minimal.

### Server structure

- `csvio.py`: load a CSV (`pandas.read_csv(comment="#",
  skipinitialspace=True)`), choose the time column, coerce every column with
  `pandas.to_numeric(errors="coerce")` and record per-column counts of
  non-numeric/empty cells; derive the description.
- `compare.py`: build per-(column, set) work, call
  `simtest.funnel.compare_dataframes` once per effective `Options` group on
  frames that contain only the time column (first) and the valid columns,
  then `simtest.funnel.summarize` per row.
- `models.py`: pydantic models for inputs (with `extra="forbid"`, so a typo
  such as `rtol_y` is an error instead of silently ignored) and outputs (the
  published output schemas).
- `render.py` (text), `snippet.py` (pytest snippet), `server.py`
  (`MCPServer`, tool registration, roots, path resolution), `__main__.py`.

### Tolerance handling

- A tolerance set is passed to `Tolerances(**given)` unchanged; `None` means
  not given. Resolved values for echoing come from the library: for every
  compared row from `summarize(...).tolerances`; for the per-set echo (also
  when every row errored) from `summarize` of a two-point dummy comparison
  with the same `Options`. The server contains no copy of the resolution
  rule.
- No sets means one set labelled `default` with nothing given. Unlabelled
  sets get `set1`, `set2`, ... by position. Duplicate labels are an error.
- Per-column overrides compose axis-wise: if the override gives any of
  `atolx/ltolx/rtolx`, the x axis comes entirely from the override (missing
  coefficients stay "not given"), likewise for y; otherwise the set's
  values for that axis are kept. Alternatives: whole-set replacement (makes
  several sets meaningless for that column) and key-wise merge (an override
  `atoly` combined with the set's `rtoly` would take the max of both, which
  is rarely what "use 0.5 for z" means). The given (composed) values are
  what the snippet uses; affected rows echo their resolved values.

### Result schema (compare_signals)

Top-level fields: `reference` and `test` (`path`, `time_column`,
`time_column_rule` = `"named time"` or `"first column"`, `row_count`,
`time_start`, `time_end`), `x_range` (`lo`/`hi`, `null` = unbounded),
`tolerance_sets` (`label`, `given`, `resolved`), `totals` (`rows`, `pass`,
`fail`, `error`), `rows`, `rows_omitted`, `columns_only_in_reference` /
`columns_only_in_test` (at most 50 names each, with `*_count`), `notes`,
`snippet` (`null` unless requested).

Row fields: `column`, `tolerance_set`, `verdict`, `status`, `status_name`,
`problem`, `tolerances` (resolved; only when a column override applied),
`points_compared`, `points_outside`, `fraction_of_points_outside`,
`fraction_of_span_outside`, `worst` (`x`, `deviation`,
`tube_half_width_y`), `interval_count`, `intervals` (each `start_x`,
`end_x`, `direction`, `point_count`, `worst_deviation`, `worst_x`).
Passing rows carry only `column`, `tolerance_set`, `verdict`, `status`,
`status_name` and `points_compared` (everything else is zero by definition).
Absent values are omitted from the structured content rather than sent as
`null` (keeps 200-column results small); non-finite floats are omitted.

- Verdict: `pass` for status 0, `fail` for -1, `error` otherwise or when the
  server did not run the library for the row.
- Status codes for server-detected column problems: column absent from the
  test file → `MISSING_TEST` (2), absent from the reference →
  `MISSING_REFERENCE` (1), absent from both → `MISSING_REFERENCE`. The
  library's own messages for these codes talk about x-ranges, so `problem`
  carries the server's explanation. Non-numeric/empty cells in a signal
  column and a requested column that is the time column have no library
  code: `status`/`status_name` are omitted, verdict `error`, explained in
  `problem`. For every other non-pass/fail status, `problem` is the library's
  `status_message`.
- Different column sets: default selection is the intersection (in
  reference order); the rest is listed, not compared. Disjoint time ranges:
  passed through to the library (which returns `MISSING_REFERENCE` /
  `MISSING_TEST` / `EMPTY_RANGE`), plus a note giving both spans and
  suggesting an `x_range`. Partial overlap with a library "missing" status
  gets the same note.

### Size limits

- `max_intervals` default 5 per failing row (0 allowed: counts only),
  intervals sorted by `abs(worst_deviation)` descending.
- `max_rows` default 100; rows ordered error, fail, pass (stable within a
  group: column order, then set order), so caps hide passes first. Totals
  always cover all rows; `rows_omitted` states the rest.
- describe_signals lists every column (one compact entry each, ~60 bytes);
  no cap, since the column list is what the agent needs to pick columns.
- Measured for 200 columns × 1 set (4 failing): 100 rows ≈ 14.5 kB structured,
  text ≈ 1.5 kB. Structured floats are rounded to 10 significant digits.

### Text rendering

First line: the two files and their time columns. Then one line per
tolerance set with its resolved values, a totals line, one line per error or
failing row (`FAIL z [loose]: 495/1001 points outside (49.5 % of span), worst
+1.533 at t=0.875 (half-width 0.2955); 3 intervals, largest: ...`), one line
per set listing its passing columns, then notes and omissions. Numbers use
4 significant digits. The snippet, when requested, is appended in a fenced
block (it must be copyable from text-only clients).

### Snippet format

A self-contained pytest module: absolute file paths, time column names,
the same `read_csv` dialect and numeric coercion, a `CASES` list of
`(column, set label, Tolerances(as given), expected Status)` and one
parametrized test that calls `simtest.funnel.compare` with
`Options(tolerances, Range(lo, hi))` and asserts the observed status. Rows
the library did not decide are listed as comments. It asserts the observed
status (not `PASS`) so it reproduces the verdict; a comment explains how to
turn it into a gate.

### Workspace roots

A resolver returns the `ListRoots` marker when the client declared the
roots capability and an empty result otherwise. `file://` roots are
converted to resolved paths; a path is accepted when its resolved location
is inside one of them. With no roots every readable path is accepted.
Relative paths resolve against the first root, else the working directory.
Roots are deprecated in the newest protocol revision (SEP-2577) but still
supported by the SDK and by current clients; when absent the server simply
does not restrict.

### Wiring

- Makefile: `test-python` also runs `python/simtest-funnel-mcp/tests`; new
  `lint-python` (`uv run mypy` on the package source and tests, strict via
  the root config) joins `make lint`.
- Root `pyproject.toml`: workspace member, source, dependency, `testpaths`
  and `mypy_path` entries.
- CI: python job runs the new tests; lint job installs Python and uv
  because `make lint` now includes mypy (run there only, not twice).
- Release: `.releaserc.json` rewrites the version line of
  `python/simtest-funnel-mcp/pyproject.toml` and commits it;
  `publish-pypi` builds the package with `uv build` into `target/wheels/`,
  which the existing `twine upload` already uploads.
- Docs: package README (tools, tolerances, Claude Code / Claude Desktop
  registration), a section in the root README, root `.mcp.json` running
  `uv run --directory . simtest-funnel-mcp`.

### Tests

Unit tests call the tool functions in-process (CSV loading, describe,
compare: pass, fail, multi-column, multi-set, overrides, x-range, problems,
caps, roots); one test writes the snippet to a temporary directory and runs
pytest on it; an end-to-end test starts `python -m simtest_funnel_mcp` as a
subprocess and drives it with `mcp.Client` over stdio (initialize, list
tools, call both tools, roots refusal).

## Risks / Trade-offs

- [The library passes NaN deviations silently] → the server flags bad cells
  before calling it; reported to the maintainers as a library gap.
- [`simtest-funnel` wheels exist only for Linux x86-64 / CPython 3.12] →
  `uvx simtest-funnel-mcp` only works there until `add-cross-platform-wheels`
  lands; documented.
- [MCP SDK 2.x is young and its roots API is deprecated in the newest
  protocol] → pinned `<3`; roots handling is isolated in one resolver and
  falls back to "no restriction".
- [Text and structured content are both sent, roughly doubling the payload]
  → both are bounded by the same caps; text is the compact form.
- [Release wiring cannot be exercised locally] → minimal diff that reuses
  the existing `twine upload target/wheels/*` step; flagged as unverified.
