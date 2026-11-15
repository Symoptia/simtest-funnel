# Proposal

## Why

A verdict and a violation summary tell an agent *that* and *where* a
signal left the tube; a picture tells it — and the person reading its
report — *what happened there*. The local MCP server
(`add-mcp-server-local`) has no way to show a comparison, and the
existing Plotly helper in the TypeScript SDK only works in a browser.
Agents need a plot they can look at themselves, and people need one that
can be dropped into a document.

## What Changes

- Add a plot tool to the local MCP server that renders reference, test,
  tube bounds and the violating regions of one comparison:
  - **SVG for documents**: written to a caller-supplied output path;
    resolution-independent and suitable for reports, READMEs and HTML
    pages.
  - **PNG preview for the agent**: a small raster image returned inline
    in the tool result so the model can see the plot. SVG is never
    returned inline, because it reaches the model as text rather than as
    an image.
  - A PNG file can also be written when the output path asks for one.
- Add output downsampling to the Rust core and expose it through the
  Python and TypeScript bindings:
  - **Post-processing only.** Comparisons and violation summaries are
    always computed on the full-resolution signals; downsampling is
    applied solely to what is drawn or handed back.
  - **Min/max per bucket**: the x-axis is divided into buckets and the
    lowest and highest sample of each bucket are kept. A bucket may
    contain many violating points; they are represented by the bucket's
    extremes like any other points.
  - A rendered plot must not contradict the verdict: where the full data
    violates the tube, the plot shows a violation. Min/max keeps a
    bucket's extremes in y, which on a steep stretch need not include
    the point that leaves the tube, so the worst point of every
    violation interval is kept in addition to the bucket extremes (at
    most one extra point per interval).
  - Tube bounds are already a compact corner list and are not
    downsampled.
- The SDK's `createFunnelPlot` may use the same downsampling for large
  signals.

Explicitly out of scope:

- Interactive plots inside the chat (MCP Apps) and Plotly specs for
  claude.ai artifacts — candidates for later changes.
- Other downsampling methods (LTTB, tolerance-aware line simplification).
- Plots covering several signals or several tolerance sets at once.

## Capabilities

### New Capabilities

- `signal-downsampling`: min/max-per-bucket reduction of a signal for
  output purposes, available consistently in Rust, Python and
  TypeScript, and never applied to comparison inputs.
- `mcp-plots`: the MCP server's plot tool — what a comparison plot
  contains, SVG/PNG file output, the inline PNG preview, and the rule
  that a plot agrees with the verdict.

### Modified Capabilities

<!-- none -->

## Impact

- `crates/simtest-funnel-core`: new downsampling function; bindings in
  `simtest-funnel-python`, `simtest-funnel-wasm` and `packages/sdk`.
- MCP server package: new tool and a plotting dependency (to be chosen
  in design).
- Depends on `add-violation-summary` (violating regions) and
  `add-mcp-server-local` (the server the tool is added to).
