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
  tube bounds and the violating regions of one comparison (one column,
  one tolerance set):
  - **SVG for documents**: written to a caller-supplied output path;
    resolution-independent and suitable for reports, READMEs and HTML
    pages.
  - **PNG preview for the agent**: a small raster image returned inline
    in the tool result so the model can see the plot. SVG is never
    returned inline, because it reaches the model as text rather than as
    an image.
  - A PNG file can also be written when the output path asks for one.
- Signals are reduced for drawing with the min/max-per-bucket
  downsampling from `add-signal-downsampling`, pinning the worst point
  of every violation interval. The comparison behind the plot always
  runs on the full-resolution data.
- A rendered plot must not contradict the verdict: where the full data
  violates the tube, the plot shows a violation.
- With this tool the server is no longer strictly read-only: it writes
  the requested plot file, and nothing else.

Explicitly out of scope:

- Interactive plots inside the chat (MCP Apps) and Plotly specs for
  claude.ai artifacts — candidates for later changes.
- Plots covering several signals or several tolerance sets at once.

## Capabilities

### New Capabilities

- `mcp-plots`: the MCP server's plot tool — what a comparison plot
  contains, SVG/PNG file output, the inline PNG preview, and the rule
  that a plot agrees with the verdict.

### Modified Capabilities

<!-- none -->

## Impact

- MCP server package: new tool and a plotting dependency (to be chosen
  in design).
- Depends on `add-violation-summary` (violating regions),
  `add-signal-downsampling` (drawing large signals) and
  `add-mcp-server-local` (the server the tool is added to).
