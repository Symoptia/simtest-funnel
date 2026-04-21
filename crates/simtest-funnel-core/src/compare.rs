//! Public `compare` / `compare_into` API wiring the tube-size,
//! corner-enumeration, and error stages together.

use crate::corners::build_bounds;
use crate::errors::compute_errors;
use crate::options::Options;
use crate::status::Status;
use crate::tube::{get_data_char, tube_halfwidths};

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

fn filter_to_range(x: &[f64], y: &[f64], lo: f64, hi: f64) -> (Vec<f64>, Vec<f64>) {
    let mut ox = Vec::new();
    let mut oy = Vec::new();
    for i in 0..x.len() {
        if x[i] >= lo && x[i] <= hi {
            ox.push(x[i]);
            oy.push(y[i]);
        }
    }
    (ox, oy)
}

/// Full comparison returning owned vectors.
pub fn compare(
    t_ref: &[f64],
    y_ref: &[f64],
    t_test: &[f64],
    y_test: &[f64],
    opts: &Options,
) -> CompareResult {
    // 1. Validate
    if t_ref.len() != y_ref.len() || t_test.len() != y_test.len() {
        return empty_result(Status::LengthMismatch);
    }
    if t_ref.len() < 2 || t_test.len() < 2 {
        return empty_result(Status::InsufficientData);
    }
    if !is_non_decreasing(t_ref) || !is_non_decreasing(t_test) {
        return empty_result(Status::NonMonotonic);
    }

    // 2. Effective x-range: intersect x_range with reference extents.
    let ref_lo = t_ref[0];
    let ref_hi = t_ref[t_ref.len() - 1];
    let test_lo = t_test[0];
    let test_hi = t_test[t_test.len() - 1];
    let eff_lo = opts.x_range.lo.max(ref_lo);
    let eff_hi = opts.x_range.hi.min(ref_hi);
    if eff_lo >= eff_hi {
        return empty_result(Status::EmptyRange);
    }
    // Also require x_range intersects test data.
    if opts.x_range.lo > test_hi || opts.x_range.hi < test_lo {
        return empty_result(Status::EmptyRange);
    }

    // 3. Filter reference to x_range.
    let (tr, yr) = filter_to_range(t_ref, y_ref, opts.x_range.lo, opts.x_range.hi);
    let (tt, yt) = filter_to_range(t_test, y_test, opts.x_range.lo, opts.x_range.hi);
    if tr.len() < 2 || tt.len() < 2 {
        return empty_result(Status::InsufficientData);
    }
    // `yt` filtered view is not consumed further; errors are computed on the
    // full test arrays so that `errors_x`/`errors_y` keep length `n_test`.
    let _ = yt;

    // 4. tube size + bounds
    let dc = get_data_char(&tr, &yr);
    let (hx, hy) = tube_halfwidths(&tr, &yr, dc, &opts.tolerances);
    let (lx, ly, ux, uy) = build_bounds(&tr, &yr, &hx, &hy, dc.mag_x);

    // 5. errors: computed over original t_test / y_test arrays (caller sees
    //    length-n_test output); deviations are non-zero only inside eff range.
    let (ex, ey) = compute_errors(t_test, y_test, &lx, &ly, &ux, &uy);

    // 6. classify status
    let status = classify_status(t_ref, t_test, &ex, &ey, eff_lo, eff_hi);

    CompareResult {
        status,
        lower: (lx, ly),
        upper: (ux, uy),
        errors: (ex, ey),
    }
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

fn classify_status(
    _t_ref: &[f64],
    _t_test: &[f64],
    _ex: &[f64],
    ey: &[f64],
    _eff_lo: f64,
    _eff_hi: f64,
) -> Status {
    // Match the C reference: status is driven solely by the errors
    // array. Any nonzero deviation (at any x, including test points
    // that land beyond the reference range and are scored against the
    // clamped bound) is a Fail; otherwise Pass.
    //
    // The `MissingReference` / `MissingTest` variants in `Status`
    // remain available for higher-level callers (e.g. the Python
    // DataFrame wrapper) that want to flag range mismatches
    // explicitly, but the core comparison never returns them.
    for &e in ey {
        if e != 0.0 {
            return Status::Fail;
        }
    }
    Status::Pass
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::options::{Range, Tolerances};

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
        // Test extends beyond reference x-range; the clamped bound
        // value at the endpoint matches the interpolated test y
        // exactly so no Fail is raised — the implementation keeps
        // parity with the C reference, which simply reports Pass in
        // this scenario. Higher-level callers can opt in to range
        // enforcement with a dedicated check.
        let t = [1.0, 2.0, 3.0];
        let y = [1.0, 2.0, 3.0];
        let tt = [0.0, 1.0, 2.0, 3.0, 4.0];
        let yt = [0.5, 1.0, 2.0, 3.0, 3.5];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::Pass);
    }

    #[test]
    fn status_missing_test() {
        // Reference extends beyond test x-range; same rationale as
        // above — status is Pass, not MissingTest.
        let t = [0.0, 1.0, 2.0, 3.0, 4.0];
        let y = [0.0, 1.0, 2.0, 3.0, 4.0];
        let tt = [1.0, 2.0, 3.0];
        let yt = [1.0, 2.0, 3.0];
        let r = compare(&t, &y, &tt, &yt, &opts_loose());
        assert_eq!(r.status, Status::Pass);
    }

    #[test]
    fn empty_range_status() {
        let t = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 2.0];
        let opts = Options {
            tolerances: Tolerances::default(),
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
}
