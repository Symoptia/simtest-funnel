# Design

## Context

See proposal.md for motivation and the specs for the required behaviour.
Relevant current state:

- `compare::compare` runs validation, x-range filtering, tube half-widths
  (`tube.rs`), corner enumeration and `remove_loop` (`corners.rs`), error
  interpolation (`errors.rs`) and status classification. Everything is
  linear except `remove_loop_gap`: with a wide x tolerance on a nearly
  noise-free signal each backward loop spans thousands of corners, and the
  backward/forward scans per loop make it quadratic (100k samples with
  `rtolx = 0.1`: 0.8 s release; 400k: 6.8 s).
- `Status` is a `#[repr(i32)]` enum without `#[non_exhaustive]`, matched
  exhaustively in the Python and WASM bindings and by downstream crates.
- The Python binding (`pyo3` 0.30, `numpy` 0.30) holds the GIL for the whole
  call (no `py.detach`).
- The MCP server (`mcp` 2.3, `MCPServer`) registers sync tool functions. The
  SDK already runs sync tools in a worker thread
  (`anyio.to_thread.run_sync`), but since the comparison held the GIL the
  event loop still froze. On `notifications/cancelled` the SDK cancels the
  handler's cancel scope ("interrupt" mode); a plain `run_sync` defers that
  until the thread returns.

## Goals / Non-Goals

**Goals:**

- Zero behaviour change and no measurable cost for `compare` /
  `compare_into` and for calls that never cancel.
- Prompt stop (milliseconds) regardless of input shape and size, including
  the quadratic case: the work done after the signal fires is bounded
  independently of the input length (only validation precedes the first
  check).
- Ctrl-C works in Python without any extra thread per call.

**Non-Goals:**

- No cancellation in `compare_into`, `summarize`, `downsample_min_max`, the
  CLI or the WASM/TypeScript API (see proposal, out of scope).
- No partial bounds from a cancelled comparison.

## Decisions

### Cancelled is an `Err`, not a `Status`

New functions return `Result<CompareResult, Cancelled>`, with
`enum Cancelled { Requested, DeadlineExceeded }` implementing
`std::error::Error`.

- A new `Status` variant would break every exhaustive `match` downstream
  (`Status` is not `#[non_exhaustive]`), i.e. a semver-major change on the
  1.0.0 line, and would give status code tables in three languages a code
  that only some entry points can return.
- Cancellation says nothing about the data; a `CompareResult` with empty
  bounds and a "cancelled" status could be mistaken for a verdict or fed to
  `summarize`. A `Result` cannot be.
- Validation comes first: invalid input still returns `Ok` with its status
  even if the signal already fired. The status is cheap, deterministic and
  more useful than "cancelled".

### Signal: `CancelToken` plus a generic check

- `CancelToken { flag: Arc<AtomicBool>, deadline: Option<Instant> }`:
  `cancel()` from any thread (clones share the flag), builder methods
  `with_deadline` / `with_timeout` (earlier deadline wins; an
  unrepresentable timeout means no deadline), `check()`.
  `compare_cancellable(.., &CancelToken)`.
- `compare_with_check(.., FnMut() -> Result<(), Cancelled>)` for callers that
  need to poll something else, e.g. Python signals. The token is the common
  case; the closure keeps the core free of any binding concern.
- `compare` calls the same generic pipeline with a closure that always
  returns `Ok`; after monomorphization the checks reduce to a counter.
  Alternative considered: a `&dyn` trait object everywhere (simpler types,
  one indirect call per checkpoint); the generic version costs nothing at
  the call sites and keeps the plain path as fast as possible.
- `Relaxed` ordering suffices: the flag carries no data, only "stop soon".

### Checkpoint placement and granularity

- Phase boundaries: before any work (an already fired signal does no work),
  after the half-widths, after each corner curve, after each `remove_loop`.
- Linear phases: every loop whose length grows with the input (range and
  magnitude, half-widths, normalized copies, corner enumeration,
  denormalization, interpolation of both bounds, deviations, the fail scan
  of the classification) runs over consecutive chunks of `CHECK_INTERVAL`
  (2^15) elements via `Checkpoint::chunks`, which ticks the chunk length
  after each; corner enumeration ticks 1 per reference point. Loop bodies,
  their order and the carried state (running min/max, interpolation
  cursor) are unchanged, so results are bit-identical; the cost is one
  counter update and branch per chunk (per point in corner enumeration).
- x-range restriction: both time arrays are validated non-decreasing and
  NaN-free before it, so the points inside `x_range` are a contiguous
  slice found by two binary searches (`range_indices`, NaN bounds select
  nothing as the former filter did). This replaces the former
  element-by-element filter and its two copies, which ran before the first
  check; a unit test checks it selects exactly what the filter selected.
- Validation (`is_non_decreasing` on both time arrays) stays before the
  first check: invalid input must report its status even when the signal
  has fired, so it cannot be interrupted.
