//! Rectangle corner enumeration + backward-loop removal.
//!
//! Direct port of
//! [algorithmRectangle.c](/home/iakovn/projects/funnel/src/algorithmRectangle.c)
//! from the LBNL Funnel C reference, preserving the normalize /
//! corner-insertion / `removeLoop` pipeline so the generated lower
//! and upper curves match the C output bit-for-bit (modulo
//! floating-point ordering).

#[cfg(test)]
use crate::cancel::never_cancelled;
use crate::cancel::{Cancelled, Checkpoint};

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

/// Lower and upper tube curves `(lower_x, lower_y, upper_x, upper_y)`.
pub(crate) type Bounds = (Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>);

/// Build lower + upper tube curves from a reference trajectory and
/// per-point half-widths (not cancellable; tests only).
#[cfg(test)]
pub(crate) fn build_bounds(
    t_ref: &[f64],
    y_ref: &[f64],
    half_x: &[f64],
    half_y: &[f64],
    mag_x: f64,
) -> Bounds {
    never_cancelled(|cp| build_bounds_checked(t_ref, y_ref, half_x, half_y, mag_x, cp))
}

/// Build lower + upper tube curves from a reference trajectory and
/// per-point half-widths, consulting `cp` between the steps and inside
/// the loop removal. Returns `(lower_x, lower_y, upper_x, upper_y)`.
pub(crate) fn build_bounds_checked<C: FnMut() -> Result<(), Cancelled>>(
    t_ref: &[f64],
    y_ref: &[f64],
    half_x: &[f64],
    half_y: &[f64],
    mag_x: f64,
    cp: &mut Checkpoint<'_, C>,
) -> Result<Bounds, Cancelled> {
    // Work on normalized x copies.
    let x_norm = normalized_copy(t_ref, mag_x, cp)?;
    let hx_norm = normalized_copy(half_x, mag_x, cp)?;

    let (mut lx, mut ly) = build_corner_curve(&x_norm, y_ref, &hx_norm, half_y, Curve::Lower, cp)?;
    cp.now()?;
    let (mut ux, mut uy) = build_corner_curve(&x_norm, y_ref, &hx_norm, half_y, Curve::Upper, cp)?;
    cp.now()?;

    remove_loop_checked(&mut lx, &mut ly, Curve::Lower, cp)?;
    cp.now()?;
    remove_loop_checked(&mut ux, &mut uy, Curve::Upper, cp)?;
    cp.now()?;

    cp.chunks(lx.len(), |r| denormalize(&mut lx[r], mag_x))?;
    cp.chunks(ux.len(), |r| denormalize(&mut ux[r], mag_x))?;

    Ok((lx, ly, ux, uy))
}

/// `src / mag` (see [`normalize`]), consulting `cp` every
/// [`CHECK_INTERVAL`](crate::cancel::CHECK_INTERVAL) elements.
fn normalized_copy<C: FnMut() -> Result<(), Cancelled>>(
    src: &[f64],
    mag: f64,
    cp: &mut Checkpoint<'_, C>,
) -> Result<Vec<f64>, Cancelled> {
    let mut out = Vec::with_capacity(src.len());
    cp.chunks(src.len(), |r| {
        let start = out.len();
        out.extend_from_slice(&src[r]);
        normalize(&mut out[start..], mag);
    })?;
    Ok(out)
}

/// Enumerate corners for either the lower (`sgn=-1`) or upper
/// (`sgn=+1`) curve. Mirrors `getLower`/`getUpper` from the C
/// reference.
fn build_corner_curve<C: FnMut() -> Result<(), Cancelled>>(
    x_norm: &[f64],
    y_ref: &[f64],
    hx_norm: &[f64],
    hy: &[f64],
    curve: Curve,
    cp: &mut Checkpoint<'_, C>,
) -> Result<(Vec<f64>, Vec<f64>), Cancelled> {
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
            // Linear in `n`: one unit of work per reference point.
            cp.tick(1)?;
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

    Ok((cx, cy))
}

