# Tasks

## 1. Rust core

- [x] 1.1 Add `downsample.rs` with documented `Downsampled`, `DownsampleError` (`Display` + `Error`) and `downsample_min_max(x, y, buckets, pinned_x)` per design D1–D7; re-export from `lib.rs`; verify with unit tests covering the two-bucket example (indices 0, 4, 5, 7, 9), pin at 2.2, midway pin, duplicate-x pin, out-of-range/NaN/duplicate pins, ties, NaN y, endpoints kept, empty buckets, zero-span x, small/empty/single-sample input unchanged, all validation errors, the output-size bound and indices matching values (`cargo test -p simtest-funnel-core`)
- [x] 1.2 Add a corpus integration test (fail1): compare + summarize, downsample the test signal to 50 buckets with every interval's `worst_x` pinned, assert every interval keeps a retained sample with non-zero deviation, the size bound holds, compare/summarize results are unchanged, and pin the output length and index checksum shared with the Python and TypeScript tests; verify `cargo test --workspace --features simtest-funnel-core/json` passes
- [x] 1.3 Document the function in the core crate docs / README where the public API is listed; verify `cargo doc -p simtest-funnel-core --no-deps` builds without warnings

## 2. Python binding

- [x] 2.1 Expose native `downsample_min_max` in `crates/simtest-funnel-python/src/lib.rs` (marshal only; errors → `ValueError`, buckets < 1 → same message) and add it to `_simtest_funnel.pyi`; verify `make build` succeeds
- [x] 2.2 Add frozen dataclass `Downsampled` and `downsample_min_max(x, y, buckets, pinned_x=None)` to `simtest/funnel/__init__.py` and `__all__`; document in the package README; verify `uv run mypy tests/python crates/simtest-funnel-python/python` is clean
- [x] 2.3 Add pytest tests (two-bucket example with and without pin, unchanged small input, validation errors incl. negative buckets, fail1 corpus with the same pinned values as Rust); verify `make test-python` passes

## 3. WASM / TypeScript binding

- [x] 3.1 Expose `downsampleMinMax` in `crates/simtest-funnel-wasm/src/lib.rs` (marshal only, typed arrays; non-integer or < 1 buckets → same error message); verify `pnpm run build:wasm` succeeds
- [x] 3.2 Add `Downsampled` interface and `downsampleMinMax(x, y, buckets, pinnedX?)` to `packages/sdk/src/index.ts` without `any`; document in the SDK README; verify `make lint-js` passes
- [x] 3.3 Add vitest tests (two-bucket example with and without pin, unchanged small input, validation errors, fail1 corpus with the same pinned values as Rust/Python); verify `make test-js` passes

## 4. Integration checks

- [x] 4.1 Run `make lint`, `make test`, mypy, `cargo +1.85 check --workspace` and `openspec validate add-signal-downsampling --strict`; verify all pass
