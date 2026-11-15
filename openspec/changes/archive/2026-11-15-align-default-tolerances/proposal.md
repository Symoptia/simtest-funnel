# Proposal

## Why

The documented default tolerance is `rtolx = rtoly = 2e-3` (0.2 % of the
signal's range on both axes), but the APIs disagree on when it applies:

- Rust `Options::default()` uses it, while `Tolerances::default()` is all
  zeros, so `Tolerances { atoly: 0.05, ..Default::default() }` silently
  means "no tolerance in x".
- Python `compare(...)` without options uses it, while `Tolerances()` and
  `Tolerances(atoly=0.05)` are zero everywhere else.
- The TypeScript SDK's `defaultOptions()` reports it, while `compare`
  without options uses all-zero tolerances.
- The CLI fills each missing coefficient individually from the default,
  so `--atoly 0.05` still applies `rtoly = 2e-3` on the same axis.

A caller who specifies only a y tolerance — the most common case, and
the one AI agents will produce through the planned MCP server — gets
zero tolerance along x in most APIs. That makes a tiny time shift on a
steep edge fail, which is exactly the false failure a funnel comparison
exists to avoid. The same inputs must give the same verdict in every
API.

## What Changes

- Define one tolerance-resolution rule, implemented once in the Rust
  core and used by every API:
  - **Default**: `rtolx = rtoly = 2e-3`; all other coefficients zero.
  - **Per axis**: if the caller gives no coefficient for an axis
    (`atol*`, `ltol*`, `rtol*` all absent), that axis gets the default.
    If the caller gives at least one coefficient for an axis, the
    unspecified coefficients on that axis are zero.
  - **An explicit zero counts as given**, so zero tolerance on an axis
    remains expressible.
- **BREAKING** Python: `Tolerances()` and partially specified
  `Tolerances(...)` follow the rule instead of defaulting every
  coefficient to `0.0`.
- **BREAKING** TypeScript SDK: `compare` (and `summarize`) with
  `options` omitted, or with partially specified `tolerances`, follow
  the rule; `defaultOptions()` and actual behaviour agree.
- **BREAKING** CLI: flags and `--params` values are resolved with the
  per-axis rule instead of per-coefficient default filling.
- Rust core: a way to express partially specified tolerances and resolve
  them with the rule; `Tolerances::default()` no longer disagrees with
  `Options::default()`. Fully explicit `Tolerances` values keep their
  exact meaning.
- Results that echo tolerances (the violation summary) always show the
  six resolved values.
- READMEs and API docs state the rule; the "Differences from LBNL
  Funnel" notes are updated.

## Capabilities

### New Capabilities

- `tolerance-resolution`: how default and partially specified
  tolerances are resolved into the six effective coefficients,
  identically in Rust, Python, TypeScript and the CLI.

### Modified Capabilities

<!-- none: `violation-summary` is still an unarchived change; its
     "echo the tolerances used" requirement is unaffected -->

## Impact

- `crates/simtest-funnel-core` (`options.rs`), `simtest-funnel-python`
  (+ `python/simtest/funnel`), `simtest-funnel-wasm`, `packages/sdk`,
  `simtest-funnel-cli`; tests in all suites; READMEs.
- Behaviour change for existing callers that relied on implicit zero
  tolerances; they must now pass explicit zeros. Acceptable while the
  project is in beta, and to be called out in the changelog.
- Builds on the uncommitted `add-violation-summary` work.
- Settles the partial-tolerance question for `add-mcp-server-local`:
  the server passes through whatever the agent specified and relies on
  this rule.
