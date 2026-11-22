//! Public `compare` / `compare_into` API wiring the tube-size,
//! corner-enumeration, and error stages together.

use crate::cancel::{CancelToken, Cancelled, Checkpoint};
use crate::corners::build_bounds_checked;
use crate::errors::compute_errors_checked;
use crate::options::{Options, Range};
use crate::status::Status;
use crate::tube::{get_data_char_checked, tube_halfwidths_checked};

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
    /// Signed deviations; zero where in-tube or outside effective range.
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
    /// Lower bound `(x, y)`.
    pub lower: (Vec<f64>, Vec<f64>),
    /// Upper bound `(x, y)`.
    pub upper: (Vec<f64>, Vec<f64>),
    /// Errors `(x, y)`. `y` is a signed deviation.
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

/// Full comparison returning owned vectors.
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

    // 3. Restrict the reference to x_range (both time arrays are
    //    non-decreasing and NaN-free here, so the points in range are a
    //    contiguous slice). Only the count of test points in range
    //    matters: errors are computed on the full test arrays so that
    //    `errors_x`/`errors_y` keep length `n_test`.
    let r = range_indices(t_ref, opts.x_range.lo, opts.x_range.hi);
    let (tr, yr) = (&t_ref[r.clone()], &y_ref[r]);
    if tr.len() < 2 || range_indices(t_test, opts.x_range.lo, opts.x_range.hi).len() < 2 {
        return Ok(empty_result(Status::InsufficientData));
    }

    // Checkpoints: before the work starts (an already fired signal does
    // no work), between the phases, and inside every phase whose cost
    // grows with the input: every `CHECK_INTERVAL` elements in the linear
    // loops, by counted work in the corner clean-up.
    let mut cp = Checkpoint::new(check);
    cp.now()?;

    // 4. tube size + bounds
    let dc = get_data_char_checked(tr, yr, &mut cp)?;
    let (hx, hy) = tube_halfwidths_checked(tr, yr, dc, &opts.tolerances, &mut cp)?;
    cp.now()?;
    let (lx, ly, ux, uy) = build_bounds_checked(tr, yr, &hx, &hy, dc.mag_x, &mut cp)?;

    // 5. errors: computed over original t_test / y_test arrays (caller sees
    //    length-n_test output); deviations are non-zero only inside eff range.
    let (ex, ey) = compute_errors_checked(t_test, y_test, &lx, &ly, &ux, &uy, &mut cp)?;

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
mod tests {
    use super::*;
    use crate::options::Tolerances;

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
