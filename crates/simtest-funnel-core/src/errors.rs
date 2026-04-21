//! Error array computation: linearly interpolate lower/upper onto
//! test x-points and record signed deviations outside the tube.
//!
//! Port of the interpolation + compare logic from
//! [tube.c](/home/iakovn/projects/funnel/src/tube.c).

/// Linearly interpolate a (source_x, source_y) curve onto `target_x`,
/// clamping values outside `source_x` to the endpoint y values.
///
/// Matches the behaviour of the C reference's error-array loop, which
/// evaluates errors at every test point — including points past the
/// end of the reference trajectory — by extending the last bound
/// value. This intentionally differs from the C's `realloc`-based
/// implementation, which reads past a shortened buffer (undefined
/// behaviour); clamping produces the same in-bounds results without
/// the UB.
fn interpolate_clamped(source_x: &[f64], source_y: &[f64], target_x: &[f64]) -> Vec<f64> {
    debug_assert_eq!(source_x.len(), source_y.len());
    if source_x.is_empty() {
        return Vec::new();
    }
    let src_len = source_x.len();
    let mut out = Vec::with_capacity(target_x.len());
    let mut j: usize = 1.min(src_len - 1);
    for &x in target_x {
        if x <= source_x[0] {
            out.push(source_y[0]);
            continue;
        }
        if x >= source_x[src_len - 1] {
            out.push(source_y[src_len - 1]);
            continue;
        }
        while j + 1 < src_len && source_x[j] < x {
            j += 1;
        }
        let (x0, x1) = (source_x[j - 1], source_x[j]);
        let (y0, y1) = (source_y[j - 1], source_y[j]);
        if (x1 - x0).abs() < 1e-10 {
            out.push(y0);
        } else {
            out.push(y0 + (y1 - y0) * (x - x0) / (x1 - x0));
        }
    }
    out
}

/// For each test point compute the signed deviation (positive above
/// upper, negative below lower). Bounds are clamped to their endpoint
/// y-values for x outside the bound x-range; this mirrors the C
/// reference, which scores every test point.
///
/// Returns vectors of length `t_test.len()` where `ex[j] = t_test[j]`.
pub(crate) fn compute_errors(
    t_test: &[f64],
    y_test: &[f64],
    lower_x: &[f64],
    lower_y: &[f64],
    upper_x: &[f64],
    upper_y: &[f64],
) -> (Vec<f64>, Vec<f64>) {
    debug_assert_eq!(t_test.len(), y_test.len());
    let n = t_test.len();
    let mut ex = vec![0.0_f64; n];
    let mut ey = vec![0.0_f64; n];
    if lower_x.is_empty() || upper_x.is_empty() {
        return (ex, ey);
    }
    let low = interpolate_clamped(lower_x, lower_y, t_test);
    let up = interpolate_clamped(upper_x, upper_y, t_test);
    for j in 0..n {
        ex[j] = t_test[j];
        let y = y_test[j];
        let l = low[j];
        let u = up[j];
        if y > u {
            ey[j] = y - u;
        } else if y < l {
            ey[j] = y - l;
        } else {
            ey[j] = 0.0;
        }
    }
    (ex, ey)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_in_tube_zeros() {
        let lx = vec![0.0, 1.0];
        let ly = vec![-1.0, -1.0];
        let ux = vec![0.0, 1.0];
        let uy = vec![1.0, 1.0];
        let t = vec![0.25, 0.5, 0.75];
        let y = vec![0.0, 0.2, -0.5];
        let (ex, ey) = compute_errors(&t, &y, &lx, &ly, &ux, &uy);
        for v in &ey {
            assert_eq!(*v, 0.0);
        }
        assert_eq!(ex, t);
    }

    #[test]
    fn above_upper_positive_diff() {
        let lx = vec![0.0, 1.0];
        let ly = vec![-1.0, -1.0];
        let ux = vec![0.0, 1.0];
        let uy = vec![1.0, 1.0];
        let t = vec![0.5];
        let y = vec![2.5];
        let (_ex, ey) = compute_errors(&t, &y, &lx, &ly, &ux, &uy);
        assert_eq!(ey, vec![1.5]); // 2.5 - 1.0
    }

    #[test]
    fn below_lower_negative_diff() {
        let lx = vec![0.0, 1.0];
        let ly = vec![-1.0, -1.0];
        let ux = vec![0.0, 1.0];
        let uy = vec![1.0, 1.0];
        let t = vec![0.5];
        let y = vec![-2.5];
        let (_ex, ey) = compute_errors(&t, &y, &lx, &ly, &ux, &uy);
        assert_eq!(ey, vec![-1.5]); // -2.5 - (-1.0)
    }
}
