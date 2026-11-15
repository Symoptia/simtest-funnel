//! Rectangle corner enumeration + backward-loop removal.
//!
//! Direct port of
//! [algorithmRectangle.c](/home/iakovn/projects/funnel/src/algorithmRectangle.c)
//! from the LBNL Funnel C reference, preserving the normalize /
//! corner-insertion / `removeLoop` pipeline so the generated lower
//! and upper curves match the C output bit-for-bit (modulo
//! floating-point ordering).

/// Curve-indicator used by `removeLoop`: `+1` for upper, `-1` for
/// lower.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Curve {
    Lower,
    Upper,
}

#[inline]
fn equ(a: f64, b: f64) -> bool {
    (a - b).abs() < 1e-10
}

#[inline]
fn sign(a: f64) -> i32 {
    if a > 0.0 {
        1
    } else if a < 0.0 {
        -1
    } else {
        0
    }
}

#[inline]
fn normalize(arr: &mut [f64], mag: f64) {
    if mag > 1e-5 {
        for v in arr.iter_mut() {
            *v /= mag;
        }
    }
}

#[inline]
fn denormalize(arr: &mut [f64], mag: f64) {
    if mag > 1e-5 {
        for v in arr.iter_mut() {
            *v *= mag;
        }
    }
}

/// Build lower + upper tube curves from a reference trajectory and
/// per-point half-widths. Returns `(lower_x, lower_y, upper_x,
/// upper_y)`.
pub(crate) fn build_bounds(
    t_ref: &[f64],
    y_ref: &[f64],
    half_x: &[f64],
    half_y: &[f64],
    mag_x: f64,
) -> (Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>) {
    // Work on normalized x copies.
    let mut x_norm: Vec<f64> = t_ref.to_vec();
    let mut hx_norm: Vec<f64> = half_x.to_vec();
    normalize(&mut x_norm, mag_x);
    normalize(&mut hx_norm, mag_x);

    let (mut lx, mut ly) = build_corner_curve(&x_norm, y_ref, &hx_norm, half_y, Curve::Lower);
    let (mut ux, mut uy) = build_corner_curve(&x_norm, y_ref, &hx_norm, half_y, Curve::Upper);

    remove_loop(&mut lx, &mut ly, Curve::Lower);
    remove_loop(&mut ux, &mut uy, Curve::Upper);

    denormalize(&mut lx, mag_x);
    denormalize(&mut ux, mag_x);

    (lx, ly, ux, uy)
}

