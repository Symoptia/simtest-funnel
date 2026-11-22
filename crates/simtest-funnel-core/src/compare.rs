//! Public `compare` / `compare_into` API wiring the tube-size,
//! corner-enumeration, and error stages together.
//!
//! # The x-range window
//!
//! [`Options::x_range`] restricts which test points are judged to the
//! window `[lo, hi]` (intersected with the reference x-extent). The tube is
//! not built from the reference clipped to the window: it is built from the
//! reference extended beyond the window on both sides (by two x
//! half-widths plus three samples, see `extended_indices`), so the tube
//! over the window covers reference values just outside it, as it does in
//! a comparison over the full range. A test point inside the window that
//! is shifted in x by less than the x tolerance is therefore judged as in
//! the full-range comparison, also at the window edges. Where the window
//! reaches the first or last reference point there is nothing to extend
//! with, as in a full-range comparison.
//!
//! What stays relative to the window: the bases of the range-relative
//! tolerances (`range_x`, `range_y` and, for the constant-reference
//! fallback, the magnitudes) are computed from the reference points
//! inside the window, so with `rtolx` / `rtoly` a windowed comparison
//! differs from the full-range one by design; the coverage checks
//! ([`Status::MissingReference`] / [`Status::MissingTest`]) compare the
//! extents clipped to the window, and at least two reference and two test
//! points must lie inside the window ([`Status::InsufficientData`]).
//!
//! Without range-relative tolerances, every test point inside the window
//! gets the same verdict as in the full-range comparison. The deviations
//! and bounds there are in practice bit-identical to the full-range ones;
//! the only known exception is floating-point rounding when a run of
//! collinear reference segments crosses the start of the extension (the
//! corner algorithm inserts no corners inside such a run), which can
//! only matter for a test point within rounding error of a bound.

use crate::cancel::{CancelToken, Cancelled, Checkpoint};
use crate::corners::build_bounds_checked;
use crate::errors::compute_errors_checked;
use crate::options::{Options, Range, Tolerances};
use crate::status::Status;
use crate::tube::{get_data_char_checked, halfwidth_x_bound, tube_halfwidths_checked, DataChar};

/// Caller-provided output buffers for [`compare_into`].
pub struct Outputs<'a> {
    /// Lower bound x-values.
    pub lower_x: &'a mut [f64],
    /// Lower bound y-values.
    pub lower_y: &'a mut [f64],
    /// Upper bound x-values.
    pub upper_x: &'a mut [f64],
    /// Upper bound y-values.
    pub upper_y: &'a mut [f64],
    /// Test-grid x-coordinates, length == `t_test.len()`.
    pub errors_x: &'a mut [f64],
    /// Signed deviations, as in [`CompareResult::errors`].
    pub errors_y: &'a mut [f64],
}

/// Sizing hints.
pub struct Capacities {
    /// Upper bound on points in each of lower/upper curves.
    pub bound_capacity: usize,
    /// Always `n_test`.
    pub errors_capacity: usize,
}

/// Suggested capacities: `8 * n_reference` for bounds; `n_test` for errors.
pub fn estimate_capacities(n_reference: usize, n_test: usize) -> Capacities {
    Capacities {
        bound_capacity: 8 * n_reference,
        errors_capacity: n_test,
    }
}

/// Owned-Vec result returned by [`compare`].
pub struct CompareResult {
    /// Comparison status code.
    pub status: Status,
    /// Lower bound `(x, y)`. With an `x_range`, the bound of the tube built
    /// from the reference extended beyond the window (see the
    /// [module docs](self)), so it reaches past the window by up to the
    /// extension plus an x half-width.
    pub lower: (Vec<f64>, Vec<f64>),
    /// Upper bound `(x, y)`, over the same x-extent as `lower`.
    pub upper: (Vec<f64>, Vec<f64>),
    /// Errors `(x, y)`, one per test point: `x` is the test x-value and `y`
    /// the signed deviation (positive above the upper bound, negative below
    /// the lower bound, `0` inside the tube). Test points outside `x_range`
    /// get `0`; test points inside `x_range` but beyond the reference
    /// extent are scored against the bounds' end values, as in the LBNL
    /// reference, but are not judged (see [`Status`]).
    pub errors: (Vec<f64>, Vec<f64>),
}

