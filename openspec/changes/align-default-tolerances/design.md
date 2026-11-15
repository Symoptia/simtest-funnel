# Design

## Context

See proposal.md (Why) for the inconsistencies. Observed in the working
tree before this change:

- `crates/simtest-funnel-core/src/options.rs`: `Tolerances` holds six
  `f64`; `impl Default for Tolerances` is all-zero;
  `Options::default_options()` sets `rtolx = rtoly = 2e-3`.
- Python native layer (`simtest-funnel-python/src/lib.rs`):
  `options=None` → `Options::default_options()`; a `tolerances` dict
  starts from `Tolerances::default()` (zero) and fills given keys. The
  Python dataclass `Tolerances` defaults every field to `0.0`, so
  `Options()` and `Tolerances(atoly=…)` send six explicit values.
- wasm (`simtest-funnel-wasm/src/lib.rs`): `JsTolerances` has six `f64`
  with `#[serde(default)]`; `undefined`/`null` options →
  `JsOptions::default()` → all zero. `defaultOptions()` hardcodes 2e-3.
- CLI (`simtest-funnel-cli/src/main.rs`): each coefficient is
  `flag.or(params).unwrap_or(default_coefficient)`.
- `io::ParamFile` stores the six coefficients as `f64` with
  `#[serde(default)]`, so an absent key is indistinguishable from `0`.
  `tests/corpus_parity.rs` builds `Tolerances` from these fields; the
  LBNL corpus treats absent keys as zero (`success7`, `success9`,
  `success10` omit keys).
- The uncommitted `add-violation-summary` work adds `summarize`, which
  echoes `opts.tolerances` (a resolved `Tolerances`) in all languages.

## Goals / Non-Goals

**Goals:**

- One resolution function in the core; every front end builds a
  "partial" set from what the caller gave and calls it.
- Make the absent-vs-zero distinction representable in every input
  surface (Rust, Python, JS, CLI flags, param JSON).
- Turn the Rust struct-update pitfall
  (`Tolerances { atoly: …, ..Default::default() }`) into a compile
  error rather than a silent semantic change.

**Non-Goals:**

- No change to the comparison algorithm, to `compare`/`summarize`
  signatures in Rust, or to how fully explicit `Tolerances` behave.
- No validation of coefficient values (negative/NaN stay as today).
- No new public "resolve" entry point in Python/TS beyond what is
  needed; resolved values are observable through `default_options()` /
  `defaultOptions()` and the summary echo.

## Decisions

1. **Core type `PartialTolerances` + `resolve()`.** A new public
   `Copy` struct with six `Option<f64>` fields, `Default` = all `None`,
   and `fn resolve(&self) -> Tolerances` implementing the per-axis rule.
   `From<Tolerances> for PartialTolerances` (all `Some`) lets explicit
   values round-trip. `Options` keeps a resolved `Tolerances`, so
   `compare`, `compare_into`, `summarize` and the tube code are
   untouched and the summary automatically echoes resolved values.
   *Alternative:* make `Options.tolerances` partial and resolve inside
   `compare` — rejected: changes the hot-path API and every existing
   caller for no gain.

2. **`Tolerances` loses its `Default` impl; gains `Tolerances::ZERO`
   and `Tolerances::DEFAULT` constants.** `DEFAULT` is
   `rtolx = rtoly = 2e-3`, everything else zero, and equals
   `PartialTolerances::default().resolve()`; `Options::default()`
   uses it. Explicit all-zero is spelled `Tolerances::ZERO`.
   *Alternatives:* `Default` = zero (status quo; disagrees with
   `Options::default()`), or `Default` = 2e-3 (struct-update would fill
   each coefficient individually — exactly the CLI bug, and contrary to
   the per-axis rule). Removing `Default` makes every existing
   `..Default::default()` fail to compile, forcing a deliberate choice
   between `ZERO`, `DEFAULT` and `PartialTolerances`.

3. **Serde on `PartialTolerances` (feature `json`).** Fields are
   `#[serde(default)]` `Option<f64>`, so an absent key and JSON `null`
   are both "not given" and `0` / `0.0` is "given".

4. **`ParamFile` tolerance fields become `Option<f64>`** plus
   `ParamFile::tolerances() -> PartialTolerances`. This is the only way
   to distinguish absent from zero in the param JSON without a second
   parse. The corpus-parity harness keeps LBNL semantics by mapping
   `None` to `0.0` explicitly (`unwrap_or(0.0)`), so its expected
   results are unchanged.

5. **CLI: merge then resolve.** Per coefficient take the flag if
   present, else the param-file value if present, else "not given";
   then call `resolve()` once. The CLI help text and README describe
   the per-axis rule.

6. **Python: dataclass fields are `float | None = None`.**
   `Tolerances()` means "nothing given" and `Options()` therefore means
   defaults. `None` values are passed through to the native layer, which
   builds a `PartialTolerances` (missing key or `None` → not given) and
   resolves it in Rust. `default_options()` returns a fully explicit
   `Tolerances` (six floats); `ViolationSummary.tolerances` is always six
   floats (resolved echo). *Alternative:* a sentinel object instead of
   `None` — rejected as less idiomatic and harder to type under
   `mypy --strict`.

7. **wasm/TS: optional (`?: number | null`) fields.** The wasm input
   struct uses `Option<f64>` fields (`undefined`, missing or `null` →
   not given) and converts to `PartialTolerances`; `undefined`/`null`
   options resolve to `Tolerances::DEFAULT`. `defaultOptions()` is
   produced from `Options::default_options()` instead of a hardcoded
   literal. The SDK adds a `ResolvedTolerances` type (six required
   numbers) used by `defaultOptions()` and `ViolationSummary`.

## Risks / Trade-offs

- [Callers relying on implicit zeros silently get `2e-3` on an
  untouched axis] → BREAKING note in proposal/changelog; READMEs state
  the rule; explicit zero remains expressible in every API.
- [Removing `Tolerances: Default` breaks downstream Rust code that
  derives `Default` on a struct containing `Tolerances`] → acceptable in
  beta; the compile error points at the fix (`Tolerances::ZERO` /
  `DEFAULT`).
- [CLI with an LBNL param file that omits a whole axis no longer gets
  LBNL's zero on that axis] → documented in the CLI README "Differences
  from LBNL Funnel"; add explicit zero keys for exact parity.

## Migration Plan

Ship in the next beta release. Rust: replace `Tolerances::default()`
with `Tolerances::ZERO` (old meaning) or use `PartialTolerances`.
Python/TS: pass explicit `0.0` where an axis must have zero tolerance.
Rollback is a revert of this change; no persisted data is affected.