- Inside `remove_loop_gap` a work counter (`Checkpoint::tick`) adds 1 per
  outer iteration plus `k_max - i` per loop removal (the span the scans and
  edits touch), and calls the check every 2^15 units. Counting work rather
  than iterations keeps the interval bounded when single loops span
  thousands of points (wide x tolerance), where a check per N iterations
  would be far too coarse.
- Measured (release, 2-core shared machine, `compare_with_check` with a
  clock-reading check; two runs each):

  | case | checks | before first | max between | after last | 50 ms deadline returns after |
  | ---- | ------ | ------------ | ----------- | ---------- | ---------------------------- |
  | 1M samples, 10 % noise, default tolerances | 1,407 | 1.4-2.0 ms | 1.3-3.8 ms | < 0.1 ms | 52-54 ms |
  | 10M samples, 10 % noise, default tolerances | 31,334 | 16 ms | 5.7-6.6 ms | 5-6 ms | 51-52 ms |
  | 100k samples, 0.1 % noise, `rtolx = 0.1` | 7,631 | 0.1 ms | 0.5-0.7 ms | < 0.1 ms | 50 ms |
  | 400k samples, 0.1 % noise, `rtolx = 0.1` | 55,987 | 0.5 ms | 4.7-10.8 ms | < 0.1 ms | 51 ms |

  "Before first" is validation; "after last" is freeing the working
  buffers. Before the linear phases had checkpoints, the 10M case had
  checks up to 340 ms apart, 220 ms before the first and 245 ms after the
  last, and a 50 ms deadline returned after 145 ms.
- Python adds the copy of the four input arrays before the comparison
  starts (about 50 ms for 10M samples), which the limit cannot interrupt
  but which counts against `timeout`.
- `remove_loop_gap` returns early on cancellation; the `GapPolyline` drop
  closes the gap, and the half-built curves are discarded.

### Measured overhead

Interleaved runs of benches built against HEAD, against this change before
the linear-phase checkpoints were added ("before"), and against this
change; minimum over 8 rounds of 3 runs each (sine on `[0, 10]`, identical
reference and test grids, release build, 2-core shared machine):

| case | HEAD | before: `compare` / `compare_cancellable` | now: `compare` / `compare_cancellable` |
| ---- | ---- | ----------------------------------------- | -------------------------------------- |
| 1M samples, 10 % noise, default tolerances | 0.199 s | 0.204 s / 0.205 s | 0.199 s / 0.198 s |
| 100k samples, 0.1 % noise, `rtolx = 0.1` | 0.789 s | 0.814 s / 0.822 s | 0.810 s / 0.827 s |
| 200k samples, 5 % noise, `x_range = [2.5, 7.25]` | 12.3 ms | 12.1 ms / 13.1 ms | 12.1 ms / 11.9 ms |

The linear-phase checkpoints cost nothing measurable (now vs. before is
within +-1 %, and the x-range restriction as a slice saves two copies). In
the quadratic case both versions of this change are 3-4 % slower than
HEAD in the minimum, which comes from the earlier `remove_loop` work
counter and is below the spread of the minima across rounds on this
machine (about 10-15 %). Output hashes of bounds and deviations are
identical between HEAD and every new path, and Rust tests assert bit
identity between `compare`, `compare_cancellable` and `compare_with_check`.

### Python: lock released, signals polled from the check

- `_ext.compare(.., options=None, *, timeout=None, cancel=None)` copies the
  four input arrays into `Vec`s, then runs `compare_with_check` inside
  `py.detach` (GIL released). Copying keeps the call sound if another
  Python thread writes to the arrays while the lock is released; it is
  linear and small next to the comparison (the core copies the inputs once
  more when filtering anyway).
