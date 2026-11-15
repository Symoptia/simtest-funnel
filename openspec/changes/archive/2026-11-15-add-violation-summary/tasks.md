# Tasks

## 1. Rust core

- [x] 1.1 Promote the clamped interpolation helper in `errors.rs` to `pub(crate)` without behaviour change; verify `cargo test -p simtest-funnel-core` still passes
- [x] 1.2 Add `summary.rs` with documented `ViolationSummary`, `ViolationInterval`, `WorstDeviation`, `Direction` and `summarize(result, t_ref, opts)` per design D1–D8; re-export from `lib.rs`; verify with unit tests covering one excursion, sign flip, boundary single-point violation, ignored out-of-range deviations, tie-break, tube half-width, span/point shares (incl. zero-length range), PASS, and validation statuses
- [x] 1.3 Add `Serialize` (under the `json` feature) for the summary types plus `Status`, `Tolerances`, `Range` per D9; verify with a `json`-feature unit test asserting `"status":"Fail"`, `"direction":"above"` and `null` for an unbounded x-range
- [x] 1.4 Add a corpus-based integration test (fail1) asserting the summary is consistent with the result (status FAIL, ≥1 interval, worst equals max |error| in range); verify `cargo test --workspace --features simtest-funnel-core/json` passes

## 2. Python binding

- [x] 2.1 Expose native `summarize` in `crates/simtest-funnel-python/src/lib.rs` (marshal only) and add it to `_simtest_funnel.pyi`; verify `make build` succeeds
- [x] 2.2 Add typed `ViolationSummary`, `ViolationInterval`, `WorstDeviation` dataclasses and `summarize(result, t_reference, options=None)` to `simtest/funnel/__init__.py` and `__all__`; document in the package README; verify `uv run mypy tests/python crates/simtest-funnel-python/python` is clean
- [x] 2.3 Add pytest tests (synthetic excursion, PASS, validation status, fail1 corpus with values matching the Rust test); verify `make test-python` passes

## 3. WASM / TypeScript binding

- [x] 3.1 Expose `summarize` in `crates/simtest-funnel-wasm/src/lib.rs` (marshal only, camelCase); verify `pnpm run build:wasm` succeeds
- [x] 3.2 Add `ViolationSummary`, `ViolationInterval`, `WorstDeviation` interfaces and `summarize(result, referenceX, options?)` to `packages/sdk/src/index.ts` without `any` in public types; document in the SDK README; verify `make lint-js` passes
- [x] 3.3 Add vitest tests (synthetic excursion, PASS, validation status, fail1 corpus with values matching the Rust/Python tests); verify `make test-js` passes

## 4. Integration checks

- [x] 4.1 Run `make lint`, `make test`, mypy, `cargo +1.85 check --workspace` and `openspec validate add-violation-summary`; verify all pass
