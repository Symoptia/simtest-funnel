//! Per-point tolerance envelope computation.
//!
//! Direct port of
//! [`set_tube_size`](/home/iakovn/projects/funnel/src/tubeSize.c)
//! from the LBNL Funnel C reference.

use crate::options::Tolerances;

/// Small non-zero floor applied to the half-widths so the corner
/// algorithm can never see a zero-size rectangle.
pub(crate) const HALFWIDTH_FLOOR: f64 = 1e-10;

/// Range and magnitude characteristics of a reference trajectory.
#[derive(Debug, Clone, Copy)]
pub(crate) struct DataChar {
    pub range_x: f64,
    pub range_y: f64,
    pub mag_x: f64,
    pub mag_y: f64,
}

/// Compute span/magnitude statistics over a slice.
pub(crate) fn get_data_char(x: &[f64], y: &[f64]) -> DataChar {
    debug_assert!(!x.is_empty() && x.len() == y.len());
    let (mut mnx, mut mxx) = (x[0], x[0]);
    let (mut mny, mut mxy) = (y[0], y[0]);
    for &v in x {
        if v < mnx {
            mnx = v;
        }
        if v > mxx {
            mxx = v;
        }
    }
    for &v in y {
        if v < mny {
            mny = v;
        }
        if v > mxy {
            mxy = v;
        }
    }
    DataChar {
        range_x: mxx - mnx,
        range_y: mxy - mny,
        mag_x: mxx.max(mnx.abs()),
        mag_y: mxy.max(mny.abs()),
    }
}

/// C reference `equ(a, 0)` — treat `|v| < 1e-10` as zero.
#[inline]
fn eq_zero(v: f64) -> bool {
    v.abs() < 1e-10
}

/// Compute per-point half-widths `(half_x, half_y)` for the reference
/// trajectory using the same formula as the C reference's
/// `set_tube_size`. Falls back to `rtol*mag` when the range-based
/// computation yields (effectively) zero, then to the hard floor
/// `HALFWIDTH_FLOOR`.
pub(crate) fn tube_halfwidths(
    t_ref: &[f64],
    y_ref: &[f64],
    dc: DataChar,
    tol: &Tolerances,
) -> (Vec<f64>, Vec<f64>) {
    debug_assert_eq!(t_ref.len(), y_ref.len());
    let n = t_ref.len();
    let mut half_x = Vec::with_capacity(n);
    let mut half_y = Vec::with_capacity(n);
    for i in 0..n {
        let mut hx = tol
            .atolx
            .max(tol.rtolx * dc.range_x)
            .max(tol.ltolx * t_ref[i].abs());
        if eq_zero(hx) {
            if !eq_zero(tol.rtolx) {
                hx = hx.max(tol.rtolx * dc.mag_x);
            }
            if eq_zero(hx) {
                hx = hx.max(HALFWIDTH_FLOOR);
            }
        }
        let mut hy = tol
            .atoly
            .max(tol.rtoly * dc.range_y)
            .max(tol.ltoly * y_ref[i].abs());
        if eq_zero(hy) {
            if !eq_zero(tol.rtoly) {
                hy = hy.max(tol.rtoly * dc.mag_y);
            }
            if eq_zero(hy) {
                hy = hy.max(HALFWIDTH_FLOOR);
            }
        }
        half_x.push(hx);
        half_y.push(hy);
    }
    (half_x, half_y)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tol(atolx: f64, atoly: f64, ltolx: f64, ltoly: f64, rtolx: f64, rtoly: f64) -> Tolerances {
        Tolerances {
            atolx,
            atoly,
            ltolx,
            ltoly,
            rtolx,
            rtoly,
        }
    }

    fn dc(range_x: f64, range_y: f64) -> DataChar {
        DataChar {
            range_x,
            range_y,
            mag_x: range_x,
            mag_y: range_y,
        }
    }

    #[test]
    fn atol_dominant() {
        let t = &[0.0, 1.0, 2.0];
        let y = &[0.0, 1.0, 2.0];
        let (hx, hy) = tube_halfwidths(t, y, dc(2.0, 2.0), &tol(0.5, 0.25, 0.0, 0.0, 0.0, 0.0));
        for v in &hx {
            assert_eq!(*v, 0.5);
        }
        for v in &hy {
            assert_eq!(*v, 0.25);
        }
    }

    #[test]
    fn rtol_dominant() {
        let t = &[0.0, 1.0, 2.0];
        let y = &[0.0, 1.0, 2.0];
        let (hx, hy) = tube_halfwidths(t, y, dc(10.0, 8.0), &tol(0.0, 0.0, 0.0, 0.0, 0.1, 0.25));
        for v in &hx {
            assert_eq!(*v, 1.0);
        }
        for v in &hy {
            assert_eq!(*v, 2.0);
        }
    }

    #[test]
    fn ltol_dominant() {
        let t = &[1.0, 2.0, 4.0];
        let y = &[-3.0, 6.0, 8.0];
        let (hx, hy) = tube_halfwidths(t, y, dc(3.0, 11.0), &tol(0.0, 0.0, 0.1, 0.5, 0.0, 0.0));
        assert_eq!(hx, vec![0.1, 0.2, 0.4]);
        assert_eq!(hy, vec![1.5, 3.0, 4.0]);
    }

    #[test]
    fn zero_tol_floor_1e_minus_10() {
        let t = &[0.0, 1.0];
        let y = &[0.0, 1.0];
        let (hx, hy) = tube_halfwidths(t, y, dc(0.0, 0.0), &Tolerances::default());
        for v in hx.iter().chain(hy.iter()) {
            assert_eq!(*v, HALFWIDTH_FLOOR);
        }
    }
}