- The check closure: token check (flag + deadline), then, only when the call
  runs in Python's main thread and at least 50 ms have passed since the last
  poll, `Python::attach(|py| py.check_signals())`. An error (normally
  `KeyboardInterrupt`) is stored and the closure returns
  `Err(Requested)`; after `detach` returns, the stored `PyErr` is raised.
  Signal handlers only run in the main thread, so other threads never
  re-acquire the lock and pay nothing.
  - Alternative considered: run the comparison in a spawned thread and poll
    signals from the caller. Costs a thread per call (tens of microseconds,
    noticeable for the MCP server's many small comparisons) and needs a
    channel; the in-thread poll needs neither.
- `CancelToken` is a `#[pyclass(frozen)]` wrapping the core token:
  `cancel()`, `cancelled`. The per-call `timeout` becomes a deadline on a
  clone of the token (or a fresh one), measured from the call's start.
- Exceptions created in the extension: `ComparisonCancelled(Exception)` and
  `ComparisonTimeout(ComparisonCancelled)`, re-exported by `simtest.funnel`.
  A negative or non-finite timeout raises `ValueError`.
- `compare_dataframes(.., timeout=None, cancel=None)` applies one deadline
  to the whole call (all columns).

### MCP: async tools, one token per call, deadline per call

- The three tool functions stay thin; `compare_signals` and `plot_signals`
  become `async` and run their existing `*_impl` in
  `anyio.to_thread.run_sync(.., abandon_on_cancel=True)` with a fresh
  `CancelToken`. On cancellation (the SDK cancels the handler scope on
  `notifications/cancelled`) the `except` handler calls `token.cancel()` and
  re-raises; the worker thread stops at its next checkpoint and its result
  is dropped. This is a handful of lines, so protocol cancellation is in
  scope. `describe_signals` (no comparison) is unchanged.
- `time_limit` (seconds, `gt=0`, finite, default 60) becomes a
  `TimeLimit` (deadline from `time.monotonic()` plus the call's token)
  at the start of the call, before the files are read. `run_compare` and
  `prepare_plot` take `limit: TimeLimit | None`; before each library
  comparison `run_compare` passes the remaining time as `timeout` together
  with the token. A comparison
  that times out, and every later one, is recorded as not completed; a
  cancelled token raises out of `run_compare` (the call is being abandoned
  anyway).
- `run_compare` therefore calls `funnel.compare` per column instead of
  `compare_dataframes` (which built the same arrays and called `compare`
  per column), so finished columns survive a timeout.
- Result shape (additive; absent when everything completed, so existing
  results are byte-identical): `time_limit_reached: true`,
  `totals.not_completed: int`, `not_completed: [{column, tolerance_set}]`
  capped at `max_rows` with `not_completed_omitted`, and a note. Rows,
  totals per verdict and the snippet cover completed comparisons only.
  Alternative considered: a fourth verdict `not_completed` in the rows; it
  would change the meaning of `verdict` for every consumer and mix
  unanswered questions with answers in the row ordering and totals.
- `plot_signals` is one comparison: a timeout raises a `ToolError` ("did
  not finish within the time limit of N s; no file was written ...") from
  `prepare_plot`, before any rendering or writing.
- `plot_signals` time limit covers rendering. The abandoned worker of a
  cancelled call keeps running after the comparison (rendering is not
  interruptible), so the token and the deadline are checked before
  rendering the preview, before rendering the file and immediately before
  the file is published. Alternative considered: the limit covers the
  comparison only and only cancellation is checked; it would let a call
  write its file well after its limit, with no simpler code. Rendering is
  bounded by the drawing reduction (well under a second), so a call can
  overrun its limit by at most about one rendering.
- Publishing a plot file: rendered bytes go to a temporary file
  (`.<name>.<random>.tmp`, `O_EXCL | O_NOFOLLOW`) in the target directory;
  under a `PublishGate` (a lock) the worker checks the call is still live
  and then moves the file into place: `os.replace` with `overwrite`,
  otherwise `os.link` (fails if the name exists; on file systems without
  hard links an exclusive create of the name). `run_off_loop` cancels the
  token while holding the same gate, so the file either appears before the
  call is reported cancelled or never. The temporary file is always
  removed.
- Output path TOCTOU: `resolve_output_path` checks the path before the
  files are read, up to a minute before the write. The write therefore
  works relative to a directory descriptor opened with `O_DIRECTORY |
  O_NOFOLLOW` and verified, immediately before publishing, to lie inside
  the allowed directories: its current path (`F_GETPATH` on macOS,
  `/proc/self/fd` on Linux, else `realpath`) must be inside a root and
  have the descriptor's device and inode. A swapped-in symlink at the file
  name is replaced by `rename`, never followed. Where `dir_fd` is not
  supported (Windows) the directory is resolved and checked again right
  before publishing, which narrows the window but cannot close it. The
  reported `file.path` is the verified location.

## Risks / Trade-offs

- [Deadline on `wasm32-unknown-unknown` panics in `Instant::now`] → only
  the new API reads the clock, the WASM crate does not use it, and the
  module docs say to use the flag only there.
- [Main-thread signal poll re-acquires the GIL every 50 ms] → at most a few
  ms per poll if other threads hold the lock (the switch interval); only
  in the main thread; no cost otherwise.
- [Input copy in Python] → linear, a few percent for 1M samples; buys
  soundness while the lock is released.
- [Abandoned MCP worker keeps running until its next checkpoint] →
  milliseconds; the token is cancelled before the handler re-raises.
- [Reading the CSV files and rendering a plot are not interrupted] → both
  count against the limit (the deadline starts with the call) and the
  descriptions say so; reading is out of scope, rendering is bounded by the
  drawing reduction and checked before and after.
- [Gate held by the event loop while cancelling] → the worker holds it only
  for the liveness check and one `rename`/`link`, so the event loop waits
  at most a few system calls.
- [Partial results depend on timing] → tests use a slow column that cannot
  finish within the limit in any build and a constant column that finishes
  in milliseconds, or an already expired deadline. The stdio test waits for
  a marker the probed server writes when the slow comparison starts
  instead of sleeping, and its limit leaves room for reading the files on
  a machine several times slower.

## Migration Plan

Additive only. Rust: new items `cancel`, `CancelToken`, `Cancelled`,
`compare_cancellable`, `compare_with_check`. Python: new keyword-only
arguments, `CancelToken`, two exception classes; `compare` now releases the
GIL (callers relying on the GIL for exclusion during `compare` were never
promised it). MCP: new optional argument and result fields. Rollback is a
revert.
