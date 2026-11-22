# Tasks

## 1. Rust core

- [x] 1.1 Measure the margin: temporary sweep over half-widths `K ∈ {0, 1, 1.5, 2, 3}` and extra samples `S ∈ {0, 1, 2, 3}` comparing every judged point of random windowed comparisons with the full-range comparison (three regimes, up to 27 515 windows). Verify the table in design.md decision 1 is reproduced and choose `K = 2`, `S = 3`.
- [x] 1.2 In `compare.rs`, build the tube from `extended_indices` (binary search on the monotone reach `x ± 2·h(x)` with `h` = `tube::halfwidth_x_bound`, plus 3 samples; whole side when `2·ltolx > 1` or times are not finite), keep the bases from the window, normalize x by the whole-reference magnitude, and compute deviations only for test points inside `x_range` (0 outside). Verify `cargo test --workspace --features simtest-funnel-core/json`: corpus parity, differential, summary and downsampling corpus tests pass unchanged.
- [x] 1.3 Add `window_property.rs` tests: in-window equivalence property (two regimes), daily-cycle edge case (and that a clipped reference still fails), data start / end, window narrower than the x tolerance, window partly / wholly outside the data, `rtoly` relative to the window, extension size on 2 million samples. Verify `cargo test -p simtest-funnel-core --lib`.
- [x] 1.4 Update rustdoc (`compare` module section "The x-range window", `CompareResult`, `Outputs`, `compare`, `Range`, `Options::x_range`, `Tolerances`) and the core README section "The x-range window". Verify `make test-docs` and reading against the `x-range-window` spec.

## 2. Python

- [x] 2.1 Document the window in the `Range` and `CompareResult` docstrings, the `_simtest_funnel.pyi` stub and the package README. Verify `make lint-python`.
- [x] 2.2 Add `tests/python/test_x_range.py` (edge case, narrow window, data start / end, partly / wholly outside, `rtoly` relative to the window, random in-window equivalence). Verify `uv run python -m pytest tests/python`.

## 3. WASM / TypeScript SDK

- [x] 3.1 Document the window in the TSDoc of `XRange`, `CompareResult` and `createFunnelPlot`, and in the SDK README. Verify `make lint-js`.
- [x] 3.2 Add `packages/sdk/tests/xrange.test.ts` with the same cases. Verify `make test-js`.

## 4. MCP server

- [x] 4.1 Add the X_RANGE paragraph to the `compare_signals` description, update the `x_range` parameter description, the `plot_signals` x_range paragraph and the MCP README; add needles to `test_mcp_server.py`. Verify `uv run python -m pytest python/simtest-funnel-mcp/tests/test_mcp_server.py`.
- [x] 4.2 Add `compare_signals` tests (daily cycle with numeric and ISO bounds, narrow window, data start, partly / wholly outside) and a `plot_signals` test (PASS with 49 points, same row as compare, tube reaching the view edges, drawn tube agrees with the verdict). Verify `uv run python -m pytest python/simtest-funnel-mcp/tests`.

## 5. Documentation and specs

- [x] 5.1 Root README: x-range entry in "Differences from LBNL Funnel". Verify by grepping the repository for `x_range` / `xRange` / `clip` outside tests and archives: no remaining statement that the reference is clipped before the tube is built.
- [x] 5.2 Write the delta specs (`x-range-window` new; `mcp-server`, `mcp-plots` modified). Verify `openspec validate extend-tube-beyond-x-range --strict`.

## 6. Integration

- [x] 6.1 Full gate in the worktree with its own virtualenv (`UV_PROJECT_ENVIRONMENT=<worktree>/.venv`): `make build`, `make lint`, `make test`, `openspec validate extend-tube-beyond-x-range --strict`; confirm no lockfile or version changes in `git status`. Verify all pass.

## Workflow follow-up

- Owner review of the three decisions flagged "not yet confirmed" in design.md (margin, range-relative bases, result arrays).
- Archive the change after review.