#[inline]
fn is_non_decreasing(x: &[f64]) -> bool {
    x.windows(2).all(|w| w[0] <= w[1])
}

/// Index range of the points of a non-decreasing, NaN-free `x` with
/// `lo <= x[i] <= hi`.
///
/// Such points are contiguous, so two binary searches find them; this
/// selects exactly the points the former element-by-element filter kept
/// (`x[i] >= lo && x[i] <= hi`, nothing when a bound is NaN) without
/// copying or scanning the input.
fn range_indices(x: &[f64], lo: f64, hi: f64) -> std::ops::Range<usize> {
    if lo.is_nan() || hi.is_nan() {
        return 0..0;
    }
    let start = x.partition_point(|&v| v < lo);
    let end = x.partition_point(|&v| v <= hi).max(start);
    start..end
}

/// `max|x|` of a non-decreasing, NaN-free, non-empty `x`, computed as
/// [`get_data_char`](crate::tube::get_data_char_checked) computes `mag_x`
/// (`max(x_max, |x_min|)`) from the two end points.
#[inline]
fn sorted_magnitude(x: &[f64]) -> f64 {
    x[x.len() - 1].max(x[0].abs())
}

/// Extension of the reference beyond an x-range window, in x half-widths.
///
/// One half-width is what a reference point's tube rectangle reaches;
/// the second covers the corner segments and loop removal of the corner
/// algorithm, which connect corners of neighbouring points. Measured with
/// the property test in `window_property.rs`: one half-width plus
/// [`EXTENSION_SAMPLES`] already gave identical in-window results; two
/// are used for safety (the extra cost is a few samples per side).
const EXTENSION_HALFWIDTHS: f64 = 2.0;

/// Reference samples kept beyond the half-width extension on each side.
///
/// The corners of a reference point depend on the slope of the segment
/// arriving at it, so the first sample of the extended reference gets
/// different corners than in the full reference, and the corner
/// algorithm skips repeated points and collinear runs. Measured (see
/// [`EXTENSION_HALFWIDTHS`]): 0 extra samples changed verdicts, 1 left
/// rounding-level differences in deviations in ~1 % of windows, 2 left
/// them in ~1 window in 10 000, 3 left none in ~40 000 random windows.
const EXTENSION_SAMPLES: usize = 3;

