# Tasks

## 1. Rust core

- [x] 1.1 Add the `cancel` module (`CancelToken` with shared flag, `with_deadline` / `with_timeout` / `cancel` / `is_cancelled` / `check`; `Cancelled { Requested, DeadlineExceeded }` implementing `Error`; internal work-counting `Checkpoint`) and verify its unit tests (shared flag, past deadline, earlier deadline wins, huge timeout, checkpoint interval)
- [x] 1.2 Route `compare` through a generic pipeline with checkpoints at the phase boundaries and the work counter in `remove_loop_gap`; add `compare_cancellable` and `compare_with_check`; verify the existing unit, differential and corpus tests pass unchanged
- [x] 1.3 Add `tests/cancellation.rs` (bit-identical results with an unfired token and check, expired deadline and cancelled token do no work, 50 ms deadline and cross-thread cancel stop the 100k wide-tube case within 500 ms, check error propagates, validation precedes cancellation) and verify `cargo test -p simtest-funnel-core` passes
- [x] 1.4 Measure overhead (interleaved HEAD vs. new, plain and token paths) and check spacing, verify output hashes are identical, and record the numbers in design.md
- [x] 1.5 Document cancellation in the crate docs (`lib.rs`, `cancel` module) and `crates/simtest-funnel-core/README.md`, and verify `cargo doc` and the doc test build

## 2. Python binding

- [x] 2.1 Release the GIL in `_ext.compare` (inputs copied, `py.detach`), add keyword-only `timeout` / `cancel`, the `CancelToken` pyclass, the `ComparisonCancelled` / `ComparisonTimeout` exceptions and the main-thread signal poll; verify `cargo clippy` is clean
- [x] 2.2 Expose `CancelToken`, the exceptions and the new arguments of `compare` / `compare_dataframes` in `simtest/funnel/__init__.py` and the `.pyi` stub, and verify `mypy --strict` passes
- [x] 2.3 Add pytest tests: timeout raises `ComparisonTimeout` promptly, cross-thread cancel and pre-cancelled token raise `ComparisonCancelled`, a second Python thread makes progress during a comparison, generous limit gives an identical result, invalid timeout raises `ValueError`, `compare_dataframes` honours the limit, and SIGINT in a subprocess raises `KeyboardInterrupt` promptly; verify `pytest tests/python` passes
- [x] 2.4 Document the new arguments and Ctrl-C behaviour in `crates/simtest-funnel-python/README.md` and verify the example runs

## 3. MCP server

- [x] 3.1 Thread a `TimeLimit` (deadline + call token) through `run_compare` (per-column `funnel.compare`, not-completed records, `time_limit_reached`, `totals.not_completed`, `not_completed` list capped at `max_rows`, note) and `prepare_plot` (timeout raises a plot argument error, nothing written); add the result fields to the models and the text rendering; verify existing compare, plot and snippet tests pass unchanged
- [x] 3.2 Make `compare_signals` / `plot_signals` async, running the impl in a worker thread with `abandon_on_cancel=True` and cancelling the token when the call is cancelled; add `time_limit` (default 60, positive, finite) to both tools; verify the tool schemas list `time_limit`
- [x] 3.3 Add tests: tiny time limit yields the fast column's row plus a not-completed entry (and a snippet of only completed rows), timed-out plot raises without writing, invalid `time_limit` is rejected, a cancelled async call cancels the token, the stdio server answers `tools/list` while a slow comparison runs; verify `make test-python` passes
- [x] 3.4 Update the tool descriptions, server instructions and `python/simtest-funnel-mcp/README.md` (time limit, partial results, cancellation), and verify the described fields match the output schema

## 4. Integration checks

- [x] 4.1 Verify the WASM crate and `packages/sdk` build and pass their tests with unchanged public API (no diff under `crates/simtest-funnel-wasm` or `packages/sdk`)
- [x] 4.2 Run `make build`, `make lint`, `make test` and `openspec validate add-cancellation --strict` and verify all pass

## 5. Review follow-up

- [x] 5.1 `plot_signals`: check token and deadline before rendering and immediately before publishing; write to a temporary file and publish by `os.replace` / `os.link` under a gate shared with `run_off_loop`; tests for a call cancelled while rendering, cancellation or deadline during file rendering, and cancellation before rendering
- [x] 5.2 Write plot files relative to a verified `O_DIRECTORY | O_NOFOLLOW` directory descriptor (re-resolve and check on platforms without `dir_fd`); tests for a directory or parent swapped for a symlink, a final-component symlink with `overwrite`, a file created meanwhile, and file systems without hard links, in both write modes
- [x] 5.3 Checkpoints in the linear phases (`Checkpoint::chunks`, corner enumeration ticks) and the x-range restriction as a slice; verify bit-identical output hashes against HEAD, re-measure spacing and overhead (design.md), add tests for per-chunk checks and the range selection; reword the latency claims in the specs, READMEs and docstrings
- [x] 5.4 `compare_dataframes` timeout message names the caller's limit; test
- [x] 5.5 Declare `anyio>=4.1` and `pillow>=9` in the MCP package and refresh `uv.lock`
- [x] 5.6 `GapPolyline` model test (random insert/delete/append, regrowth, drop); CI runs `cargo test` with the core's `json` feature like `make test-rust`
- [x] 5.7 Stdio time-limit test waits for the slow comparison to start (probed server) with limits robust to a slower machine; smaller files for the in-process tests
- [x] 5.8 Align the `time_limit` field and tool descriptions, README and specs: a deadline for the whole call including reading (and rendering for plots)

## Workflow follow-up

- Archive the change after review.
