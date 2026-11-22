# Design

## Context

See proposal.md (Why) for the motivation. State before this change:

- The rule lives once in `crates/simtest-funnel-core/src/options.rs`:
  `PartialTolerances::resolve()` fills an axis with no coefficient given
  from `Tolerances::DEFAULT` (`rtolx = rtoly = 2e-3`);
  `Options::default_options()` uses the same constant. Every front end
  (Python native layer, WASM `defaultOptions()` and option parsing, CLI)
  builds a `PartialTolerances` and calls `resolve()`; none hardcodes the
  default values. So the behaviour change is one constant.
- The tube code (`tube.rs`) already handles a zero half-width: if
  `max(atol, rtol*range, ltol*|v|)` is below `1e-10` it falls back to
  `rtol * max|v|` when `rtol > 0`, then to the `1e-10` floor. With all x
  coefficients zero the x half-width is therefore exactly `1e-10`.
- The old default appears verbatim in rustdoc, CLI help, Python
  docstrings and stub, TSDoc, five READMEs, the MCP tool description,
  and in tests in every suite.
- The MCP server already collects free-text `notes` in the
  `compare_signals` result; `plot_signals` reuses `run_compare` and
  forwards its notes.

## Goals / Non-Goals

**Goals:**

- Change the x default to all-zero in every API by changing only
  `Tolerances::DEFAULT`, keeping the "one rule, one place" property.
- Say in every user-facing doc what zero x tolerance means in practice.
- Keep cross-language pinned test values (corpus `fail1`) unchanged.
- Help MCP callers notice a failure that an x tolerance might explain.

**Non-Goals:**

- No change to the per-axis rule, to `PartialTolerances`, to any
  signature or type, to the `1e-10` floor, or to how fully explicit
  tolerances behave.
- No new "previous defaults" switch or compatibility flag.
- No change to the LBNL corpus parity harness (it already maps absent
  keys to explicit `0`).
- No change to the pytest snippet format (it keeps the tolerances "as
  given"; see Risks).
- No version bump and no `BREAKING CHANGE` footer: this is a default
  change on the beta line, described in the proposal and the commit
  message.

## Decisions

1. **Change `Tolerances::DEFAULT` to `{ rtoly: 2e-3, ..ZERO }`.**
   `PartialTolerances::default().resolve()`, `Options::default()`, the
   Python `default_options()`, the SDK `defaultOptions()` and the CLI
   follow automatically. *Alternative:* a separate per-axis default
   table — rejected, the existing constant already is the per-axis
   default.

2. **"Zero x tolerance" is documented as "the x half-width is the
   `1e-10` floor: the tube has no width along x, so each test point is
   checked only against the y band around the reference at the same
   x".** This is what the code does, and it tells the reader the
   practical consequence (a slightly shifted steep edge fails). Docs
   recommend `atolx` in time units over `rtolx`, and give the
   record-length argument (15 days → 43 min, a year → 17.5 h at
   `rtolx = 2e-3`). *Alternative:* raise the floor or special-case zero
   — rejected, out of scope and it would change explicit-zero results.

3. **Tests: keep intent, decide per test.**
   - Tests that assert the default itself (`default_options`,
     `nothing given`, summary echo, CLI `--atoly` only) now assert the
     new values.
   - The shared step-edge test (Rust core, CLI, Python, TypeScript)
     asserts the new behaviour: with defaults or a y-only tolerance the
     delayed edge fails; with an explicit `atolx = 0.002` or
     `rtolx = 2e-3` it passes. This is the behavioural test required by
     the change, present in each layer.
   - Tests that use the corpus case `fail1` with the default options to
     produce cross-language pinned values (summary and downsampling, in
     Rust, Python and TypeScript) now pass the case's own tolerances
     (`rtolx = rtoly = 2e-3`, as in its `param.json`) explicitly, so the
     pinned numbers stay valid and no longer depend on the default.
   - A JS test that checked the default with `toBeCloseTo(2e-3)` (two
     decimals, which also accepts `0`) now uses exact equality.
   - The corners differential test keeps `Tolerances::DEFAULT` among its
     random tolerance kinds; it now covers the zero-x case, while
     `rtolx = r` kinds still cover non-zero x.

4. **MCP hint, implemented.** After all comparisons, `run_compare`
   counts rows that the library judged FAIL and for which no x
   coefficient was given (after per-column overrides). If the count is
   positive, one note is appended:

   > `N failing row(s) had no x (time) tolerance: none was given and the
   > default is 0. If the test may be shifted or delayed in time against
   > the reference (e.g. at steep edges), consider an x tolerance such as
   > atolx (time units)`

   It is cheap (a pass over existing records) and not noisy: never on
   pass or error rows, never when the caller gave any x coefficient
   (including an explicit `atolx = 0`, which is a deliberate choice),
   and at most once per call. `plot_signals` gets it through the notes
   it already forwards. *Alternatives:* a per-row field (rejected: grows
   every failing row and the output schema); analysing whether the
   violations look like a time shift (rejected: costly and heuristic).

5. **Tool description and server instructions** state the default per
   axis ("x: all 0 (NO time tolerance); y: rtoly = 0.002"), what zero x
   tolerance does to shifted edges, prefer `atolx`, and that a failed
   row without an x coefficient gets a note. The parameter descriptions
   for "omit for the library default" name the default. In the spec this
   is a new requirement rather than an edit of "Tool descriptions explain
   tolerances", whose text already covers "the default" and is close to
   the 500-character limit.

6. **`mcp-plots` housekeeping.** The two requirements over 500
   characters are cut to their first behaviour under MODIFIED (keeping
   their headers and all scenarios), and each removed behaviour becomes
   its own ADDED requirement with its own scenarios: "Plot write does
   not trust the checked path", "Output directory re-checked on other
   platforms", "Reported plot path" and "Plot file put in place in one
   step". The text is moved, not reworded in meaning. The main spec's
   warnings disappear when this change is archived.

## Risks / Trade-offs

- [Comparisons that passed only because of the implicit time slack now
  fail after upgrading] → stated in the proposal and to be stated in
  the generated changelog; every doc says how to restore slack
  (`atolx`, or `rtolx = 2e-3` for the old behaviour); the MCP hint
  points agents at it.
- [Committed MCP pytest snippets from older versions that gave no x
  coefficient now assert with the new default and may fail] → accepted
  in beta; the fix is to regenerate the snippet or add the x coefficient.
  Recording resolved values instead of given ones would decouple
  snippets from future default changes, but changes the
  "tolerances as given" requirement and is left for a separate change.
- [Zero x tolerance makes noisy-but-aligned signals stricter only at
  steep edges; smooth signals are almost unaffected] → acceptable; it
  is the documented intent.
- [The hint could be mistaken for a diagnosis] → worded as a
  conditional suggestion ("if the test may be shifted…").

## Migration Plan

Ships with the next beta release; no data migration. Callers who want
the previous behaviour pass `rtolx = 2e-3` explicitly (Rust:
`PartialTolerances { rtolx: Some(2e-3), .. }`; Python:
`Tolerances(rtolx=2e-3)`; TS: `{ rtolx: 2e-3 }`; CLI: `--rtolx 0.002`;
MCP: `"rtolx": 0.002`), preferably an absolute `atolx`. Rollback is a
revert of the change.
