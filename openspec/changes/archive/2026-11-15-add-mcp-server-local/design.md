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
  `simtest-funnel==<same version as this package>`, `pandas>=2`,
  `numpy>=1.26`. The server relies on library behaviour of the same
  release (`summarize`, `None` tolerances, coverage judged within
  `x_range`), and both packages are released together, so the dependency
  is an exact pin. The release `prepareCmd` rewrites the pin with the
  package version (a second `sed` on `"simtest-funnel==..."`). In the uv
  workspace the library is a workspace source, which uv resolves without
  checking the specifier, so `uv lock` / `uv sync` are unaffected; the pin
  matters for the published wheel metadata (`Requires-Dist:
  simtest-funnel==X`). (The first draft used a `>=1.0.0b11` lower bound,
  which was too low and would go stale.)

### Server structure

- `reader.py`: a self-contained CSV reader (only `csv`, `io`, `warnings`,
  numpy and pandas) that the generated snippet embeds verbatim
  (`inspect.getsource`), so server and snippet read files identically.
  Lines whose first non-blank character is `#` (and blank lines) are
  dropped before parsing (pandas' `comment="#"` would truncate any line at
  a `#`, e.g. a header `time,a#1,b`); the header is split with
  `csv.reader`; the data is parsed by pandas with explicit integer names
  and `index_col=False`, so pandas never turns surplus fields into an
  index (a trailing comma on data rows used to shift every column left).
  pandas drops a single surplus field with a `ParserWarning` and raises
  for more; either makes the reader locate the first offending row with
  `csv.reader` and fail with "data row N (line L) has M fields, header has
  K". A trailing delimiter on every line including the header (which
  worked before, producing a junk `Unnamed` column) is accepted and the
  unnamed all-empty trailing column dropped; any other empty header name is
  an error. Every column is coerced with
  `pandas.to_numeric(errors="coerce")`.
- `csvio.py`: file checks, time column choice, per-column counts of
  non-numeric/empty cells.
- `selection.py`: column selection by exact name or glob pattern
  (`fnmatchcase`), shared by both tools. An entry equal to an existing
  name is exact even if it contains glob characters.
- `compare.py`: build per-(column, set) work, call
  `simtest.funnel.compare_dataframes` once per effective `Options` group on
  frames that contain only the time column (first, under the private key
  `"\0time"`, which no CSV header can contain, so a signal column named
  `time` next to a time column `Time` cannot collide) and the valid
  columns, then `simtest.funnel.summarize` per row.
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
  `MISSING_TEST` / `EMPTY_RANGE`), plus a note giving both spans. Partial
  overlap with a library "missing" status gets a note with the exact
  `x_range` of the overlap. The core judges coverage on both time extents
  clipped to `x_range` (fixed in review: it used to ignore `x_range`, so
  the advice could not work), so that `x_range` turns the rows into
  `pass`/`fail`. Rows with a library `MISSING_*` status keep verdict
  `error` but also carry `points_compared` / `points_outside` and a
  `problem` text naming both time spans and the overlap `x_range`.

### Size limits

- `max_intervals` default 5 per failing row (0 allowed: counts only),
  intervals sorted by `abs(worst_deviation)` descending.
- `max_rows` default 100; rows ordered error, fail, pass (stable within a
  group: column order, then set order), so caps hide passes first. Totals
  always cover all rows; `rows_omitted` states the rest.
- describe_signals lists at most `max_columns` (default 100) columns and
  as many problems, with `columns_total`, `columns_selected`,
  `columns_omitted` and `problems_omitted`; `columns` filters by exact name
  or glob pattern. (The first draft had no cap: ~470 kB for 3000 columns.)
- Measured for 200 columns × 1 set (4 failing): 100 rows ≈ 14.5 kB structured,
  text ≈ 1.5 kB. Value fields (min/max/range, deviations, half-widths,
  fractions) are rounded to 10 significant digits to drop binary noise;
  time/x fields and tolerances are never rounded (epoch-second times need
  all digits: rounding turned 1731628800.25 into 1731628800.0).

### Text rendering

First line: the two files and their time columns. Then one line per
tolerance set with its resolved values, a totals line, one line per error or
failing row (`FAIL z [loose]: 495/1001 points outside (49.5 % of span), worst
+1.533 at t=0.875 (half-width 0.2955); 3 intervals, largest: ...`), one line
per set listing its passing columns, then notes and omissions. Numbers use
4 significant digits except times, which use enough significant digits to
resolve a tenth of the smallest positive time step of the files
(at least 4), so adjacent samples stay distinguishable.

The snippet, when requested, is sent once, in the structured content field
`snippet`; the text rendering only says where it is. Rationale: sending it
in both places doubled the payload (620 kB for 3000 columns). Claude Code,
the primary client (the repository ships `.mcp.json` for it), was observed
during review to hand the model only the structured content of this
server's results, not the text block, so the structured content is the
place an agent actually sees; clients that show only text still get the
verdicts and a pointer, and can retrieve the snippet by reading the
structured result.

### Snippet format

A self-contained pytest module: data paths, time column names, the
server's reader embedded verbatim, a `CASES` list of
`(column, set label, Tolerances(as given), expected Status)` and one
parametrized test that calls `simtest.funnel.compare` with
`Options(tolerances, Range(lo, hi))` and asserts the observed status. Rows
the library did not decide are listed as comments. It asserts the observed
status (not `PASS`) so it reproduces the verdict; a comment explains how to
turn it into a gate.

- Only the rows returned in the result (`max_rows`) become cases; a
  comment states how many were not returned. A hard cap of 64 kB drops
  further cases with a comment saying so.
- Paths: a file under the base directory (first workspace root, else the
  server's working directory) is written relative to it, as
  `DATA_ROOT / "rel/path.csv"` with
  `DATA_ROOT = Path(os.environ.get("SIMTEST_FUNNEL_DATA_ROOT", Path.cwd()))`
  and a comment explaining it, so the snippet works from the same place in
  a CI checkout. Files outside the base keep their absolute path with a
  comment that it will not resolve elsewhere.
- Tolerance coefficients and `x_range` bounds are validated as finite at
  the schema level (`allow_inf_nan=False`; pydantic otherwise accepts the
  strings `"inf"`/`"nan"`), so the snippet never contains a bare `inf`
  and the structured content never contains `-Infinity`; an omitted bound
  becomes `float("-inf")` / `float("inf")` in the snippet.

### Workspace roots

A resolver returns the `ListRoots` marker when the client declared the
roots capability and an empty result otherwise. `file://` roots with an
empty or `localhost` host are converted with `urllib.request.url2pathname`
(so `file:///C:/x` becomes `C:\x` on Windows) and resolved; roots with
another host or scheme are ignored with a note in the result. A path is
accepted when its resolved location is inside one of the roots. With no roots every readable path is accepted.
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
- Release: `.releaserc.json` rewrites the version line and the
  `simtest-funnel==` pin of `python/simtest-funnel-mcp/pyproject.toml`,
  then runs `scripts/release-refresh-lockfiles.sh` (`cargo update
  --workspace` and `uv lock`, which only touch workspace package entries,
  plus a guard that fails if any lockfile line other than a
  `version = "..."` line changed) and commits both lockfiles; the
  `semantic-release` job installs uv with `astral-sh/setup-uv`;
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
