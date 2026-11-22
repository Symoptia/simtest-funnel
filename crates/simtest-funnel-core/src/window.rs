//! The part of the reference a windowed comparison builds its tube from.
//!
//! With an x-range window `[lo, hi]`, the tube is built from a slice
//! `s..e` of the reference that contains the window and is chosen so that
//! the tube over the window equals the tube of the whole reference there.
//! The slice starts as the window plus two x half-widths and three samples
//! on each side ([`initial_extension`]) and is grown (doubling the
//! extension of the side that fails) until [`synchronized`] confirms both
//! sides; in the worst case it is the whole reference on that side, and
//! once it would cover more than half of the reference the whole
//! reference is used without further checks.
//!
//! # Why a check and not a fixed margin
//!
//! The corner algorithm (`corners.rs`) adds no corners inside a run of
//! collinear reference points or of points it treats as repeated (x and y
//! equal within its `1e-10` tolerance, in normalized x: with epoch-sized
//! times, samples less than ~0.17 s apart), and connects the corners
//! before and after such a run with one segment. Cutting the reference
//! inside a run changes that segment over the whole run, however far it
//! reaches. The check below finds, from the corners of the slice, a place
//! on each side where the slice and the whole reference provably give the
//! same tube.
//!
//! # The argument
//!
//! Write `T` for the corner list of the slice and `F` for that of the
//! whole reference (one per curve, lower and upper, checked separately).
//!
//! 1. *Corner state.* The corner scan carries the sign and slope of the
//!    last segment and visits the points left to right. The slice scan
//!    starts at `b` (the first point of the slice not repeated by its
//!    successor) with the slope of segment `(b, b+1)`; the whole-reference
//!    scan, which also processes `b`, leaves `b` with the same slope. From
//!    `b + 1` on both scans compute the same corners for every point up to
//!    `e - 2` (the last point whose successor is in the slice). Only two
//!    things differ: the corners of `b` and before, and the undo step (a
//!    point's corners are removed when they lie on the horizontal edge of
//!    the previous corner and of the next point), which looks at the
//!    previous corner. A *firm* corner point is one whose undo condition
//!    is false whatever precedes it; its corners stay in both lists, and
//!    from the first firm point `q > b` on the lists are identical up to
//!    the corners of `e - 2`.
//! 2. *Where the differences lie.* The x half-width has the form
//!    `max(c, ltolx*|x|)`, so for `ltolx <= 1` both `x + h(x)` and
//!    `x - h(x)` are non-decreasing. Corners of points `<= b` therefore
//!    lie at most at `x[b] + h[b]`; corners of points in `(b, q)` are
//!    corners of `T` or undone candidates of `T`; corners of points
//!    `>= e - 1` lie at least at `x[e-1] - h[e-1]`.
//! 3. *Loop removal.* `remove_loop` walks the curve left to right; at a
//!    backward segment `(j, j+1)` it scans back to the last point with
//!    `x <= x[j+1]`, forward to the first point with `x >= x[j]`, deletes
//!    the points in between and inserts their intersection. Call corner
//!    `A` a *gap* when every corner before it (in `T` and, by step 2, in
//!    `F`) lies left of `A` and every corner after it lies right of `A`,
//!    both by more than the corner algorithm's equality tolerance. No
//!    backward segment spans a gap; a removal left of a gap stops at it
//!    without changing it; a removal right of a gap reaches back at most
//!    to the gap (which it may delete) and the point before it (which it
//!    reads). So for two consecutive gaps `P`, `A` the processed curve
//!    left of `x(P)` depends only on the corners up to `P`, and the one
//!    right of `x(P)` only on the corners from `P` on. With such a pair
//!    `x(P_L) < lo` and such a pair `x(P_R) > hi`, all four corners
//!    common to `T` and `F` (step 1), the processed curves agree on
//!    `[x(P_L), x(P_R)]`, which contains the window, bit for bit, and so
//!    do the deviations of the test points in the window (interpolation
//!    passes the points left of the window, all left of `x(P_L)`, and
//!    then reads only that part).
//!
//! The assumption in step 3 is that loop removal inserts the intersection
//! where the curve crosses the segment it cuts, which holds except where
//! the heuristic meets degenerate geometry (lines parallel or crossing
//! within rounding of a corner). Where the window reaches the first or
//! last reference point, that side is not cut at all.
//!
//! The check reads only the slice, so its cost grows with the extension:
//! a few half-widths for most signals. It can reach the data end where no
//! gap exists: a long linear or constant run (no corners), or a signal
//! whose direction changes more often than the x tolerance is wide (no
//! backward-free stretch, e.g. noise with a large `atolx`).
//!
//! Range-relative tolerances (`rtolx`, `rtoly`) use the window for their
//! bases, so the tube differs from the full-range one by design; the
//! slice is chosen the same way.

