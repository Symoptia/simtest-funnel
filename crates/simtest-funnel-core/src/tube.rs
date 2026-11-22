//! Per-point tolerance envelope computation.
//!
//! Direct port of
//! [`set_tube_size`](/home/iakovn/projects/funnel/src/tubeSize.c)
//! from the LBNL Funnel C reference.

#[cfg(test)]
use crate::cancel::never_cancelled;
use crate::cancel::{Cancelled, Checkpoint};
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

/// Compute span/magnitude statistics over a slice (tests only).
#[cfg(test)]
pub(crate) fn get_data_char(x: &[f64], y: &[f64]) -> DataChar {
    never_cancelled(|cp| get_data_char_checked(x, y, cp))
}

/// Compute span/magnitude statistics over a slice, consulting `cp`
/// every [`CHECK_INTERVAL`](crate::cancel::CHECK_INTERVAL) elements.
pub(crate) fn get_data_char_checked<C: FnMut() -> Result<(), Cancelled>>(
    x: &[f64],
    y: &[f64],
    cp: &mut Checkpoint<'_, C>,
) -> Result<DataChar, Cancelled> {
    debug_assert!(!x.is_empty() && x.len() == y.len());
    let (mut mnx, mut mxx) = (x[0], x[0]);
    let (mut mny, mut mxy) = (y[0], y[0]);
    cp.chunks(x.len(), |r| {
        for &v in &x[r] {
            if v < mnx {
                mnx = v;
            }
            if v > mxx {
                mxx = v;
            }
        }
    })?;
    cp.chunks(y.len(), |r| {
        for &v in &y[r] {
            if v < mny {
                mny = v;
            }
            if v > mxy {
                mxy = v;
            }
        }
    })?;
    Ok(DataChar {
        range_x: mxx - mnx,
        range_y: mxy - mny,
        mag_x: mxx.max(mnx.abs()),
        mag_y: mxy.max(mny.abs()),
    })
}

/// C reference `equ(a, 0)` — treat `|v| < 1e-10` as zero.
#[inline]
fn eq_zero(v: f64) -> bool {
    v.abs() < 1e-10
}

/// An upper bound on the x half-width that [`tube_halfwidths_checked`]
/// gives a reference point at `x`:
/// `max(atolx, rtolx*range_x, ltolx*|x|, fallback, HALFWIDTH_FLOOR)`, where
/// `fallback = rtolx*mag_x` if `rtolx` is non-zero (the constant-reference
/// fallback), else `0`. Equal to the half-width except where the fallback
/// is not taken although it is larger.
///
/// As a function of `x` it has the form `max(c, ltolx*|x|)`, which the
/// x-range extension relies on (see `compare::extended_indices`).
#[inline]
pub(crate) fn halfwidth_x_bound(x: f64, dc: DataChar, tol: &Tolerances) -> f64 {
    let fallback = if eq_zero(tol.rtolx) {
        0.0
    } else {
        tol.rtolx * dc.mag_x
    };
    tol.atolx
        .max(tol.rtolx * dc.range_x)
        .max(fallback)
        .max(HALFWIDTH_FLOOR)
        .max(tol.ltolx * x.abs())
}

/// Compute per-point half-widths `(half_x, half_y)` for the reference
/// trajectory using the same formula as the C reference's
/// `set_tube_size`. Falls back to `rtol*mag` when the range-based
/// computation yields (effectively) zero, then to the hard floor
/// `HALFWIDTH_FLOOR` (tests only).
#[cfg(test)]
pub(crate) fn tube_halfwidths(
    t_ref: &[f64],
    y_ref: &[f64],
    dc: DataChar,
    tol: &Tolerances,
) -> (Vec<f64>, Vec<f64>) {
    never_cancelled(|cp| tube_halfwidths_checked(t_ref, y_ref, dc, tol, cp))
}

/// The half-widths of `tube_halfwidths`, consulting `cp` every
/// [`CHECK_INTERVAL`](crate::cancel::CHECK_INTERVAL) points.
pub(crate) fn tube_halfwidths_checked<C: FnMut() -> Result<(), Cancelled>>(
    t_ref: &[f64],
    y_ref: &[f64],
    dc: DataChar,
    tol: &Tolerances,
    cp: &mut Checkpoint<'_, C>,
) -> Result<(Vec<f64>, Vec<f64>), Cancelled> {
    debug_assert_eq!(t_ref.len(), y_ref.len());
    let n = t_ref.len();
    let mut half_x = Vec::with_capacity(n);
    let mut half_y = Vec::with_capacity(n);
    cp.chunks(n, |r| {
        for i in r {
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
    })?;
    Ok((half_x, half_y))
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
        let (hx, hy) = tube_halfwidths(t, y, dc(0.0, 0.0), &Tolerances::ZERO);
        for v in hx.iter().chain(hy.iter()) {
            assert_eq!(*v, HALFWIDTH_FLOOR);
        }
    }
}
