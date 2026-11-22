# Design

## Context

See proposal.md (Why). State before this change, in
`crates/simtest-funnel-core/src/compare.rs`:

- `range_indices` (two binary searches) selects the reference points in
  `[lo, hi]`; `tube_halfwidths_checked` and `build_bounds_checked` then
  run on that clipped slice only. `get_data_char` over the slice gives the
  bases of `rtolx` / `rtoly` (`range_x`, `range_y`), the magnitudes of the
  constant-reference fallback, and `mag_x`, by which the corner algorithm
  normalizes x (`normalize` / `denormalize`, and its `1e-10` equality
  tests work on normalized x).
- Deviations are computed for every test point against the clipped tube,
  clamped to its end values outside it; only test points in the
  effective range (`x_range` ∩ reference extent) decide `Fail`
  (`classify_status`) and enter `summarize`. Coverage
  (`MissingReference` / `MissingTest`) compares both extents clipped to
  `x_range`.
- The corner algorithm (port of LBNL `algorithmRectangle.c`) is local but
  not an exact envelope: the corners of a reference point depend on the
  slope arriving at it, repeated points and collinear runs insert no
  corners, and loop removal intersects segments of neighbouring corners.
- Consumers of the result arrays: `summarize` (filters by effective
  range, evaluates the bounds at the worst x), the MCP plot tool (reduces
  the bounds inside the view plus one neighbour, evaluates them at judged
  test points bit-identically to the library, filters violations by
  effective range), the TS `createFunnelPlot` helper (draws all arrays).
  The CLI has no x-range option.

## Goals / Non-Goals

**Goals:**

- In-window verdicts equal to the full-range comparison when no
  range-relative tolerance is involved, verified by a property test.
- Bit-identical results without `x_range` (LBNL corpus parity,
  differential and pinned cross-language tests unchanged).
- A small window on a huge record stays cheap.

**Non-Goals:**

- No new option (e.g. to switch back to clipping) and no API shape change.
- No change to coverage classification, to the `InsufficientData` rule or
  to what `summarize` judges.
- No change to the corner algorithm itself.
- No compatibility with earlier beta behaviour (beta line).

## Decisions

1. **Extension rule and margin — design choice, not yet confirmed by
   the owner.** On each side the tube is built from every reference point
   `x` beyond the window whose reach `x ± 2·h(x)` touches the window, plus
   **3 further samples**. `h` is an upper bound of the x half-width,
   `max(atolx, rtolx·range_x, rtolx·mag_x (fallback), 1e-10, ltolx·|x|)`,
   with the window's bases (decision 3).
   - *One half-width* is what a point's tube rectangle reaches; a
     second covers the corner segments and loop removal that connect
     corners of neighbouring points. *Extra samples* are needed because
     the first point of a truncated reference gets other corners than in
     the full reference (no incoming slope) and the algorithm skips
     repeated points and collinear runs.
   - *Evidence* (the experiment that the property test in
     `window_property.rs` keeps): random references (random walk, noisy
     sine, steps, small integers, smooth sine, flat runs mixed with a
     cosine; irregular grids, some with repeated x), shifted noisy tests
     on another grid, random `atolx`, `ltolx`, `atoly`, `ltoly`, random
     windows (also partly outside the data); every judged point compared
     with the full-range comparison. `K` = half-widths, `S` = extra
     samples; "verdict" = points whose inside/outside differs, "value" =
     points whose deviation differs in any bit.

     | Run | K=0 | K=1 | K=1.5 | K=2 | K=3 |
     | --- | --- | --- | --- | --- | --- |
     | A, S=0 (verdict/value) | 733/1779 | 63/510 | 41/401 | 35/367 | 31/336 |
     | A, S=1 | 170/565 | 0/29 | 0/25 | 0/24 | 0/22 |
     | A, S=2 | 66/232 | 0/1 | 0/0 | 0/0 | 0/0 |
     | B, S=2 (value) | | 3 | 0 | 0 | 0 |
     | B, S=3 (value) | | 0 | 0 | 0 | 0 |
     | C, S=1 (value) | | 135 | 133 | 133 | 132 |
     | C, S=2 (value) | | 2 | 1 | 1 | 1 |
     | C, S=3 (value) | | 0 | 0 | 0 | 0 |

     A: 2 754 windows, 72 622 judged points (`atolx` ≤ 3 samples-ish,
     windows ≤ 60 % of the data). B: as A with 27 515 windows, 711 127
     points. C: wide x tolerance (`atolx` up to ~20 samples, `ltolx` up
     to 0.3), windows ≤ 30 %, 12 971 windows, 201 596 points. With `K ≥ 1`
     and `S ≥ 1` no verdict differed; all remaining value differences were
     rounding (relative ≤ 5e-14), in cases with zero x tolerance, flat
     runs or repeated x. `K = 2, S = 3` is chosen: zero differences in
     every run, with a factor-2 safety on the half-width count, for a cost
     of a few samples per side.
   - *What is guaranteed* (spec "In-window equivalence"): with
     `rtolx = rtoly = 0`, the same verdict for every judged point, and
     deviations and bounds equal up to rounding. Bit-identity is not
     promised: a run of collinear reference segments (no corners inside)
     crossing the start of the extension draws the same line from a
     different start corner, which can differ in the last bits; making it
     exact would mean scanning back over the whole run (unbounded cost).
     Such a difference can only flip a verdict for a test point within
     rounding of a bound; none was observed. The Rust property test
     asserts identical verdicts, deviations within `1e-12` relative and
     ≥ 99.9 % bit-identical deviations (in fact 100 % on its seeds);
     Python and TypeScript property tests assert bit-identical deviations
     on their own random cases.
   - *Alternatives*: one half-width and no extra samples (verdicts
     differ, table); extending by a fixed multiple of the window or by a
     time span given by the caller (not tied to the tolerance; would need
     a new option); recomputing the full-range tube and cutting it
     (correct but costs a full comparison).

