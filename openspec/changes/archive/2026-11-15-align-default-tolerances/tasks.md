# Tasks

## 1. Rust core

- [x] 1.1 Add `PartialTolerances` (six `Option<f64>`, `Default` = all `None`, `resolve()`, `From<Tolerances>`, serde behind `json`) and `Tolerances::ZERO` / `Tolerances::DEFAULT` in `options.rs`; remove `impl Default for Tolerances`; make `Options::default_options()` use `Tolerances::DEFAULT`; re-export from `lib.rs`; document all items. Verify with unit tests covering every spec scenario of the per-axis rule (`cargo test -p simtest-funnel-core`).
- [x] 1.2 Replace remaining `Tolerances::default()` uses in core unit tests (`tube.rs`, `compare.rs`, `summary.rs`) and `tests/summary_corpus.rs` with `Tolerances::ZERO` / `Tolerances::DEFAULT` keeping their old meaning; add a summary unit test that the echoed tolerances of resolved partial options are the six resolved values. Verify `cargo test --workspace --features simtest-funnel-core/json` passes.
- [x] 1.3 Make `io::ParamFile` tolerance fields `Option<f64>` with `ParamFile::tolerances()`; keep LBNL semantics in `tests/corpus_parity.rs` by mapping absent keys to explicit `0.0`. Verify an io unit test distinguishes absent / `null` / `0` and corpus parity passes unchanged.
- [x] 1.4 Update rustdoc and the core README example (`..Default::default()` no longer compiles) to state the rule. Verify `make test-docs` and `cargo +1.85 check --workspace`.

## 2. CLI

- [x] 2.1 Merge flags over `--params` per coefficient into a `PartialTolerances` and resolve once; update the clap doc comment. Verify with unit tests in `main.rs` for flag-only y, empty param file, and flag+params combined.
- [x] 2.2 Update the CLI README (Usage resolution order, "Differences from LBNL Funnel" default-tolerance note). Verify by reading the rendered text against the spec.

## 3. Python

- [x] 3.1 Native layer: parse the `tolerances` dict into `PartialTolerances` (missing key or `None` = not given) and resolve; build `default_options()` from `Options::default_options()`. Update `_simtest_funnel.pyi` docstrings. Verify `cargo clippy` clean.
- [x] 3.2 Package: `Tolerances` fields `float | None = None`, pass `None` through, document the rule in docstrings; `ViolationSummary.tolerances` holds the resolved six floats. Verify `uv run mypy tests/python crates/simtest-funnel-python/python` is clean.
- [x] 3.3 Tests: add pytest cases for default, only-`atoly`, explicit zero, `None` = absent, `Options()` == no options, `default_options()` round-trip, and summary echo of resolved values; adjust existing tests only to make relied-on zeros explicit. Verify `make test-python`.
- [x] 3.4 Update the Python READMEs (package and crate) and the example to state the rule. Verify examples still run (`uv run python crates/simtest-funnel-python/python/simtest/funnel/examples/compare_dataframes.py`).

## 4. WASM / TypeScript SDK

- [x] 4.1 wasm: input tolerances with `Option<f64>` fields converted to `PartialTolerances` and resolved; `undefined`/`null` options → defaults; `defaultOptions()` built from `Options::default_options()`; summary echoes resolved values. Verify `cargo clippy` clean and `make build` regenerates the wasm.
- [x] 4.2 SDK: `Tolerances` fields `?: number | null`, add `ResolvedTolerances` / `ResolvedOptions` types for `defaultOptions()` and `ViolationSummary`; document the rule in TSDoc. Verify `pnpm lint` and typecheck pass with no `any`.
- [x] 4.3 Tests: add vitest cases mirroring 3.3 (default, only `atoly`, explicit zero, `null` = absent, `defaultOptions()` round-trip, summary echo); adjust existing tests only to make relied-on zeros explicit. Verify `make test-js`.
- [x] 4.4 Update the SDK README and the root README examples / "Differences from LBNL Funnel" note. Verify by reading against the spec.

## 5. Integration

- [x] 5.1 Cross-front-end check: the same trajectories with only `atoly` given resolve to the same six values and the same status in Rust, Python, TS and the CLI (shared step-edge case in each suite plus a CLI run). Verify the four outputs agree.
- [x] 5.2 Full gate: `openspec validate align-default-tolerances --strict`, `make lint`, `make test`, mypy, `cargo +1.85 check --workspace`; revert lockfile-only version-string churn. Verify all pass.