/// Enumerate corners for either the lower (`sgn=-1`) or upper
/// (`sgn=+1`) curve. Mirrors `getLower`/`getUpper` from the C
/// reference.
fn build_corner_curve(
    x_norm: &[f64],
    y_ref: &[f64],
    hx_norm: &[f64],
    hy: &[f64],
    curve: Curve,
) -> (Vec<f64>, Vec<f64>) {
    let n = x_norm.len();
    // sign of y-offset for this curve: lower -> -1, upper -> +1.
    let y_sgn: f64 = match curve {
        Curve::Lower => -1.0,
        Curve::Upper => 1.0,
    };

    let mut cx: Vec<f64> = Vec::with_capacity(4 * n.max(2));
    let mut cy: Vec<f64> = Vec::with_capacity(4 * n.max(2));

    // ----- 1.1 Start: ignore leading identical points -----
    let mut b = 0usize;
    while b + 1 < n && equ(x_norm[b], x_norm[b + 1]) && equ(y_ref[b], y_ref[b + 1]) {
        b += 1;
    }

    // For lower: "down left" = (x - hx, y - hy). For upper: "top left" =
    // (x - hx, y + hy).
    cx.push(x_norm[b] - hx_norm[b]);
    cy.push(y_ref[b] + y_sgn * hy[b]);

    if b + 1 < n {
        // slopes of reference curve (initialization)
        let mut s0 = sign(y_ref[b + 1] - y_ref[b]);
        let mut m0 = if !equ(x_norm[b + 1], x_norm[b]) {
            (y_ref[b + 1] - y_ref[b]) / (x_norm[b + 1] - x_norm[b])
        } else if s0 > 0 {
            1e15
        } else {
            -1e15
        };

        // Initial "other" corner based on curve type:
        //  - lower: add down-right if s0 == +1
        //  - upper: add top-right if s0 == -1
        let initial_other = match curve {
            Curve::Lower => s0 == 1,
            Curve::Upper => s0 == -1,
        };
        if initial_other {
            cx.push(x_norm[b] + hx_norm[b]);
            cy.push(y_ref[b] + y_sgn * hy[b]);
        }

        // ----- 1.2 iterate -----
        let mut i = b + 1;
        while i < n.saturating_sub(1) {
            // ignore identical points
            if equ(x_norm[i], x_norm[i + 1]) && equ(y_ref[i], y_ref[i + 1]) {
                i += 1;
                continue;
            }
            let s1 = sign(y_ref[i + 1] - y_ref[i]);
            let m1 = if !equ(x_norm[i + 1], x_norm[i]) {
                (y_ref[i + 1] - y_ref[i]) / (x_norm[i + 1] - x_norm[i])
            } else if s1 > 0 {
                1e15
            } else {
                -1e15
            };

            if !equ(m0, m1) {
                // Corner insertion patterns — distinct for lower vs upper.
                match curve {
                    Curve::Lower => {
                        if s0 != -1 && s1 != -1 {
                            // down right
                            cx.push(x_norm[i] + hx_norm[i]);
                            cy.push(y_ref[i] - hy[i]);
                        } else if s0 != 1 && s1 != 1 {
                            // down left
                            cx.push(x_norm[i] - hx_norm[i]);
                            cy.push(y_ref[i] - hy[i]);
                        } else if s0 == -1 && s1 == 1 {
                            cx.push(x_norm[i] - hx_norm[i]);
                            cy.push(y_ref[i] - hy[i]);
                            cx.push(x_norm[i] + hx_norm[i]);
                            cy.push(y_ref[i] - hy[i]);
                        } else if s0 == 1 && s1 == -1 {
                            cx.push(x_norm[i] + hx_norm[i]);
                            cy.push(y_ref[i] - hy[i]);
                            cx.push(x_norm[i] - hx_norm[i]);
                            cy.push(y_ref[i] - hy[i]);
                        }
                    }
                    Curve::Upper => {
                        if s0 != -1 && s1 != -1 {
                            // top left
                            cx.push(x_norm[i] - hx_norm[i]);
                            cy.push(y_ref[i] + hy[i]);
                        } else if s0 != 1 && s1 != 1 {
                            // top right
                            cx.push(x_norm[i] + hx_norm[i]);
                            cy.push(y_ref[i] + hy[i]);
                        } else if s0 == 1 && s1 == -1 {
                            cx.push(x_norm[i] - hx_norm[i]);
                            cy.push(y_ref[i] + hy[i]);
                            cx.push(x_norm[i] + hx_norm[i]);
                            cy.push(y_ref[i] + hy[i]);
                        } else if s0 == -1 && s1 == 1 {
                            cx.push(x_norm[i] + hx_norm[i]);
                            cy.push(y_ref[i] + hy[i]);
                            cx.push(x_norm[i] - hx_norm[i]);
                            cy.push(y_ref[i] + hy[i]);
                        }
                    }
                }

                // Remove last added points if next reference's horizontal
                // tube edge lies at the same y.
                let len = cy.len();
                let last_y = cy[len - 1];
                let next_edge = y_ref[i + 1] + y_sgn * hy[i + 1];
                if equ(next_edge, last_y) {
                    if s0 * s1 == -1 && len >= 3 && equ(cy[len - 3], last_y) {
                        // two-point undo
                        cx.pop();
                        cy.pop();
                        cx.pop();
                        cy.pop();
                    } else if s0 * s1 != -1 && len >= 2 && equ(cy[len - 2], last_y) {
                        cx.pop();
                        cy.pop();
                    }
                }
            }
            s0 = s1;
            m0 = m1;
            i += 1;
        }

        // ----- 1.3 End corner -----
        let add_end_left = match curve {
            Curve::Lower => s0 == -1,
            Curve::Upper => s0 == 1,
        };
        if add_end_left {
            cx.push(x_norm[n - 1] - hx_norm[n - 1]);
            cy.push(y_ref[n - 1] + y_sgn * hy[n - 1]);
        }
    }

    // Down/top right end point
    cx.push(x_norm[n - 1] + hx_norm[n - 1]);
    cy.push(y_ref[n - 1] + y_sgn * hy[n - 1]);

    (cx, cy)
}

