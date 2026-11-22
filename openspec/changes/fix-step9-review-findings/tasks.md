# Tasks

## 1. Core: window extension (finding 1)

- [x] 1.1 Add `CornerObserver` / `CornerTrace` to `corners.rs` (no-op observer for the plain comparison). Verify corpus parity and the differential tests unchanged (`cargo test --workspace --features simtest-funnel-core/json`).
- [x] 1.2 Add `window.rs`: initial extension (former margin), the synchronization check (firm corner point, pairs of consecutive common gap corners on both sides, bounds from monotone reach), geometric growth, whole reference beyond half of it; wire into `compare.rs`. Verify `cargo test -p simtest-funnel-core`.
- [x] 1.3 Regression tests from the reviewer's dumped cases, collinear-run and constant-reference extension tests, bit-identity in the property tests, port of the reviewer's harness as `adversarial_windows_match_full_range_bit_for_bit`. Verify each fixture fails at 41882ff and passes now.
- [x] 1.4 Run the differential harnesses at scale against 41882ff: the reviewer's original harness (6 seeds × 25 000 cases: 624 489 windows) and the extended one (14 distinct seeds × 20 000 cases: 1 133 000 windows): 0 verdict flips, 0 bit differences in judged deviations, 0 parity differences without x-range.
- [x] 1.5 Update rustdoc (`compare` module, `window` module with the argument), the core, Python, SDK, MCP and root READMEs and the `compare_signals` description to state the guarantee and its assumption.
