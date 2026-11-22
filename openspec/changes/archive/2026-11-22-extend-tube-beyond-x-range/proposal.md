# Proposal

## Why

`x_range` limits a comparison to a window of x. Today the reference and
the test are clipped to the window first and the tube is built from the
clipped reference. With an x tolerance, the tube at a window edge should
also cover reference values from just outside the window, but those were
clipped away. A test signal that is merely shifted in time by less than
the x tolerance therefore fails in the first or last points of the
window, although the same points pass in a full-range comparison. Seen
in the MCP plot tool: a daily temperature cycle, `atolx = 10800` (±3 h),
a 2-day window: 2 of 49 points fail at the left edge only because of the
clipping.

The owner has decided: **build the tube from the reference extended
beyond the window by the x tolerance on both sides, and judge only test
points inside the window.** In-window verdicts must then match what the
same points get in a full-range comparison, as far as that is well
defined. At the true start and end of the data there is nothing to
extend with, so behaviour there is unchanged.

## What Changes

- **Core (all APIs: Rust, Python, TypeScript/WASM, MCP server; the CLI
  has no x-range option).** With an `x_range`, the tube is built from the
  reference points inside the window plus, on each side, the points whose
  x tolerance reaches the window (twice their x half-width) and three
  more samples. Only test points inside the window are judged, as
  before.
- **Guarantee.** Without range-relative tolerances (`rtolx = rtoly = 0`),
  every test point inside the window gets the same verdict as in the
  full-range comparison; deviations and bounds there are in practice
  bit-identical (only rounding can differ, in a documented corner case).
- **Unchanged by design**: the bases of `rtolx` / `rtoly` (and of the
  constant-reference fallback) are the reference inside the window; the
  coverage statuses `MissingReference` / `MissingTest` and the "at least
  two reference and two test points" rule are judged inside the window;
  without `x_range` every result is bit-identical to today.
- **Result arrays.** With an `x_range`, the bounds cover the window plus
  the extension (so the tube is drawn up to the window edges); the
  deviations keep one entry per test point and are now `0` for test
  points outside `x_range` (previously they were scored against the
  clipped tube's end values, but never judged).
- **Cost.** The extension is found by binary search and adds a few
  samples per side: a small window on a long record stays cheap. The
  deviations are computed only for test points inside `x_range`.
- **Docs**: rustdoc, READMEs (root, core, Python, SDK, MCP), Python
  docstrings and stub, TSDoc (incl. the plotting helper) and the MCP tool
  descriptions describe the window semantics.
- This is a behaviour change of a beta API, made deliberately. Windowed
  comparisons with an x tolerance can now pass where they failed; no
  signature, type or status code changes.

## Capabilities

### New Capabilities

- `x-range-window`: what a comparison with an x-range judges, which
  reference the tube is built from, what stays relative to the window,
  what the result arrays contain, and the equivalence with a full-range
  comparison; identical in every API.

### Modified Capabilities

- `mcp-server`: the optional x-range requirement states that the tube is
  built from the reference beyond the window and that the tool
  description says so.
- `mcp-plots`: the x-range zoom requirement states that the tube is drawn
  up to the edges of the view and that edge points shifted within the x
  tolerance pass.

`violation-summary`, `tolerance-resolution`, `cancellation`,
`signal-downsampling` and `wasm-demo-site` were checked: their
requirements (judged points = x-range intersected with the reference
extent; tolerance resolution; checkpoints; downsampling of given arrays;
the demo) stay true as written, so they are not modified.

## Impact

- Code: `crates/simtest-funnel-core` (`compare.rs`, `tube.rs`, docs in
  `options.rs`), docs in `crates/simtest-funnel-python`,
  `packages/sdk/src/index.ts`, `python/simtest-funnel-mcp` (tool
  descriptions). Bindings pass `x_range` through unchanged.
- Tests: new tests in Rust (property test against the full-range
  comparison, edge cases, extension cost), Python, TypeScript and the MCP
  server (compare and plot). No existing test changes its expected
  values.
- Users: windowed comparisons with an x tolerance may now pass at the
  window edges where they failed; tube bounds returned for a window are
  longer; deviations outside `x_range` are `0`. MCP pytest snippets
  generated earlier assert the old status and may need regenerating if
  they hit the edge case.