use crate::cancel::{Cancelled, Checkpoint};
use crate::corners::{corner_traces, denormalized, normalized_copy, CornerTrace};
use crate::options::Tolerances;
use crate::tube::{halfwidth_x_bound, tube_halfwidths_checked, DataChar};

/// Initial extension beyond the window, in x half-widths: what a
/// reference point's tube rectangle reaches, plus one for the corner
/// segments and loop removal. Enough for most signals; the check grows
/// it where it is not.
const EXTENSION_HALFWIDTHS: f64 = 2.0;

/// Reference samples added to the initial extension on each side.
const EXTENSION_SAMPLES: usize = 3;

/// Minimum separation, in normalized x, of a gap corner from the corners
/// before and after it: more than the corner algorithm's equality
/// tolerance `1e-10`, so loop removal never treats a neighbour as equal
/// to it.
const GAP: f64 = 2.5e-10;

/// The slice of the reference to build the tube for the window `w`
/// (the reference points in `[lo, hi]`) from, so that the tube over the
/// window equals the full-range tube (see the [module docs](self)).
#[allow(clippy::too_many_arguments)]
pub(crate) fn window_extension<C: FnMut() -> Result<(), Cancelled>>(
    t_ref: &[f64],
    y_ref: &[f64],
    w: std::ops::Range<usize>,
    lo: f64,
    hi: f64,
    dc: DataChar,
    tol: &Tolerances,
    mag_x: f64,
    cp: &mut Checkpoint<'_, C>,
) -> Result<std::ops::Range<usize>, Cancelled> {
    let n = t_ref.len();
    let init = initial_extension(t_ref, w.clone(), lo, hi, dc, tol);
    let (mut s, mut e) = (init.start, init.end);
    loop {
        if s == 0 && e == n {
            return Ok(0..n);
        }
        let (left, right) = synchronized(t_ref, y_ref, s..e, lo, hi, dc, tol, mag_x, cp)?;
        if left && right {
            return Ok(s..e);
        }
        if !left {
            s = w.start.saturating_sub(2 * (w.start - s) + 8);
        }
        if !right {
            e = w.end.saturating_add(2 * (e - w.end) + 8).min(n);
        }
        // Beyond half the reference, checking costs more than it saves.
        if 2 * (e - s) > n {
            return Ok(0..n);
        }
    }
}

/// Initial slice for the window `w` (the reference points in `[lo, hi]`).
///
/// On the left it starts `EXTENSION_SAMPLES` points before the first
/// point `x` left of the window whose x half-width `h(x)` satisfies
/// `x + EXTENSION_HALFWIDTHS * h(x) >= lo`; on the right it ends
/// `EXTENSION_SAMPLES` points after the last point with
/// `x - EXTENSION_HALFWIDTHS * h(x) <= hi`. `h` is the upper bound
/// [`halfwidth_x_bound`], of the form `max(c, ltolx * |x|)`, so with
/// `EXTENSION_HALFWIDTHS * ltolx <= 1` both reaches are monotone in `x`
/// and the points are found by binary search. Otherwise (a local x
/// tolerance of 50 % or more, or non-finite times) the slice is the whole
/// reference on each side that has points beyond the window; the check of
/// [`synchronized`] also relies on that monotonicity. A window that starts
/// (ends) at the first (last) reference point has nothing to extend on
/// that side.
pub(crate) fn initial_extension(
    t_ref: &[f64],
    w: std::ops::Range<usize>,
    lo: f64,
    hi: f64,
    dc: DataChar,
    tol: &Tolerances,
) -> std::ops::Range<usize> {
    let n = t_ref.len();
    let (k, extra) = (EXTENSION_HALFWIDTHS, EXTENSION_SAMPLES);
    let reach = |x: f64| k * halfwidth_x_bound(x, dc, tol);
    let bounded = k * tol.ltolx <= 1.0 && t_ref[0].is_finite() && t_ref[n - 1].is_finite();
    let start = if w.start == 0 || !bounded {
        0
    } else {
        let p = t_ref[..w.start].partition_point(|&x| x + reach(x) < lo);
        p.saturating_sub(extra)
    };
    let end = if w.end == n || !bounded {
        n
    } else {
        let p = t_ref[w.end..].partition_point(|&x| x - reach(x) <= hi);
        (w.end + p).saturating_add(extra).min(n)
    };
    start..end
}

