# Proposal

## Why

Signals handed to the library can have hundreds of thousands of samples.
Drawing them as SVG or Plotly traces, or returning them to an AI agent,
at full resolution produces multi-megabyte files and floods the model's
context. Naive thinning (every n-th sample) can drop exactly the spike
that made a comparison fail, so a plot would contradict the verdict. The
planned plot tool of the MCP server (`add-mcp-plots`) and the SDK's
existing `createFunnelPlot` both need a reduction that keeps what
matters.

## What Changes

- Add an output-downsampling function to the Rust core and expose it
  through the Python package and the TypeScript SDK, with identical
  results in all three:
  - **Min/max per bucket**: the x-axis is divided into a requested
    number of buckets and the lowest and highest sample of each bucket
    are kept, in x order. A bucket may contain many violating points;
    they are represented by the bucket's extremes like any other points.
  - **Pinned points**: the caller can pass x-positions that must be
    kept in addition to the bucket extremes. The intended use is the
    worst point of every violation interval from the violation summary
    (at most one extra point per interval), so that a rendered plot
    never hides a violation that the full data contains.
  - First and last samples are always kept; signals already at or below
    the target size are returned unchanged.
- **Post-processing only.** The function is never applied inside
  `compare` or `summarize`; comparisons and violation summaries are
  always computed on full-resolution signals.
- Tube bounds are already a compact corner list and need no
  downsampling.

Explicitly out of scope:

- Other methods (LTTB, tolerance-aware line simplification).
- Rendering plots (`add-mcp-plots`).
- Changing `createFunnelPlot` to downsample by default (may follow once
  the function exists).

## Capabilities

### New Capabilities

- `signal-downsampling`: min/max-per-bucket reduction of a signal for
  output purposes with caller-pinned points, available consistently in
  Rust, Python and TypeScript, and never applied to comparison inputs.

### Modified Capabilities

<!-- none -->

## Impact

- `crates/simtest-funnel-core`: new public function (new module).
- `crates/simtest-funnel-python` and `python/simtest/funnel`: typed
  accessor; pytest coverage.
- `crates/simtest-funnel-wasm` and `packages/sdk`: typed accessor;
  vitest coverage.
- Additive public API in all three published packages.
- Unblocks `add-mcp-plots`.
