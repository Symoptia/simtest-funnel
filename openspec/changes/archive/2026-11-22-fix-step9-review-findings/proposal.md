# Proposal

## Why

An independent review of the step-9 line (x-range window, URL sources,
MCP server) found one correctness issue in the core and a set of smaller
issues in the MCP server.

1. **Windowed verdicts could differ from full-range verdicts** with
   absolute tolerances only (about 4–8 windows in 25 000 in the
   reviewer's differential harness). The tube of a window was built from
   the reference extended by a fixed margin (two x half-widths plus three
   samples). The corner algorithm adds no corners inside a collinear run
   of reference points (or a run of points it treats as repeated: with
   epoch-sized x, samples less than ~0.17 s apart), so the tube over the
   window depends on where such a run ends, however far that is. The
   owner's decision stands: the verdict inside a window must match the
   full-range comparison.
2. Every `https` URL with an IP-literal host crashed with an uncaught
   `ValueError`.
3. Fetched content is untrusted text placed in the model's context
   (remote error bodies were quoted), and the documentation did not say
   that without `--allow-host` the host name itself (DNS lookup) can
   carry data out.
4. A pair naming the same column of the same file on both sides passed
   trivially.
5. Non-ASCII digits were accepted in ISO timestamps.
6. Address policy gaps (`fec0::/10`, `5f00::/16`) and an uninterruptible
   `getaddrinfo`.
7. In-flight downloads were not counted in the cache bound; the
   de-duplication set grew without limit.
8. The opt-in download code in generated snippets had no overall
   deadline, followed redirects anywhere, accepted compressed transfer
   encodings and had an exists-then-replace race.
9. A slow, wall-clock-ratio test.
10. Description inconsistencies between the compare and plot tools.
11. Smaller items: gzip bodies with trailing padding, the preamble hint
    for CR-only files, and `test_mcp_examples.py` in the sdist without
    the examples.

## What Changes

- **Core (all APIs).** The extension of a window is grown, starting from
  the former margin, until a check on the corners of the extended
  reference proves that it gives the full-range tube over the window
  (`window.rs`). Without range-relative tolerances every in-window
  deviation is then bit-identical to the full-range one, for any
  `atolx`, `atoly`, `ltolx`, `ltoly`; the documentation states the one
  assumption about the loop-removal heuristic. Results without an
  x-range are unchanged bit for bit.
- **MCP server.** Fixes and documentation for findings 2–11 (see the
  design).

## Impact

- `x-range-window`: extension and guarantee requirements modified.
- `mcp-url-sources`, `mcp-server`, `mcp-plots`: modified as listed in
  the deltas.
- No API or result change without an x-range; no version or release
  configuration change.