/// Whether the slice `r` of the reference gives the full-range tube over
/// `[lo, hi]`, as `(left side, right side)`; a side where the slice
/// reaches the data end is always confirmed. See the
/// [module docs](self) for the argument.
#[allow(clippy::too_many_arguments)]
fn synchronized<C: FnMut() -> Result<(), Cancelled>>(
    t_ref: &[f64],
    y_ref: &[f64],
    r: std::ops::Range<usize>,
    lo: f64,
    hi: f64,
    dc: DataChar,
    tol: &Tolerances,
    mag_x: f64,
    cp: &mut Checkpoint<'_, C>,
) -> Result<(bool, bool), Cancelled> {
    let (cut_left, cut_right) = (r.start > 0, r.end < t_ref.len());
    let (tr, yr) = (&t_ref[r.clone()], &y_ref[r]);
    let (hx, hy) = tube_halfwidths_checked(tr, yr, dc, tol, cp)?;
    let xn = normalized_copy(tr, mag_x, cp)?;
    let hxn = normalized_copy(&hx, mag_x, cp)?;
    let traces = corner_traces(&xn, yr, &hxn, &hy, cp)?;
    let sides = Sides {
        cut_left,
        cut_right,
        lo,
        hi,
        mag_x,
    };
    let (mut left, mut right) = (true, true);
    for t in &traces {
        let (l, r) = sides.check(t, &xn, &hxn);
        left &= l;
        right &= r;
        cp.tick(t.x.len())?;
    }
    Ok((left, right))
}

/// What [`synchronized`] checks a corner trace against.
struct Sides {
    cut_left: bool,
    cut_right: bool,
    lo: f64,
    hi: f64,
    mag_x: f64,
}

impl Sides {
    /// `(left, right)` confirmation for one corner curve of the slice
    /// with normalized x `xn` and x half-widths `hxn`.
    fn check(&self, t: &CornerTrace, xn: &[f64], hxn: &[f64]) -> (bool, bool) {
        let m = xn.len();
        let k = t.x.len();
        // Corners of points >= `first` are corners of the whole reference
        // too; `head` bounds the x of the whole reference's corners of
        // points < `first` that are not corners of the slice.
        let (first, head) = if self.cut_left {
            let b = t.start;
            let Some(&q) = t.firm.iter().find(|&&i| i > b) else {
                return (false, false);
            };
            let mut head = xn[b] + hxn[b];
            for &(i, x) in &t.undone {
                if i < q {
                    head = head.max(x);
                }
            }
            (q, head)
        } else {
            (0, f64::NEG_INFINITY)
        };
        // Corners of points <= `last` are corners of the whole reference
        // too; corners of the whole reference of points beyond the slice
        // lie at or right of `tail`.
        let (last, tail) = if self.cut_right {
            (m.saturating_sub(2), xn[m - 1] - hxn[m - 1])
        } else {
            (usize::MAX, f64::INFINITY)
        };
        // suffix[g]: smallest x of corners g.. and of the tail.
        let mut suffix = vec![tail; k + 1];
        for g in (0..k).rev() {
            suffix[g] = suffix[g + 1].min(t.x[g]);
        }
        // A pair of consecutive common gap corners (P, A): the processed
        // curve right of P depends only on corners from P on, the one
        // left of P only on corners up to A.
        let (mut left, mut right) = (!self.cut_left, !self.cut_right);
        let mut prefix = head;
        let mut previous_gap = false;
        for g in 0..k {
            if left && right {
                break;
            }
            let x = t.x[g];
            let common = t.tag[g] >= first && t.tag[g] <= last;
            let gap = common && x > prefix + GAP && x < suffix[g + 1] - GAP;
            if gap && previous_gap {
                let p = denormalized(t.x[g - 1], self.mag_x);
                left |= p < self.lo;
                right |= p > self.hi;
            }
            previous_gap = gap;
            prefix = prefix.max(x);
        }
        (left, right)
    }
}