/// Index range of the reference used to build the tube for the window
/// `w` (the reference points in `[lo, hi]`).
///
/// On the left it starts `EXTENSION_SAMPLES` points before the first
/// point `x` left of the window whose x half-width `h(x)` satisfies
/// `x + EXTENSION_HALFWIDTHS * h(x) >= lo`; on the right it ends
/// `EXTENSION_SAMPLES` points after the last point with
/// `x - EXTENSION_HALFWIDTHS * h(x) <= hi`. `h` is the upper bound
/// [`halfwidth_x_bound`], of the form `max(c, ltolx * |x|)`, so with
/// `EXTENSION_HALFWIDTHS * ltolx <= 1` both reaches are monotone in `x`
/// and the points are found by binary search: the cost grows with the
/// extension, not with the length of the reference. Otherwise (a local
/// x tolerance of 50 % or more, or non-finite times) the extension takes
/// the whole reference on the side that has points beyond the window.
/// A window that starts (ends) at the first (last) reference point has
/// nothing to extend on that side.
fn extended_indices(
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

/// Full comparison returning owned vectors.
///
/// With an `x_range`, only test points inside it are judged, against the
/// tube built from the reference extended beyond it (see the
/// [module docs](self) for what is relative to the window).
///
/// Cannot be interrupted; see [`compare_cancellable`] /
/// [`compare_with_check`] for a comparison that can be stopped.
pub fn compare(
    t_ref: &[f64],
    y_ref: &[f64],
    t_test: &[f64],
    y_test: &[f64],
    opts: &Options,
) -> CompareResult {
    match compare_impl(t_ref, y_ref, t_test, y_test, opts, &mut || Ok(())) {
        Ok(r) => r,
        // The check above never fires.
        Err(_) => unreachable!("a check that never fires cannot cancel"),
    }
}

/// [`compare`] that stops when `token` is cancelled or its deadline
/// passes.
///
/// Returns `Err(`[`Cancelled`]`)` if the token fired before the
/// comparison finished (including a token that had already fired), and
/// otherwise exactly the result of [`compare`]. Input validation comes
/// first: invalid input returns its status even if the token has fired.
/// See the [`cancel`](crate::cancel) module for how promptly a comparison
/// stops.
pub fn compare_cancellable(
    t_ref: &[f64],
    y_ref: &[f64],
    t_test: &[f64],
    y_test: &[f64],
    opts: &Options,
    token: &CancelToken,
) -> Result<CompareResult, Cancelled> {
    compare_impl(t_ref, y_ref, t_test, y_test, opts, &mut || token.check())
}

/// [`compare`] that calls `check` at its checkpoints and stops as soon as
/// `check` returns `Err`, returning that error.
///
/// `check` is called between the phases of the comparison, every 32 768
/// elements inside the linear phases and, inside the corner clean-up,
/// after every few tens of thousands of elementary steps (typically
/// about 0.1 ms apart), so it may be moderately expensive, e.g. read a
/// clock or poll for an interrupt. It is not called for
/// invalid input, which returns its status as in [`compare`]. If `check`
/// never returns `Err`, the result equals [`compare`] exactly.
pub fn compare_with_check<F>(
    t_ref: &[f64],
    y_ref: &[f64],
    t_test: &[f64],
    y_test: &[f64],
    opts: &Options,
    mut check: F,
) -> Result<CompareResult, Cancelled>
where
    F: FnMut() -> Result<(), Cancelled>,
{
    compare_impl(t_ref, y_ref, t_test, y_test, opts, &mut check)
}

/// The comparison pipeline shared by every entry point.
fn compare_impl<C: FnMut() -> Result<(), Cancelled>>(
    t_ref: &[f64],
    y_ref: &[f64],
    t_test: &[f64],
    y_test: &[f64],
    opts: &Options,
    check: &mut C,
) -> Result<CompareResult, Cancelled> {
    // 1. Validate
    if t_ref.len() != y_ref.len() || t_test.len() != y_test.len() {
        return Ok(empty_result(Status::LengthMismatch));
    }
    if t_ref.len() < 2 || t_test.len() < 2 {
        return Ok(empty_result(Status::InsufficientData));
    }
    if !is_non_decreasing(t_ref) || !is_non_decreasing(t_test) {
        return Ok(empty_result(Status::NonMonotonic));
    }

    // 2. Effective x-range: intersect x_range with reference extents.
    let ref_lo = t_ref[0];
    let ref_hi = t_ref[t_ref.len() - 1];
    let test_lo = t_test[0];
    let test_hi = t_test[t_test.len() - 1];
    let eff_lo = opts.x_range.lo.max(ref_lo);
    let eff_hi = opts.x_range.hi.min(ref_hi);
    if eff_lo >= eff_hi {
        return Ok(empty_result(Status::EmptyRange));
    }
    // Also require x_range intersects test data.
    if opts.x_range.lo > test_hi || opts.x_range.hi < test_lo {
        return Ok(empty_result(Status::EmptyRange));
    }

    // 3. The window: reference and test points inside x_range (both time
    //    arrays are non-decreasing and NaN-free here, so the points in
    //    range are contiguous slices).
    let (lo, hi) = (opts.x_range.lo, opts.x_range.hi);
    let w = range_indices(t_ref, lo, hi);
    let tw = range_indices(t_test, lo, hi);
    if w.len() < 2 || tw.len() < 2 {
        return Ok(empty_result(Status::InsufficientData));
    }

    // Checkpoints: before the work starts (an already fired signal does
    // no work), between the phases, and inside every phase whose cost
    // grows with the input: every `CHECK_INTERVAL` elements in the linear
    // loops, by counted work in the corner clean-up.
    let mut cp = Checkpoint::new(check);
    cp.now()?;

    // 4. Tube size from the reference inside the window (the bases of the
    //    range-relative tolerances), then the tube from the reference
    //    extended beyond the window by the x half-widths, so that the tube
    //    over the window is the tube of the whole reference there.
    let tol = &opts.tolerances;
    let dc = get_data_char_checked(&t_ref[w.clone()], &y_ref[w.clone()], &mut cp)?;
    let e = extended_indices(t_ref, w, lo, hi, dc, tol);
    let (tr, yr) = (&t_ref[e.clone()], &y_ref[e]);
    let (hx, hy) = tube_halfwidths_checked(tr, yr, dc, tol, &mut cp)?;
    cp.now()?;
    // Normalize x by the magnitude of the whole reference (O(1): it is
    // sorted), so the corner arithmetic does not depend on the window.
    let mag_x = sorted_magnitude(t_ref);
    let (lx, ly, ux, uy) = build_bounds_checked(tr, yr, &hx, &hy, mag_x, &mut cp)?;

    // 5. Deviations of the test points inside x_range; the arrays keep
    //    length n_test, with deviation 0 outside x_range.
    let (ex, ey) = if tw.len() == t_test.len() {
        compute_errors_checked(t_test, y_test, &lx, &ly, &ux, &uy, &mut cp)?
    } else {
        let (_, eyw) = compute_errors_checked(
            &t_test[tw.clone()],
            &y_test[tw.clone()],
            &lx,
            &ly,
            &ux,
            &uy,
            &mut cp,
        )?;
        let mut ey = vec![0.0_f64; t_test.len()];
        ey[tw].copy_from_slice(&eyw);
        (t_test.to_vec(), ey)
    };

    // 6. classify status
    let status = classify_status(t_ref, t_test, &ey, eff_lo, eff_hi, opts.x_range, &mut cp)?;

    Ok(CompareResult {
        status,
        lower: (lx, ly),
        upper: (ux, uy),
        errors: (ex, ey),
    })
}

/// Allocation-free variant filling caller buffers.
pub fn compare_into(
    t_ref: &[f64],
    y_ref: &[f64],
    t_test: &[f64],
    y_test: &[f64],
    opts: &Options,
    out: &mut Outputs<'_>,
) -> (Status, usize, usize) {
    let r = compare(t_ref, y_ref, t_test, y_test, opts);
    if matches!(
        r.status,
        Status::NonMonotonic
            | Status::LengthMismatch
            | Status::EmptyRange
            | Status::InsufficientData
    ) {
        return (r.status, 0, 0);
    }
    // Size checks.
    if out.lower_x.len() < r.lower.0.len()
        || out.lower_y.len() < r.lower.1.len()
        || out.upper_x.len() < r.upper.0.len()
        || out.upper_y.len() < r.upper.1.len()
        || out.errors_x.len() < r.errors.0.len()
        || out.errors_y.len() < r.errors.1.len()
    {
        return (Status::BufferTooSmall, 0, 0);
    }
    let ln = r.lower.0.len();
    let un = r.upper.0.len();
    out.lower_x[..ln].copy_from_slice(&r.lower.0);
    out.lower_y[..ln].copy_from_slice(&r.lower.1);
    out.upper_x[..un].copy_from_slice(&r.upper.0);
    out.upper_y[..un].copy_from_slice(&r.upper.1);
    out.errors_x[..r.errors.0.len()].copy_from_slice(&r.errors.0);
    out.errors_y[..r.errors.1.len()].copy_from_slice(&r.errors.1);
    (r.status, ln, un)
}

fn empty_result(status: Status) -> CompareResult {
    CompareResult {
        status,
        lower: (Vec::new(), Vec::new()),
        upper: (Vec::new(), Vec::new()),
        errors: (Vec::new(), Vec::new()),
    }
}

/// Classify the outcome of a comparison.
///
/// Implements Plan 02 §3.3 step 7, with coverage judged within the
/// requested x-range:
///
/// 1. Any non-zero deviation `ey[j]` at a test point whose
///    `t_test[j]` lies in the effective x-range `[eff_lo, eff_hi]`
///    (the requested `x_range` intersected with the reference extent)
///    yields [`Status::Fail`]. `Fail` takes precedence over any
///    range asymmetry (Plan 02 Q2 / Plan 02.1 §10 Q7).
/// 2. Otherwise both trajectories' x-extents (`[first, last]` x, not
///    only the samples inside the window) are clipped to `x_range`. If
///    the clipped test extent reaches beyond the clipped reference
///    extent by more than `eps`, return [`Status::MissingReference`].
/// 3. Otherwise, if the clipped reference extent reaches beyond the
///    clipped test extent by more than `eps`, return
///    [`Status::MissingTest`].
/// 4. Otherwise, [`Status::Pass`].
///
/// With the default unbounded `x_range` the clipping is a no-op, so the
/// coverage checks compare the full extents (LBNL corpus behaviour). A
/// window inside the overlap of both trajectories, e.g. reference
/// `0..1`, test `0..1.1`, `x_range = [0, 1]`, is therefore not "missing".
///
/// `eps = 1e-12 * max(|t_ref_max|, |t_test_max|)` guards the range
/// comparisons against floating-point noise when the inputs share
/// identical endpoints.
fn classify_status<C: FnMut() -> Result<(), Cancelled>>(
    t_ref: &[f64],
    t_test: &[f64],
    ey: &[f64],
    eff_lo: f64,
    eff_hi: f64,
    x_range: Range,
    cp: &mut Checkpoint<'_, C>,
) -> Result<Status, Cancelled> {
    // 1. Fail wins: any non-zero deviation inside the effective range.
    let mut fail = false;
    cp.chunks(ey.len(), |r| {
        if !fail {
            fail = r.into_iter().any(|j| {
                let x = t_test[j];
                ey[j] != 0.0 && x >= eff_lo && x <= eff_hi
            });
        }
    })?;
    if fail {
        return Ok(Status::Fail);
    }

    // 2/3. Range-asymmetry checks within the requested x-range.
    let (Some(&tr_lo), Some(&tr_hi)) = (t_ref.first(), t_ref.last()) else {
        return Ok(Status::Pass);
    };
    let (Some(&tt_lo), Some(&tt_hi)) = (t_test.first(), t_test.last()) else {
        return Ok(Status::Pass);
    };
    let eps = 1e-12 * tr_hi.abs().max(tt_hi.abs());
    let (r_lo, r_hi) = (tr_lo.max(x_range.lo), tr_hi.min(x_range.hi));
    let (t_lo, t_hi) = (tt_lo.max(x_range.lo), tt_hi.min(x_range.hi));

    if t_hi > r_hi + eps || t_lo < r_lo - eps {
        return Ok(Status::MissingReference);
    }
    if r_hi > t_hi + eps || r_lo < t_lo - eps {
        return Ok(Status::MissingTest);
    }

    Ok(Status::Pass)
}

#[cfg(test)]
#[path = "window_property.rs"]
mod window_property;

#[cfg(test)]
mod tests {
    use super::*;

    fn opts_loose() -> Options {
        Options {
            tolerances: Tolerances {
                atolx: 0.0,
                atoly: 0.5,
                ltolx: 0.0,
                ltoly: 0.0,
                rtolx: 0.0,
                rtoly: 0.0,
            },
            x_range: Range::default(),
        }
    }

    #[test]
    fn status_pass() {
        let t = [0.0, 1.0, 2.0, 3.0];
        let y = [0.0, 1.0, 2.0, 3.0];
        let tt = [0.0, 1.0, 2.0, 3.0];
        let yt = [0.1, 1.1, 1.9, 2.95];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::Pass);
    }

    #[test]
    fn status_fail() {
        let t = [0.0, 1.0, 2.0, 3.0];
        let y = [0.0, 1.0, 2.0, 3.0];
        let tt = [0.0, 1.0, 2.0, 3.0];
        let yt = [10.0, 10.0, 10.0, 10.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::Fail);
    }

    #[test]
    fn status_missing_reference() {
        // Test extends beyond reference x-range; no out-of-tube
        // points inside the common range → MissingReference.
        let t = [1.0, 2.0, 3.0];
        let y = [1.0, 2.0, 3.0];
        let tt = [0.0, 1.0, 2.0, 3.0, 4.0];
        let yt = [0.5, 1.0, 2.0, 3.0, 3.5];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::MissingReference);
    }

    #[test]
    fn status_missing_test() {
        // Reference extends beyond test x-range; no out-of-tube
        // points inside the common range → MissingTest.
        let t = [0.0, 1.0, 2.0, 3.0, 4.0];
        let y = [0.0, 1.0, 2.0, 3.0, 4.0];
        let tt = [1.0, 2.0, 3.0];
        let yt = [1.0, 2.0, 3.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::MissingTest);
    }

    #[test]
    fn classify_fail_wins_over_range_mismatch() {
        // Test extends beyond reference AND has an out-of-tube point
        // inside the common range. Fail wins (Plan 02 §3.3 step 7).
        let t = [1.0, 2.0, 3.0];
        let y = [1.0, 2.0, 3.0];
        let tt = [0.0, 1.0, 2.0, 3.0, 4.0];
        let yt = [0.5, 10.0, 10.0, 10.0, 3.5];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::Fail);
    }

    #[test]
    fn classify_missing_reference_simple() {
        let t = [0.0, 1.0];
        let y = [0.0, 0.0];
        let tt = [0.0, 1.0, 2.0];
        let yt = [0.0, 0.0, 0.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::MissingReference);
    }

    #[test]
    fn classify_missing_test_simple() {
        let t = [0.0, 1.0, 2.0];
        let y = [0.0, 0.0, 0.0];
        let tt = [0.0, 1.0];
        let yt = [0.0, 0.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::MissingTest);
    }

    #[test]
    fn classify_pass_when_ranges_align() {
        let t = [0.0, 1.0, 2.0];
        let y = [0.0, 0.0, 0.0];
        let tt = [0.0, 1.0, 2.0];
        let yt = [0.0, 0.0, 0.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::Pass);
    }

    fn opts_loose_range(lo: f64, hi: f64) -> Options {
        Options {
            x_range: Range { lo, hi },
            ..opts_loose()
        }
    }

    #[test]
    fn coverage_judged_within_x_range_missing_reference() {
        // Test covers 0..1.1, reference 0..1: unbounded range reports the
        // asymmetry, but an x_range inside the overlap compares cleanly.
        let t = [0.0, 0.5, 1.0];
        let y = [0.0, 0.5, 1.0];
        let tt = [0.0, 0.25, 0.5, 0.75, 1.0, 1.1];
        let yt = [0.0, 0.25, 0.5, 0.75, 1.0, 1.1];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::MissingReference);
        let r = compare(&t, &y, &tt, &yt, &opts_loose_range(0.0, 1.0));
        assert_eq!(r.status, Status::Pass);
        // The window still extends past the reference: still missing.
        let r = compare(&t, &y, &tt, &yt, &opts_loose_range(0.0, 1.05));
        assert_eq!(r.status, Status::MissingReference);
        // Unbounded below, clipped above.
        let r = compare(&t, &y, &tt, &yt, &opts_loose_range(f64::NEG_INFINITY, 1.0));
        assert_eq!(r.status, Status::Pass);
    }

    #[test]
    fn coverage_judged_within_x_range_missing_test() {
        // Reference covers -1..2, test 0..1 (sampled more coarsely than
        // the window bounds): the window [0, 1] is covered by both.
        let t = [-1.0, 0.0, 1.0, 2.0];
        let y = [-1.0, 0.0, 1.0, 2.0];
        let tt = [0.0, 0.5, 1.0];
        let yt = [0.0, 0.5, 1.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::MissingTest);
        let r = compare(&t, &y, &tt, &yt, &opts_loose_range(0.0, 1.0));
        assert_eq!(r.status, Status::Pass);
        let r = compare(&t, &y, &tt, &yt, &opts_loose_range(-0.5, 1.0));
        assert_eq!(r.status, Status::MissingTest);
    }

    #[test]
    fn coverage_window_not_aligned_with_samples() {
        // The test trajectory spans past the window even though it has no
        // sample exactly at the window bound: coverage uses the extent.
        let t = [0.0, 0.5, 1.0];
        let y = [0.0, 0.0, 0.0];
        let tt = [0.0, 0.3, 0.7, 1.2];
        let yt = [0.0, 0.0, 0.0, 0.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose_range(0.0, 1.0));
        assert_eq!(r.status, Status::Pass);
    }

    #[test]
    fn empty_range_status() {
        let t = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 2.0];
        let opts = Options {
            tolerances: Tolerances::ZERO,
            x_range: Range {
                lo: 100.0,
                hi: 200.0,
            },
        };
        let r = compare(&t, &y, &t, &y, &opts);
        assert_eq!(r.status, Status::EmptyRange);
    }

    #[test]
    fn non_monotonic_status() {
        let t = [0.0, 2.0, 1.0];
        let y = [0.0, 1.0, 2.0];
        let tt = [0.0, 1.0, 2.0];
        let r = compare(&t, &y, &tt, &y, &opts_loose());
        assert_eq!(r.status, Status::NonMonotonic);
    }

    #[test]
    fn length_mismatch_status() {
        let t = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0];
        let tt = [0.0, 1.0];
        let yt = [0.0, 1.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::LengthMismatch);
    }

    #[test]
    fn insufficient_data_status() {
        let t = [0.0];
        let y = [0.0];
        let tt = [0.0, 1.0];
        let yt = [0.0, 1.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::InsufficientData);
    }

    #[test]
    fn buffer_too_small_status() {
        let t = [0.0, 1.0, 2.0, 3.0];
        let y = [0.0, 1.0, 2.0, 3.0];
        let mut lx = [0.0; 1];
        let mut ly = [0.0; 1];
        let mut ux = [0.0; 1];
        let mut uy = [0.0; 1];
        let mut ex = [0.0; 4];
        let mut ey = [0.0; 4];
        let mut out = Outputs {
            lower_x: &mut lx,
            lower_y: &mut ly,
            upper_x: &mut ux,
            upper_y: &mut uy,
            errors_x: &mut ex,
            errors_y: &mut ey,
        };
        let (s, _, _) = compare_into(&t, &y, &t, &y, &opts_loose(), &mut out);
        assert_eq!(s, Status::BufferTooSmall);
    }

    /// The element-by-element filter `range_indices` replaced.
    fn filter_indices(x: &[f64], lo: f64, hi: f64) -> Vec<usize> {
        (0..x.len()).filter(|&i| x[i] >= lo && x[i] <= hi).collect()
    }

    #[test]
    fn range_indices_selects_what_the_filter_selected() {
        let xs: [&[f64]; 5] = [
            &[0.0, 1.0, 2.0, 3.0],
            &[0.0, 1.0, 1.0, 1.0, 2.0, 2.0],
            &[-0.0, 0.0, 0.0, 5.0],
            &[f64::NEG_INFINITY, -1.0, 1.0, f64::INFINITY],
            &[3.0, 3.0],
        ];
        let bounds = [
            f64::NEG_INFINITY,
            -2.0,
            -1.0,
            -0.0,
            0.0,
            0.5,
            1.0,
            2.0,
            3.0,
            4.0,
            f64::INFINITY,
            f64::NAN,
        ];
        for x in xs {
            for &lo in &bounds {
                for &hi in &bounds {
                    let r: Vec<usize> = range_indices(x, lo, hi).collect();
                    assert_eq!(r, filter_indices(x, lo, hi), "x={x:?} lo={lo} hi={hi}");
                }
            }
        }
    }

    /// The linear phases (half-widths, corner curves, deviations,
    /// classification) consult the check every `CHECK_INTERVAL` elements,
    /// not only at phase boundaries, so even a comparison without loops to
    /// remove can be stopped between any two chunks of work.
    #[test]
    fn linear_phases_are_checked_per_chunk() {
        use crate::cancel::CHECK_INTERVAL;
        let n = 8 * CHECK_INTERVAL;
        let t: Vec<f64> = (0..n).map(|i| i as f64).collect();
        let y: Vec<f64> = t.iter().map(|v| v * 0.5).collect();
        let opts = Options::default();
        let mut calls = 0usize;
        let r = compare_with_check(&t, &y, &t, &y, &opts, || {
            calls += 1;
            Ok(())
        })
        .expect("never cancelled");
        assert_eq!(r.status, Status::Pass);
        // Phase boundaries plus the corner clean-up alone give fewer than
        // 30 checks here; every linear pass over n points adds 8.
        assert!(calls >= 80, "checks: {calls}");

        // A check that fires at any of them stops the comparison.
        for k in [1, 2, calls / 4, calls / 2, calls - 1, calls] {
            let mut seen = 0usize;
            let res = compare_with_check(&t, &y, &t, &y, &opts, || {
                seen += 1;
                if seen >= k {
                    Err(Cancelled::Requested)
                } else {
                    Ok(())
                }
            });
            assert!(matches!(res, Err(Cancelled::Requested)), "k={k}");
            assert_eq!(seen, k);
        }
    }
}