/// A polyline edited in place as a gap buffer over its `x` / `y` vectors.
///
/// `remove_loop` deletes and inserts points close to a cursor that only
/// moves locally. With plain `Vec::drain` / `insert` / `remove` every
/// edit shifts the whole tail (`O(n)` per edit, hence `O(n^2)` for noisy
/// references, which produce `O(n)` loops). The gap buffer keeps an
/// unused hole at the last edit position, so an edit only moves the
/// points between the previous and the current edit position. Logical
/// indices, values and the order of floating-point operations are
/// unchanged, so results are bit-identical.
struct GapPolyline<'a> {
    /// Points `[0, gap_start)` and `[gap_end, x.len())` are live.
    x: &'a mut Vec<f64>,
    y: &'a mut Vec<f64>,
    gap_start: usize,
    gap_end: usize,
}

impl<'a> GapPolyline<'a> {
    /// Start editing; the gap is initially empty, at the end.
    fn new(x: &'a mut Vec<f64>, y: &'a mut Vec<f64>) -> Self {
        assert_eq!(x.len(), y.len());
        let n = x.len();
        Self {
            x,
            y,
            gap_start: n,
            gap_end: n,
        }
    }

    #[inline]
    fn len(&self) -> usize {
        self.x.len() - (self.gap_end - self.gap_start)
    }

    /// Physical index of logical point `i`. An out-of-range `i` maps to
    /// at least `x.len()`, so the subsequent slice access panics just as
    /// the former `Vec` indexing did (it never lands inside the gap).
    #[inline]
    fn phys(&self, i: usize) -> usize {
        if i < self.gap_start {
            i
        } else {
            i + (self.gap_end - self.gap_start)
        }
    }

    #[inline]
    fn x(&self, i: usize) -> f64 {
        self.x[self.phys(i)]
    }

    #[inline]
    fn y(&self, i: usize) -> f64 {
        self.y[self.phys(i)]
    }

    /// Move the gap so it starts at logical position `pos`.
    fn move_gap_to(&mut self, pos: usize) {
        if pos < self.gap_start {
            let n = self.gap_start - pos;
            let dst = self.gap_end - n;
            self.x.copy_within(pos..self.gap_start, dst);
            self.y.copy_within(pos..self.gap_start, dst);
            self.gap_start = pos;
            self.gap_end = dst;
        } else if pos > self.gap_start {
            let n = pos - self.gap_start;
            let src = self.gap_end..self.gap_end + n;
            self.x.copy_within(src.clone(), self.gap_start);
            self.y.copy_within(src, self.gap_start);
            self.gap_start += n;
            self.gap_end += n;
        }
    }

    /// Delete logical points `start..end` (like `Vec::drain(start..end)`).
    fn delete(&mut self, start: usize, end: usize) {
        assert!(start <= end && end <= self.len(), "delete out of range");
        self.move_gap_to(start);
        self.gap_end += end - start;
    }

    /// Insert a point before logical index `i` (like `Vec::insert`);
    /// `i == len()` appends.
    fn insert(&mut self, i: usize, x: f64, y: f64) {
        assert!(i <= self.len(), "insert out of range");
        if self.gap_start == self.gap_end {
            // Gap exhausted: open a new one (amortised O(1) per insert).
            let extra = (self.x.len() / 8).max(64);
            let at = self.gap_start;
            self.x.splice(at..at, std::iter::repeat_n(0.0, extra));
            self.y.splice(at..at, std::iter::repeat_n(0.0, extra));
            self.gap_end += extra;
        }
        self.move_gap_to(i);
        self.x[self.gap_start] = x;
        self.y[self.gap_start] = y;
        self.gap_start += 1;
    }
}