2. **x is normalized by the magnitude of the whole reference** — a
   technical decision required for decision 1. The corner algorithm
   divides x by `mag_x` and compares normalized values with `1e-10`; with
   the window's (or extension's) `mag_x` the corners would differ from
   the full-range ones in rounding and, near the `1e-10` tests, in
   behaviour. The reference is sorted, so `max(x_last, |x_first|)` is the
   value `get_data_char` computes for the whole reference, in O(1).
   Without `x_range` this is the same value as before, so results stay
   bit-identical (verified by the corpus tests).

3. **Range-relative bases stay those of the window — design choice, not
   yet confirmed by the owner.** `range_x`, `range_y` and the fallback
   magnitudes are computed from the reference points inside the window,
   as before; the extension points get half-widths from the same bases.
   This is the easiest rule to explain ("rtol is relative to what you
   compare"), keeps windowed `rtol` results unchanged apart from the edge
   effect, and makes the extension well defined (it depends on the
   half-widths, which depend on the bases). Consequence, documented
   everywhere: with `rtolx` / `rtoly` a windowed comparison differs from
   the full-range one by design. *Alternatives*: bases from the whole
   reference (a window would then be a pure zoom, but `rtoly` on a small
   window of a long record would become very loose, and it changes
   today's results); bases from the extended reference (depends on the
   tolerance itself and is hard to explain).

4. **Coverage and minimum points stay judged within the window**
   (owner's instruction): `MissingReference` / `MissingTest` compare the
   extents clipped to `x_range`; at least two reference and two test
   points must lie inside the window. A window that misses the data, even
   by less than the x tolerance, stays `EmptyRange`.

5. **Result arrays — design choice, not yet confirmed by the owner.**
   - *Bounds*: the tube of the extended reference, not cut at the
     window. Cutting would need interpolated end vertices, whose values
     differ in rounding from the values the comparison judged; the MCP
     plot evaluates the bounds bit-identically to the library and reduces
     only the part in the view, and `summarize` evaluates them at judged
     points, so both stay correct with longer bounds. The plot now draws
     the tube up to the view edges instead of ending inside the window.
   - *Deviations*: one per test point (`errors_x` = test x as before);
     `0` for test points outside `x_range`, and computed only for test
     points inside it. Before, points outside the window got values from
     the clipped tube's clamped end values that nothing judged and that
     the TS plotting helper drew as spurious errors; against the extended
     tube they would be partial and misleading as well. Inside `x_range`
     but beyond the reference extent, deviations are still scored against
     the clamped end values, as in LBNL, so the unbounded case stays
     bit-identical. `summarize`, the plot and the snippet need no change.
   - *Alternatives*: return the full-range bounds (costly); report
     deviations against the extended tube outside the window (partial,
     not judged).

6. **Finding the extension: binary search on a monotone reach.** The
   bound `h(x) = max(c, ltolx·|x|)` makes `x + 2h(x)` and `x − 2h(x)`
   non-decreasing whenever `2·ltolx ≤ 1`, so `partition_point` finds the
   first reaching point on each side in O(log n). Because `h` bounds the
   real half-width from above (it may include the fallback where the
   real one does not), the extension can only be larger than needed,
   never smaller. With `ltolx ≥ 0.5` (a 50 % local x tolerance, where far
   points can reach the window) or non-finite times, the whole side is
   used: correct, only slower, and not a realistic setting.

7. **Cost and cancellation.** The extension search is O(log n) and needs
   no checkpoint. The half-width, corner and deviation phases run on the
   extended slice and the in-window test slice, with their existing
   checkpoints; only the copy of the test x-values and the zero-filled
   deviation array are O(n_test) (memory-bound, as the classification pass
   already was). An 11-sample window in 2 million samples builds its tube
   from 37 samples (test `extension_cost_does_not_grow_with_the_reference`).

8. **Tests.** Rust: property test (two seeds and tolerance regimes,
   ~3 300 windows, ~75 000 judged points), the daily-cycle edge case
   (including that a clipped reference still fails), data start / end,
   window narrower than the tolerance, window partly / wholly outside the
   data, `rtoly` relative to the window, extension size. The same cases in
   Python and TypeScript (with smaller property tests), MCP
   `compare_signals` (numeric and ISO bounds) and `plot_signals` (PASS, same
   row as compare, tube reaching the view edges). **No existing test
   changes its expected values**: every existing windowed test either has
   no x tolerance, or no reference outside the window, or a verdict the
   edge effect does not touch, and none asserted deviations outside the
   window. The CLI has no x-range and gets no test.

## Risks / Trade-offs

- [Windowed comparisons with an x tolerance can now pass at the window
  edges where they failed] → this is the intended effect; stated in the
  proposal and in the commit message.
- [Range-relative tolerances still make a window differ from the full
  comparison] → documented in every layer as a deliberate rule
  (decision 3); flagged for the owner.
- [The margin is empirical, not proven for every input of the corner
  algorithm] → the guarantee is stated as verdict equality, checked by a
  property test in three languages over several signal shapes; a factor-2
  safety on half-widths and one sample more than measured were added.
- [Rounding-level differences in deviations and bounds in rare collinear
  cases] → documented; harmless for verdicts except at a bound within
  rounding.
- [Longer bounds in the result for small windows] → bounded by the
  extension (a few samples and two half-widths per side).
- [MCP pytest snippets generated before may assert an old `Fail` status
  for a window edge case] → beta; regenerate the snippet.

## Migration Plan

Ships with the next beta release; no data migration and no API change.
Rollback is a revert of the change.
