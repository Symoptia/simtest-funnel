# Tasks

## 1. Rust core

- [x] 1.1 Change `Tolerances::DEFAULT` to `rtoly = 2e-3`, all other coefficients zero; update rustdoc of `Tolerances::DEFAULT`, `PartialTolerances` (incl. doctest for x-only and y-only), `Options::default_options()` and the crate docs in `lib.rs`, stating what zero x tolerance means (the `1e-10` floor). Verify `cargo test -p simtest-funnel-core --features json` (doctests included).
- [x] 1.2 Update core unit tests: resolution tests assert the new default (nothing given, only `atoly`), the shared step-edge test asserts fail with defaults / y only and pass with `atolx = 0.002` or `rtolx = 2e-3`, the summary echo test drops `rtolx = 2e-3`. Verify the tests pass.
- [x] 1.3 Make `tests/summary_corpus.rs` and `tests/downsample_corpus.rs` pass the `fail1` case's tolerances (`rtolx = rtoly = 2e-3`) explicitly so the pinned values stay unchanged. Verify `cargo test --workspace --features simtest-funnel-core/json`.
- [x] 1.4 Update the core README (usage comment, Tolerances section with the meaning of zero x tolerance). Verify by reading against the spec.

## 2. CLI

- [x] 2.1 Update the clap doc comment, `long_about` and `--params` help (y default only; an LBNL file without y keys gets `rtoly = 2e-3`, without x keys zero as in LBNL); update the step-edge and `--atoly`-only unit tests and add a default-has-no-x test. Verify `cargo test -p simtest-funnel-cli`.
- [x] 2.2 Update the CLI README (resolution rule, `--params` semantics, "Differences from LBNL Funnel"). Verify by reading against the spec.

## 3. Python

- [x] 3.1 Update `Tolerances`, `default_options` and `compare` docstrings in `__init__.py` and the `_simtest_funnel.pyi` stub. Verify `make lint-python` and `uv run mypy tests/python crates/simtest-funnel-python/python`.
- [x] 3.2 Update pytest: default / `default_options()` / summary echo assert the new values; step-edge test fails by default and with only `atoly`; new test that `atolx = 0.002` (or only `rtolx = 2e-3`) passes; the `fail1` downsampling test passes the case's tolerances explicitly. Verify `uv run python -m pytest tests/python`.
- [x] 3.3 Update the package and crate READMEs (table of effective tolerances, meaning of zero x tolerance). Verify the example `compare_dataframes.py` still runs.

## 4. WASM / TypeScript SDK

- [x] 4.1 Update TSDoc of `Tolerances`, `Options` and `defaultOptions()` (the values come from the core). Verify `make build` regenerates the WASM and `make lint-js` passes.
- [x] 4.2 Update vitest: `DEFAULT` constant, default and `atoly`-only cases fail on the step edge, new explicit-x case passes, `defaultOptions()` checked with exact equality, `fail1` downsampling uses explicit tolerances. Verify `make test-js`.
- [x] 4.3 Update the SDK README (table, meaning of zero x tolerance). Verify by reading against the spec.

## 5. MCP server

- [x] 5.1 Update the `compare_signals` description (per-axis defaults, no time tolerance unless given, what zero x does, prefer `atolx`, the hint), the server instructions and the "omit for the library default" parameter descriptions; update `test_mcp_server.py` needles. Verify `uv run python -m pytest python/simtest-funnel-mcp/tests/test_mcp_server.py`.
- [x] 5.2 Add the no-x-tolerance hint in `run_compare` (FAIL rows from the library with no x coefficient given after overrides; one note per call) and tests: default set on a delayed step fails with the exact note, explicit `atolx` passes without it, explicit `atolx = 0` / x override / all-pass give no note, `plot_signals` forwards it. Verify `uv run python -m pytest python/simtest-funnel-mcp/tests`.
- [x] 5.3 Update the resolved-tolerance test (`rtolx = 0`) and the no-sets test, and the MCP README Tolerances section (default, meaning of zero x, the hint text). Verify `make lint-python`.

## 6. Documentation and specs

- [x] 6.1 Update the root README (quick-start comments, a "Time (x) tolerance" section, "Differences from LBNL Funnel"). Verify by grepping the repository for `2e-3`, `0.002`, `rtolx` and "default tolerance" outside tests, corpora and archives: no remaining statement of the old default.
- [x] 6.2 Write delta specs for `tolerance-resolution`, `mcp-server` and `mcp-plots` (split the two over-long requirements without changing meaning). Verify `openspec validate zero-default-x-tolerance --strict`.

## 7. Integration

- [x] 7.1 Full gate: `make build`, `make lint`, `make test`, `openspec validate zero-default-x-tolerance --strict`; confirm no lockfile or version churn in `git status`. Verify all pass.

## Workflow follow-up

- Archive the change after review; the `mcp-plots` main-spec length warnings disappear then, and `openspec validate --all --strict` no longer reports them.
