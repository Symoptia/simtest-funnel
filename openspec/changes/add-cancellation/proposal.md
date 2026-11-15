# Proposal

## Why

A comparison of a long, noisy signal can take a long time, and nothing
can stop it once started. Measured on this machine with identical
sampling for reference and test:

| samples | smooth signal | noisy signal |
| ------- | ------------- | ------------ |
| 12,500  | 0.004 s       | 0.05 s       |
| 25,000  | 0.007 s       | 0.16 s       |
| 50,000  | 0.014 s       | 0.61 s       |
| 100,000 | 0.030 s       | 3.0 s        |

For noisy data the time roughly quadruples when the length doubles, so a
million-sample signal would run for minutes. During that time:

- the Rust `compare` cannot be interrupted;
- the Python binding holds the interpreter lock for the whole call, so
  Ctrl-C has no effect and no other Python thread runs;
- the MCP server cannot even read a cancellation request from the
  client, and one slow column blocks the whole tool call with no
  feedback.

An agent that passes a large file therefore hangs its session until the
call finishes or the client gives up.

## What Changes

- **Rust core**: comparison can be given a cancellation signal that is
  checked regularly during the long-running phases. A cancelled
  comparison stops promptly and reports that it was cancelled instead of
  returning a verdict. Calls without a signal behave exactly as today.
- **Python**: the interpreter lock is released while a comparison runs;
  Ctrl-C interrupts it; callers can cancel from another thread and can
  give a time limit.
- **TypeScript SDK**: callers can give a time limit and/or a function
  that is polled to decide whether to continue (WebAssembly runs on a
  single thread, so nothing else can interrupt it).
- **MCP server**:
  - comparisons run off the event loop, so the server stays responsive
    and honours the protocol's cancellation notification;
  - `compare_signals` and `plot_signals` take a time limit, 60 seconds
    per call by default and adjustable per call; on timeout or cancellation the columns already finished
    are returned and the rest are reported as not completed, rather
    than the whole call failing;
  - progress is reported to clients that ask for it.
- `summarize` and `downsample_min_max` are linear-time and are not
  changed.

Explicitly out of scope:

- Making the comparison itself faster. The growth on noisy data points
  at the algorithm (the tube/corner construction); whether it can be
  improved without changing results is a separate investigation
  (`improve-compare-performance`).
- Cancellation of CSV reading.

## Capabilities

### New Capabilities

- `cancellation`: how a running comparison can be cancelled or
  time-limited in Rust, Python, TypeScript and the MCP server, and what
  a cancelled comparison reports.

### Modified Capabilities

<!-- none: `mcp-server` and `mcp-plots` are still unarchived changes;
     their tool arguments gain a time limit, described in this change -->

## Impact

- `crates/simtest-funnel-core` (comparison loops, status/result type),
  `simtest-funnel-python`, `simtest-funnel-wasm`, `packages/sdk`,
  `python/simtest-funnel-mcp`.
- Additive API in all packages; a new "cancelled" outcome that existing
  callers never see unless they opt in.
- Open points for design: how "cancelled" is represented (new status
  code vs. error); granularity of the checks versus their overhead.
