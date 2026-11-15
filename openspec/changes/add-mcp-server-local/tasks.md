# Tasks

## 1. Package scaffolding

- [x] 1.1 Create `python/simtest-funnel-mcp/` (hatchling `pyproject.toml`, `src/simtest_funnel_mcp/` with `__init__.py`, `__main__.py`, `py.typed`, console script `simtest-funnel-mcp`) and verify `uv sync` installs it
- [x] 1.2 Add the package to the root `pyproject.toml` (workspace member, source, dependency, pytest `testpaths`, mypy `mypy_path`) and verify `uv run python -c "import simtest_funnel_mcp"` succeeds and `uv.lock` contains `mcp` 2.x

## 2. CSV loading and describe_signals

- [x] 2.1 Implement CSV loading (dialect, time column rule, numeric coercion with per-column bad-cell counts, unreadable-file errors) and verify with unit tests in `tests/test_mcp_csv.py`
- [x] 2.2 Implement `describe_signals` (time span, sampling statistics, per-column min/max/range, problems) with output models and text rendering, and verify with unit tests on the demo CSV and on files with problems

## 3. compare_signals

- [x] 3.1 Implement input models (tolerance sets with `extra="forbid"`, labels, per-column overrides composed per axis, x-range, caps) and verify label/unknown-key errors in unit tests
- [x] 3.2 Implement the comparison (column selection, `compare_dataframes` + `summarize`, library-resolved tolerances echoed, per-column problems with status codes, notes for disjoint ranges) and verify pass, fail, multi-column, multi-set, override, x-range and problem cases in `tests/test_mcp_compare.py`
- [x] 3.3 Implement row ordering and caps (`max_rows`, `max_intervals`, worst first, totals and omitted counts) and the text rendering, and verify capping with a 200-column test
- [x] 3.4 Implement the opt-in pytest snippet and verify in a test that running it with pytest reproduces the observed statuses

## 4. MCP server

- [x] 4.1 Register both tools on `MCPServer` with read-only annotations, descriptions explaining the six coefficients, structured output schemas and text content; honour client roots and resolve relative paths; verify with in-process unit tests (roots accepted/refused)
- [x] 4.2 Add an end-to-end test that launches the server over stdio with `mcp.Client` (initialize, list tools, call both tools on the demo CSVs, roots refusal) and verify it passes

## 5. Wiring and docs

- [x] 5.1 Makefile: run the package tests in `test-python`, add `lint-python` (mypy --strict on package and tests) to `lint`; verify `make lint` and `make test` pass
- [x] 5.2 CI (`.github/workflows/ci.yml`): run the package tests in the python job, install Python and uv in the lint job (whose `make lint` now runs mypy); verify YAML parses
- [x] 5.3 Release: version sync in `.releaserc.json` and `uv build` of the package in the `publish-pypi` job; verify JSON/YAML parse and that the `sed` rewrites exactly one line of the package `pyproject.toml`
- [x] 5.4 Docs: package README (tools, tolerances, Claude Code and Claude Desktop registration), root README section, root `.mcp.json`; verify the `.mcp.json` command starts the server (e2e initialize via that command line)

## 6. Integration checks

- [x] 6.1 Run `openspec validate add-mcp-server-local --strict`, `make lint`, `make test` and mypy on the package; all pass