impl Drop for GapPolyline<'_> {
    /// Close the gap so `x` / `y` hold exactly the live points.
    fn drop(&mut self) {
        let n = self.len();
        self.move_gap_to(n);
        self.x.truncate(n);
        self.y.truncate(n);
    }
}

/// Remove backward-going segments, inserting intersection points (not
/// cancellable; tests only).
#[cfg(test)]
fn remove_loop(x: &mut Vec<f64>, y: &mut Vec<f64>, curve: Curve) {
    never_cancelled(|cp| remove_loop_checked(x, y, curve, cp));
}

/// Remove backward-going segments, inserting intersection points.
/// Direct port of `removeLoop`; edits through a [`GapPolyline`] so each
/// loop removal costs time proportional to the loop, not to the curve.
/// On cancellation the curve is left in an unspecified (but valid) state.
fn remove_loop_checked<C: FnMut() -> Result<(), Cancelled>>(
    x: &mut Vec<f64>,
    y: &mut Vec<f64>,
    curve: Curve,
    cp: &mut Checkpoint<'_, C>,
) -> Result<(), Cancelled> {
    let mut p = GapPolyline::new(x, y);
    remove_loop_gap(&mut p, curve, cp)
}

fn remove_loop_gap<C: FnMut() -> Result<(), Cancelled>>(
    p: &mut GapPolyline,
    curve: Curve,
    cp: &mut Checkpoint<'_, C>,
) -> Result<(), Cancelled> {
    let cur_ind: i32 = match curve {
        Curve::Lower => -1,
        Curve::Upper => 1,
    };
    let mut j: usize = 1;
    while j + 2 < p.len() {
        // Checkpoint: one step per outer iteration; a loop removal adds
        // the points it scanned below. Bounds the time between checks
        // even when single loops span many points (wide x tolerance).
        cp.tick(1)?;
        if p.x(j + 1) < p.x(j) {
            // ===== 1. find i, k =====
            let mut i: usize = j;
            let mut i_previous: usize = i;

            // Find i_s such that X[i_s - 1] <= X[j+1] < X[i_s]
            let x_j1 = p.x(j + 1);
            while i > 0 && x_j1 < p.x(i - 1) {
                i -= 1;
            }
            let x_j = p.x(j);
            let mut k_max: usize = j + 1;
            while k_max < p.len() - 1 && p.x(k_max) < x_j {
                k_max += 1;
            }

            // The scans above and the edits below are bounded by the
            // points between `i` and `k_max`.
            cp.tick(k_max - i)?;

            let mut k: usize = j + 1;
            // `y_intp` is the interpolated y at X[k] on segment (i-1, i)
            let mut y_intp: f64 = if i == 0 { p.y(0) } else { p.y(i - 1) };

            loop {
                let cond = if cur_ind == -1 {
                    y_intp < p.y(k)
                } else {
                    p.y(k) < y_intp
                };
                if !cond || k >= k_max {
                    break;
                }
                i_previous = i;
                k += 1;
                // advance i
                let (xk, yk) = (p.x(k), p.y(k));
                while i < j {
                    let (xi, yi) = (p.x(i), p.y(i));
                    let advance = xi < xk
                        || (cur_ind == -1
                            && equ(xi, xk)
                            && yi < yk
                            && !(k + 1 < p.len() && equ(xk, p.x(k + 1)) && p.y(k + 1) < yk))
                        || (cur_ind == 1
                            && equ(xi, xk)
                            && yi > yk
                            && !(k + 1 < p.len() && equ(xk, p.x(k + 1)) && p.y(k + 1) > yk));
                    if !advance {
                        break;
                    }
                    i += 1;
                }
                // linear interpolation of y at X[k] on segment (i-1, i)
                if i == 0 {
                    y_intp = p.y(0);
                } else if !equ(p.x(i), p.x(i - 1)) {
                    y_intp = (p.y(i) - p.y(i - 1)) / (p.x(i) - p.x(i - 1)) * (xk - p.x(i - 1))
                        + p.y(i - 1);
                } else {
                    y_intp = p.y(i);
                }
            }

            // Regular case: i = iPrevious - 1; special case: i = iPrevious.
            i = if i_previous > 1 {
                i_previous - 1
            } else {
                i_previous
            };
            // linear interpolation of y at X[i] on segment (k-1, k)
            if k >= 1 && !equ(p.x(k), p.x(k - 1)) {
                y_intp = (p.y(k) - p.y(k - 1)) / (p.x(k) - p.x(k - 1)) * (p.x(i) - p.x(k - 1))
                    + p.y(k - 1);
            }
            // Advance i
            loop {
                let cond = if k >= 1 && !equ(p.x(k), p.x(k - 1)) {
                    if cur_ind == -1 {
                        p.y(i) < y_intp
                    } else {
                        y_intp < p.y(i)
                    }
                } else if k >= 1 {
                    p.x(i) < p.x(k)
                } else {
                    false
                };
                if !cond {
                    break;
                }
                i += 1;
                if i >= p.len() {
                    break;
                }
                if k >= 1 && !equ(p.x(k), p.x(k - 1)) {
                    y_intp = (p.y(k) - p.y(k - 1)) / (p.x(k) - p.x(k - 1)) * (p.x(i) - p.x(k - 1))
                        + p.y(k - 1);
                }
            }

            // ===== 2. intersection point =====
            let (mut ix, mut iy, mut add_point) = (0.0, 0.0, true);
            if k == 0 || i == 0 || (equ(p.x(i), p.x(i - 1)) && equ(p.x(k), p.x(k - 1))) {
                add_point = false;
            } else if equ(p.x(i), p.x(i - 1)) {
                ix = p.x(i);
                iy = p.y(k - 1)
                    + ((p.x(i) - p.x(k - 1)) * (p.y(k) - p.y(k - 1))) / (p.x(k) - p.x(k - 1));
            } else if equ(p.x(k), p.x(k - 1)) {
                ix = p.x(k);
                iy = p.y(i - 1)
                    + ((p.x(k) - p.x(i - 1)) * (p.y(i) - p.y(i - 1))) / (p.x(i) - p.x(i - 1));
            } else {
                let a1 = (p.y(i) - p.y(i - 1)) / (p.x(i) - p.x(i - 1));
                let a2 = (p.y(k) - p.y(k - 1)) / (p.x(k) - p.x(k - 1));
                if !equ(a1, a2) {
                    ix = (a1 * p.x(i - 1) - a2 * p.x(k - 1) - p.y(i - 1) + p.y(k - 1)) / (a1 - a2);
                    if a1.abs() > a2.abs() {
                        iy = a2 * (ix - p.x(k - 1)) + p.y(k - 1);
                    } else {
                        iy = a1 * (ix - p.x(i - 1)) + p.y(i - 1);
                    }
                } else {
                    add_point = false;
                }
            }

            // ===== 3. Delete points i..=k-1 =====
            if k > i {
                p.delete(i, k);
            }
            // ===== 4. Add intersection point =====
            if add_point && i < p.len() {
                if !(equ(p.x(i), ix) && equ(p.y(i), iy)) {
                    p.insert(i, ix, iy);
                }
            } else if add_point {
                let end = p.len();
                p.insert(end, ix, iy);
            }

            // ===== 5. set j = i =====
            j = i;

            // ===== 6. Delete doubled points =====
            if i >= 1 && i < p.len() && equ(p.x(i - 1), p.x(i)) && equ(p.y(i - 1), p.y(i)) {
                p.delete(i, i + 1);
                j = i.saturating_sub(1);
            }
        }
        j += 1;
    }
    Ok(())
}

