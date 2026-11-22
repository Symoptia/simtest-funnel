# Design

## D1. Window extension that provably reproduces the full-range tube

### Problem

The extension used to be a fixed margin: every reference point whose x
half-width, taken twice, reaches the window, plus three samples. The
corner algorithm (C reference `algorithmRectangle.c`, `corners.rs`)
inserts no corners at a point whose incoming and outgoing slopes are
equal (within `1e-10`) and skips points equal to their successor (x in
normalized units and y within `1e-10`; with epoch-sized x, normalized by
~1.7e9, samples less than ~0.17 s apart with equal y). Inside such a run
the tube boundary is one segment between the corners before and after the
run. Cutting the reference inside the run moves the end of that segment,
which changes the boundary over the whole run, i.e. possibly over the
window however far away the cut is. Reviewer's case A: y = 0 for 13
points, then a long run of 2 at ~0.02 s spacing, epoch x, `atolx =
0.5585`: the upper boundary at the first sample is 0.4085 in the full
comparison (deviation 0.0915, Fail) and 2.0555 with the old extension
(Pass). Case B (one long linear run, `ltoly = 0.018`): the end corners of
a cut run lie on a different line than those of the whole run because
`hy` varies along it.

### Decision

Keep the old margin as the initial extension and grow it (doubling the
extension of a failing side) until a check on the corners of the
extended slice proves that the slice gives the full-range tube over the
window (`window.rs`). Once the slice would cover more than half of the
reference, use the whole reference. The check needs the corner scan to
report, per corner, the reference point it belongs to, the start point,
the *firm* corner points and the undone candidates; `corners.rs` gets a
`CornerObserver` (the plain comparison uses the no-op observer `()`, so
its arithmetic and results are unchanged bit for bit).

### Argument (also in the `window.rs` module docs)

`T` = corner list of the slice `s..e`, `F` = corner list of the whole
reference, per curve (lower and upper).

1. **Corner state.** The scan carries `(s0, m0)`, the sign and slope of
   the last processed segment. The slice scan starts at `b` (first point
   of the slice not equal to its successor) with the slope of `(b, b+1)`;
   the whole-reference scan processes `b` (it is not skipped) and leaves
   it with the same `(s0, m0)`. Hence both scans make the same corner
   decisions for every point in `(b, e-2]`, including steps (vertical
   segments, slope `±1e15`) and runs of repeated points (skipped
   identically, since skipping depends only on a point and its
   successor). They differ only in the corners of `b` and before, and in
   the undo step (a point's new corners are removed when the previous
   corner, the new corner and the next point's edge are at the same y),
   which reads the previous corner. A point is *firm* when its undo
   condition (`y[i+1] ± hy[i+1]` equal to its corner's y) is false: its
   corners stay whatever precedes them. From the first firm point `q > b`
   on, `T` and `F` are identical up to the corners of `e-2`.
2. **Bounds on what differs.** `hx = max(c, ltolx*|x|)` (absolute,
   local; no range-relative part when `rtolx = 0`), so `x + hx` and
   `x - hx` are non-decreasing for `ltolx <= 1` (the initial extension
   already uses the whole reference when `2*ltolx > 1`). Corners of
   points `<= b` lie at most at `x[b] + hx[b]`; corners of points in
   `(b, q)` are corners or undone candidates of `T`; corners of points
   `>= e-1` lie at least at `x[e-1] - hx[e-1]`. `hy` is per point
   (`max(atoly, ltoly*|y|)`), so varying `hy` along a run (case B) is
   covered by step 1 without further conditions.
3. **Loop removal.** `remove_loop` walks left to right; at a backward
   segment `(j, j+1)` it scans back to the last point with `x <= x[j+1]`,
   forward to the first point with `x >= x[j]`, deletes the points in
   between and inserts the intersection. A corner `A` is a *gap* when all
   corners before it (in `T`, and in `F` by step 2) are left of `x(A)`
   and all after it right of `x(A)`, by more than `2.5e-10` (normalized;
   more than the algorithm's equality tolerance, so `A` is never merged
   with a neighbour). No backward segment spans a gap; a removal left of a
   gap stops at it unchanged; a removal right of a gap reaches back at
   most to the gap (may delete it) and the point before (reads it). So
   for two consecutive gaps `P, A`, the processed curve left of `x(P)`
   depends only on corners up to `P` and the processed curve right of
   `x(P)` only on corners from `P` on. With a pair `x(P_L) < lo` and a
   pair `x(P_R) > hi`, all four corners common to `T` and `F`, the
   processed curves agree on `[x(P_L), x(P_R)]`, which contains the
   window. The deviation interpolation walks a cursor over the bounds;
   everything left of `x(P_L)` is left of every judged point, so the
   cursor lands in the common part in both comparisons and the judged
   deviations are bit-identical.

**Assumption.** Step 3 uses that each removal inserts its intersection
on the segment it cuts (a genuine crossing). The C reference's heuristic
can, in degenerate geometry (nearly parallel segments, crossings within
rounding of a corner), intersect the extended lines elsewhere; then a
removal could reach one point further back. This is the only part of the
guarantee that is not proven; the documentation says so.

**Remove-loop interaction across the boundary** (asked for in the
review): handled by step 3, which is why a pair of consecutive gaps is
needed on each side and not a single gap or a point count.
**ltolx / ltoly varying along a run**: handled by steps 1–2 (per-point
half-widths, monotone reach for `ltolx <= 1`; whole reference otherwise).

### Guarantee as now stated

With `rtolx = rtoly = 0` and any `atolx`, `atoly`, `ltolx`, `ltoly`, every
test point inside the window gets the same deviation, bit for bit, and so
the same verdict, as in the comparison without an x-range; exact for the
corner construction, assuming genuine crossings in loop removal. With
`rtolx` / `rtoly` the window is the base of the tolerances by design.

### Cost

The check reads only the slice, so the cost is proportional to the final
extension (geometric growth). For smooth and step signals it stays within
a few half-widths (measured on 10^6 samples, 10-unit window: within 30 %
of the old cost). It reaches the data end through a collinear or constant
run that long, or where the reference turns more often than the x
tolerance is wide (noise with `atolx` of several samples): then the
window costs about 1.5× a full-range comparison (measured: 190–270 ms vs
120–175 ms full, 2–3 ms before). A weaker but still exact condition for
such signals would need a proof that loop removal forgets distant
history, which the heuristic does not obviously give; not attempted.

### Verification

- Regression tests from the reviewer's dumped cases
  (`tests/fixtures/window/*.txt`): case A, case B, an `ltoly` run at epoch
  x, an `ltolx` case.
- `extension_reaches_the_end_of_a_collinear_run`, constant reference,
  cost on 2·10^6 samples.
- Property tests now require bit-identical deviations; new
  `adversarial_windows_match_full_range_bit_for_bit` ports the reviewer's
  harness (collinear runs, steps, repeated/clustered/log-uniform x, epoch
  x, window edges inside runs).
- Reviewer's harness and an extended version run at scale (numbers in the
  task list).