/// Remove backward-going segments, inserting intersection points.
/// Direct port of `removeLoop`.
fn remove_loop(x: &mut Vec<f64>, y: &mut Vec<f64>, curve: Curve) {
    let cur_ind: i32 = match curve {
        Curve::Lower => -1,
        Curve::Upper => 1,
    };
    let mut j: usize = 1;
    while j + 2 < x.len() {
        if x[j + 1] < x[j] {
            // ===== 1. find i, k =====
            let mut i: usize = j;
            let mut i_previous: usize = i;

            // Find i_s such that X[i_s - 1] <= X[j+1] < X[i_s]
            while i > 0 && x[j + 1] < x[i - 1] {
                i -= 1;
            }
            let mut k_max: usize = j + 1;
            while k_max < x.len() - 1 && x[k_max] < x[j] {
                k_max += 1;
            }

            let mut k: usize = j + 1;
            // `y_intp` is the interpolated y at X[k] on segment (i-1, i)
            let mut y_intp: f64 = if i == 0 { y[0] } else { y[i - 1] };

            loop {
                let cond = if cur_ind == -1 {
                    y_intp < y[k]
                } else {
                    y[k] < y_intp
                };
                if !cond || k >= k_max {
                    break;
                }
                i_previous = i;
                k += 1;
                // advance i
                while i < j {
                    let advance = x[i] < x[k]
                        || (cur_ind == -1
                            && equ(x[i], x[k])
                            && y[i] < y[k]
                            && !(k + 1 < x.len() && equ(x[k], x[k + 1]) && y[k + 1] < y[k]))
                        || (cur_ind == 1
                            && equ(x[i], x[k])
                            && y[i] > y[k]
                            && !(k + 1 < x.len() && equ(x[k], x[k + 1]) && y[k + 1] > y[k]));
                    if !advance {
                        break;
                    }
                    i += 1;
                }
                // linear interpolation of y at X[k] on segment (i-1, i)
                if i == 0 {
                    y_intp = y[0];
                } else if !equ(x[i], x[i - 1]) {
                    y_intp = (y[i] - y[i - 1]) / (x[i] - x[i - 1]) * (x[k] - x[i - 1]) + y[i - 1];
                } else {
                    y_intp = y[i];
                }
            }

            // Regular case: i = iPrevious - 1; special case: i = iPrevious.
            i = if i_previous > 1 {
                i_previous - 1
            } else {
                i_previous
            };
            // linear interpolation of y at X[i] on segment (k-1, k)
            if k >= 1 && !equ(x[k], x[k - 1]) {
                y_intp = (y[k] - y[k - 1]) / (x[k] - x[k - 1]) * (x[i] - x[k - 1]) + y[k - 1];
            }
            // Advance i
            loop {
                let cond = if k >= 1 && !equ(x[k], x[k - 1]) {
                    if cur_ind == -1 {
                        y[i] < y_intp
                    } else {
                        y_intp < y[i]
                    }
                } else if k >= 1 {
                    x[i] < x[k]
                } else {
                    false
                };
                if !cond {
                    break;
                }
                i += 1;
                if i >= x.len() {
                    break;
                }
                if k >= 1 && !equ(x[k], x[k - 1]) {
                    y_intp = (y[k] - y[k - 1]) / (x[k] - x[k - 1]) * (x[i] - x[k - 1]) + y[k - 1];
                }
            }

            // ===== 2. intersection point =====
            let (mut ix, mut iy, mut add_point) = (0.0, 0.0, true);
            if k == 0 || i == 0 || (equ(x[i], x[i - 1]) && equ(x[k], x[k - 1])) {
                add_point = false;
            } else if equ(x[i], x[i - 1]) {
                ix = x[i];
                iy = y[k - 1] + ((x[i] - x[k - 1]) * (y[k] - y[k - 1])) / (x[k] - x[k - 1]);
            } else if equ(x[k], x[k - 1]) {
                ix = x[k];
                iy = y[i - 1] + ((x[k] - x[i - 1]) * (y[i] - y[i - 1])) / (x[i] - x[i - 1]);
            } else {
                let a1 = (y[i] - y[i - 1]) / (x[i] - x[i - 1]);
                let a2 = (y[k] - y[k - 1]) / (x[k] - x[k - 1]);
                if !equ(a1, a2) {
                    ix = (a1 * x[i - 1] - a2 * x[k - 1] - y[i - 1] + y[k - 1]) / (a1 - a2);
                    if a1.abs() > a2.abs() {
                        iy = a2 * (ix - x[k - 1]) + y[k - 1];
                    } else {
                        iy = a1 * (ix - x[i - 1]) + y[i - 1];
                    }
                } else {
                    add_point = false;
                }
            }

            // ===== 3. Delete points i..=k-1 =====
            if k > i {
                x.drain(i..k);
                y.drain(i..k);
            }
            // ===== 4. Add intersection point =====
            if add_point && i < x.len() {
                if !(equ(x[i], ix) && equ(y[i], iy)) {
                    x.insert(i, ix);
                    y.insert(i, iy);
                }
            } else if add_point {
                x.push(ix);
                y.push(iy);
            }

            // ===== 5. set j = i =====
            j = i;

            // ===== 6. Delete doubled points =====
            if i >= 1 && i < x.len() && equ(x[i - 1], x[i]) && equ(y[i - 1], y[i]) {
                x.remove(i);
                y.remove(i);
                j = i.saturating_sub(1);
            }
        }
        j += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tube::{get_data_char, tube_halfwidths};

    fn bounds_default(t: &[f64], y: &[f64]) -> (Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>) {
        let dc = get_data_char(t, y);
        let tol = crate::options::Tolerances {
            atolx: 0.0,
            atoly: 0.0,
            ltolx: 0.0,
            ltoly: 0.0,
            rtolx: 2e-3,
            rtoly: 2e-3,
        };
        let (hx, hy) = tube_halfwidths(t, y, dc, &tol);
        build_bounds(t, y, &hx, &hy, dc.mag_x)
    }

    #[test]
    fn monotonic_reference_noop() {
        let t = [0.0, 1.0, 2.0, 3.0, 4.0];
        let y = [0.0, 1.0, 2.0, 3.0, 4.0];
        let (lx, ly, ux, uy) = bounds_default(&t, &y);
        assert!(lx.len() >= 2);
        assert!(ux.len() >= 2);
        // lower envelope stays strictly below reference, upper strictly above,
        // at the interior of t.
        // Simple invariant: curves are non-empty and finite.
        for v in lx.iter().chain(ly.iter()).chain(ux.iter()).chain(uy.iter()) {
            assert!(v.is_finite());
        }
    }

    #[test]
    fn slope_change_inserts_corners() {
        // triangular reference: slope changes at the apex
        let t = [0.0, 1.0, 2.0];
        let y = [0.0, 1.0, 0.0];
        let (lx, _ly, ux, _uy) = bounds_default(&t, &y);
        // Expect more corner points than reference (corners inserted
        // at the apex).
        assert!(ux.len() >= 4);
        assert!(lx.len() >= 3);
    }

    #[test]
    fn backward_loop_removed() {
        // Pick a case where corner algorithm produces a backward-going
        // segment: saw-tooth shape.
        let t = [0.0, 0.5, 1.0, 1.5, 2.0];
        let y = [0.0, 1.0, 0.0, 1.0, 0.0];
        let (lx, _ly, ux, _uy) = bounds_default(&t, &y);
        // Monotonic non-decreasing x after removal (with small eps for
        // identical corners).
        for w in ux.windows(2) {
            assert!(w[0] <= w[1] + 1e-12, "upper x not monotone: {:?}", ux);
        }
        for w in lx.windows(2) {
            assert!(w[0] <= w[1] + 1e-12, "lower x not monotone: {:?}", lx);
        }
    }
}
