# Proposal

## Why

`compare` returns a status plus raw arrays (tube bounds and one signed
deviation per test point). A caller that wants to reason about the result
— in particular an AI agent asking "is this signal close enough to the
reference, and if not, how badly and where?" — has to post-process
thousands of numbers itself, and every caller does it slightly
differently. A compact, deterministic summary of *how much the given
tolerances were violated* is the missing building block for the planned
MCP server (`add-mcp-server-local`) and is equally useful in pytest
failure messages.

## What Changes

- Add a violation summary derived from an existing comparison result and
  its inputs. For the tolerances that were actually used it reports:
  - the verdict and the tolerances/x-range echoed back;
  - the violation intervals (start x, end x, direction above/below, worst
    signed deviation and the x at which it occurs);
  - the overall worst deviation, together with the tube half-width at
    that location so the size of the excursion can be put in proportion;
  - the share of the compared span and of the test points that lie
    outside the tube.
- Expose the summary through the Rust core, the Python package
  (`simtest.funnel`) and the TypeScript SDK (`@simtest-js/funnel`) with
  identical numbers in all three.
- No change to the comparison algorithm, to the meaning of the existing
  result fields, or to the CLI output files. Purely additive.

Explicitly out of scope:

- Any tolerance-free "closeness" measure (for example a minimum
  tolerance or scale factor at which the comparison would pass). Whether
  such a number is meaningful for generic signals with varying time
  scales is undecided; it may be explored later as a separate spike.
- Evaluating several tolerance sets in one call — that is a convenience
  of the MCP server, built on repeated use of this summary.

## Capabilities

### New Capabilities

- `violation-summary`: a compact, deterministic description of how a
  comparison violated its tolerances (intervals, worst deviation, share
  outside the tube), available consistently in Rust, Python and
  TypeScript.

### Modified Capabilities

<!-- none: `wasm-demo-site` requirements are unchanged -->

## Impact

- `crates/simtest-funnel-core`: new public summary type and function;
  optional JSON serialisation under the existing `json` feature.
- `crates/simtest-funnel-python` and `python/simtest/funnel`: new typed
  accessor; pytest coverage.
- `crates/simtest-funnel-wasm` and `packages/sdk`: new typed accessor;
  vitest coverage.
- Additive public API in all three published packages (minor release).
- Unblocks `add-mcp-server-local`.