#[cfg(test)]
#[path = "corners_differential.rs"]
mod differential;

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

    /// Logical contents of a gap polyline, as bits.
    fn gap_bits(p: &GapPolyline<'_>) -> Vec<(u64, u64)> {
        (0..p.len())
            .map(|i| (p.x(i).to_bits(), p.y(i).to_bits()))
            .collect()
    }

    fn model_bits(x: &[f64], y: &[f64]) -> Vec<(u64, u64)> {
        x.iter()
            .zip(y)
            .map(|(a, b)| (a.to_bits(), b.to_bits()))
            .collect()
    }

    /// `GapPolyline` against a plain `Vec` model: random inserts (also at
    /// the end and without a preceding delete), deletes (also empty ones,
    /// at any position including the end) and appends, compared bit for
    /// bit after every operation and after `Drop`. Runs of inserts exhaust
    /// the gap so it is regrown several times, also mid-curve.
    #[test]
    fn gap_polyline_matches_vec_model() {
        let mut s: u64 = 0x2545_F491_4F6C_DD1D;
        let mut next = move |m: usize| -> usize {
            s ^= s << 13;
            s ^= s >> 7;
            s ^= s << 17;
            (s % m as u64) as usize
        };
        for case in 0..40usize {
            let n0 = [0usize, 1, 2, 7, 100, 1000][case % 6];
            let mut x: Vec<f64> = (0..n0).map(|i| i as f64 * 0.5 + case as f64).collect();
            let mut y: Vec<f64> = (0..n0).map(|i| -(i as f64) * 0.25).collect();
            let (mut mx, mut my) = (x.clone(), y.clone());
            let mut grows = 0usize;
            let mut value = 1e6 * case as f64;
            {
                let mut p = GapPolyline::new(&mut x, &mut y);
                for step in 0..1500usize {
                    let len = p.len();
                    // Mostly inserts in the bursts (exhaust the gap), a mix
                    // otherwise.
                    let burst = (step / 150) % 3 == 1;
                    let op = if burst { next(10).min(1) } else { next(4) };
                    value += 1.0;
                    match op {
                        // insert anywhere, also at len (append)
                        0 => {
                            let i = next(len + 1);
                            if p.gap_start == p.gap_end {
                                grows += 1;
                            }
                            p.insert(i, value, -value);
                            mx.insert(i, value);
                            my.insert(i, -value);
                        }
                        // append explicitly
                        1 => {
                            if p.gap_start == p.gap_end {
                                grows += 1;
                            }
                            p.insert(len, value, value * 0.5);
                            mx.push(value);
                            my.push(value * 0.5);
                        }
                        // delete a range, possibly empty, possibly at len
                        2 => {
                            let a = next(len + 1);
                            let b = a + next((len - a).min(20) + 1);
                            p.delete(a, b);
                            mx.drain(a..b);
                            my.drain(a..b);
                        }
                        // empty delete exactly at the end, then insert there
                        _ => {
                            p.delete(len, len);
                            let i = next(len + 1);
                            p.delete(i, i);
                            if p.gap_start == p.gap_end {
                                grows += 1;
                            }
                            p.insert(i, value, 0.0);
                            mx.insert(i, value);
                            my.insert(i, 0.0);
                        }
                    }
                    assert_eq!(
                        gap_bits(&p),
                        model_bits(&mx, &my),
                        "case {case} step {step}"
                    );
                }
                // Exhaust and regrow the gap twice more, inserting mid-curve.
                let target = grows + 2;
                while grows < target {
                    let i = next(p.len() + 1);
                    if p.gap_start == p.gap_end {
                        grows += 1;
                    }
                    value += 1.0;
                    p.insert(i, value, value);
                    mx.insert(i, value);
                    my.insert(i, value);
                    assert_eq!(gap_bits(&p), model_bits(&mx, &my), "case {case} regrow");
                }
            }
            // Drop closed the gap: the vectors hold exactly the model.
            assert_eq!(
                model_bits(&x, &y),
                model_bits(&mx, &my),
                "case {case} after drop"
            );
            assert!(grows >= 2, "case {case}: gap regrown {grows} times");
        }
    }
}
