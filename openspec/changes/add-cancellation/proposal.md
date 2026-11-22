# Proposal

## Why

A running comparison cannot be stopped. The quadratic `remove_loop` cost
on noisy data has since been fixed (commit 731fd5a, gap buffer), so a
million noisy samples now take about 0.2-0.3 s in a release build. One
input shape is still quadratic: a nearly noise-free signal with a wide
tube in x (many corners per backward loop). Measured in a release build,
sine plus 0.1 % noise, `rtolx = 0.02`:

| samples | time   |
| ------- | ------ |
| 100,000 | 0.21 s |
| 200,000 | 0.65 s |
| 400,000 | 1.8 s  |

With `rtolx = 0.1`, 100,000 samples already take 0.8 s. So cancellation
is a safety net rather than a daily need, but an unlucky input can still
run for minutes, and during that time:

- the Rust `compare` cannot be interrupted;
- the Python binding holds the interpreter lock, so Ctrl-C has no effect
  and no other Python thread runs;
- the MCP server cannot even read its next message, and one slow column
  blocks the whole tool call with no result at all.

## What Changes

- **Rust core**: new functions run a comparison with a cancellation
  signal (a shared flag plus an optional deadline, or a caller-supplied
  check) that is consulted at coarse checkpoints in the long-running
  phases. A cancelled comparison stops promptly and reports that it was
  cancelled, distinctly from every verdict. `compare` / `compare_into`
  are unchanged: same results, bit for bit, and no measurable overhead.
- **Python**: the interpreter lock is released while a comparison runs;
  Ctrl-C interrupts it; `compare` (and `compare_dataframes`) accept a
  time limit and a cancellation token that another thread can trigger.
- **MCP server**:
  - comparisons run off the event loop with the lock released, so the
    server stays responsive; the protocol's cancellation notification
    stops the running comparison;
  - `compare_signals` and `plot_signals` take a time limit, 60 seconds
    per call by default and adjustable per call. On timeout
    `compare_signals` returns the rows already finished and lists the
    comparisons that did not complete instead of failing; `plot_signals`
    (one comparison) fails with a message saying so and writes nothing.
- `summarize` and `downsample_min_max` are linear-time and are not
  changed.

Explicitly out of scope (later, if needed):

- A TypeScript / WASM API for cancellation (polling callback or time
  limit). WebAssembly runs on one thread, so it needs a polled callback;
  the WASM crate and `@simtest-js/funnel` keep their current API.
- Progress reporting (Rust callback, MCP progress notifications).
- Cancellation of CSV reading.
- Making the remaining quadratic case faster.

## Capabilities

### New Capabilities

- `cancellation`: how a running comparison is cancelled or time-limited
  in the Rust core and the Python binding, what a cancelled comparison
  reports, and that calls without a signal are unaffected.

### Modified Capabilities

- `mcp-server`: `compare_signals` gains a time limit with partial
  results; comparisons run off the event loop and honour protocol
  cancellation; rows exist only for completed comparisons.
- `mcp-plots`: `plot_signals` gains the same time limit argument; a
  timed-out plot fails without writing.

## Impact

- `crates/simtest-funnel-core` (new `cancel` module, checkpoints in the
  comparison pipeline), `crates/simtest-funnel-python` (lock release,
  signal polling, token class, stub), `python/simtest-funnel-mcp`
  (async tool wrappers, time limit, partial results, docs).
- Additive API only; the `Status` enum and its codes are unchanged.
  Existing callers see no difference unless they opt in.
- The WASM crate and TypeScript SDK are not changed.
