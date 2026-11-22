//! Tests of the x-range window: the tube is built from the reference
//! extended beyond the window, so in-window test points are judged as in
//! a full-range comparison.

use super::*;
use crate::errors::interpolate_clamped;

/// xorshift64 generator (deterministic, no dependency).
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
    /// Uniform in `[0, 1)`.
    fn f(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
    /// Uniform in `0..m`.
    fn u(&mut self, m: usize) -> usize {
        (self.next() % m as u64) as usize
    }
}

/// Signals of several shapes: random walk, noisy sine, steps, small
/// integers (many flat and repeated values), smooth sine, flat runs mixed
/// with a cosine (collinear segments).
fn signal(rng: &mut Rng, kind: usize, t: &[f64]) -> Vec<f64> {
    let mut v = 0.0;
    t.iter()
        .enumerate()
        .map(|(i, &x)| match kind {
            0 => {
                v += rng.f() - 0.5;
                v
            }
            1 => (x * 0.7).sin() + 0.1 * (rng.f() - 0.5),
            2 => {
                if rng.u(8) == 0 {
                    v = rng.u(5) as f64 - 2.0;
                }
                v
            }
            3 => rng.u(3) as f64,
            4 => (x * 0.3).sin(),
            _ => {
                if i % 7 < 3 {
                    1.0
                } else {
                    (x * 1.3).cos()
                }
            }
        })
        .collect()
}

/// Irregular non-decreasing grid; with `dup`, about 10 % repeated x.
fn grid(rng: &mut Rng, n: usize, x0: f64, dup: bool) -> Vec<f64> {
    let mut t = Vec::with_capacity(n);
    let mut x = x0;
    for _ in 0..n {
        t.push(x);
        if dup && rng.u(10) == 0 {
            continue;
        }
        x += 0.2 + rng.f();
    }
    t
}

fn opts(tol: Tolerances, lo: f64, hi: f64) -> Options {
    Options {
        tolerances: tol,
        x_range: Range { lo, hi },
    }
}

/// Relative difference small enough to be floating-point rounding.
fn close(a: f64, b: f64) -> bool {
    a == b || (a - b).abs() <= 1e-12 * a.abs().max(b.abs())
}

struct PropertyStats {
    windows: usize,
    points: usize,
    exact: usize,
}

/// For random references, test signals (shifted, noisy, on another grid),
/// tolerances without range-relative coefficients and windows (also
/// partly outside the data and narrower than the x tolerance): every
/// test point inside the effective window gets the same verdict as in the
/// full-range comparison, and the same deviation and bound values up to
/// rounding.
fn check_property(
    seed: u64,
    cases: usize,
    atolx_max: f64,
    ltolx_max: f64,
    win_frac: f64,
) -> PropertyStats {
    let mut rng = Rng(seed);
    let mut st = PropertyStats {
        windows: 0,
        points: 0,
        exact: 0,
    };
    for case in 0..cases {
        let kind = case % 6;
        let n = 20 + rng.u(200);
        let x0 = if rng.u(3) == 0 {
            -50.0 * rng.f()
        } else {
            100.0 * rng.f()
        };
        let t = grid(&mut rng, n, x0, case % 5 == 0);
        let y = signal(&mut rng, kind, &t);
        let nt = 20 + rng.u(200);
        let tx0 = t[0] + (rng.f() - 0.5) * 2.0;
        let tt = grid(&mut rng, nt, tx0, case % 7 == 0);
        let shift = (rng.f() - 0.5) * 2.0;
        let shifted: Vec<f64> = tt.iter().map(|x| x - shift).collect();
        let yt: Vec<f64> = signal(&mut rng, kind, &shifted)
            .into_iter()
            .map(|v| v + 0.2 * (rng.f() - 0.5))
            .collect();
        let tol = Tolerances {
            atolx: if rng.u(4) == 0 {
                0.0
            } else {
                atolx_max * rng.f()
            },
            atoly: if rng.u(4) == 0 { 0.0 } else { 0.5 * rng.f() },
            ltolx: if rng.u(3) == 0 {
                ltolx_max * rng.f()
            } else {
                0.0
            },
            ltoly: if rng.u(3) == 0 { 0.2 * rng.f() } else { 0.0 },
            rtolx: 0.0,
            rtoly: 0.0,
        };
        let full = compare(
            &t,
            &y,
            &tt,
            &yt,
            &opts(tol, f64::NEG_INFINITY, f64::INFINITY),
        );
        let span = t[n - 1] - t[0];
        let lo = t[0] + (rng.f() * 1.2 - 0.1) * span;
        let hi = lo + rng.f() * win_frac * span;
        let win = compare(&t, &y, &tt, &yt, &opts(tol, lo, hi));
        if !matches!(
            win.status,
            Status::Pass | Status::Fail | Status::MissingReference | Status::MissingTest
        ) {
            continue;
        }
        st.windows += 1;
        let (eff_lo, eff_hi) = (lo.max(t[0]), hi.min(t[n - 1]));
        let judged: Vec<usize> = (0..nt)
            .filter(|&j| tt[j] >= eff_lo && tt[j] <= eff_hi)
            .collect();
        let xs: Vec<f64> = judged.iter().map(|&j| tt[j]).collect();
        let bound = |r: &CompareResult| {
            (
                interpolate_clamped(&r.lower.0, &r.lower.1, &xs),
                interpolate_clamped(&r.upper.0, &r.upper.1, &xs),
            )
        };
        let (fl, fu) = bound(&full);
        let (wl, wu) = bound(&win);
        for (k, &j) in judged.iter().enumerate() {
            let (ef, ew) = (full.errors.1[j], win.errors.1[j]);
            let ctx = format!(
                "case {case} kind {kind} x={} window [{lo}, {hi}] {tol:?}",
                tt[j]
            );
            assert_eq!(ef == 0.0, ew == 0.0, "verdict differs: {ctx}: {ef} vs {ew}");
            assert!(close(ef, ew), "deviation differs: {ctx}: {ef} vs {ew}");
            assert!(
                close(fl[k], wl[k]) && close(fu[k], wu[k]),
                "bounds differ: {ctx}"
            );
            st.points += 1;
            if ef.to_bits() == ew.to_bits() {
                st.exact += 1;
            }
        }
        // Not judged: deviation 0 outside x_range.
        for (j, &x) in tt.iter().enumerate() {
            if x < lo || x > hi {
                assert_eq!(
                    win.errors.1[j], 0.0,
                    "case {case}: deviation outside x_range"
                );
            }
            assert_eq!(win.errors.0[j], x);
        }
        // Same verdict as the full comparison restricted to the window.
        let full_fail = judged.iter().any(|&j| full.errors.1[j] != 0.0);
        assert_eq!(
            full_fail,
            win.status == Status::Fail,
            "case {case}: status {:?}",
            win.status
        );
    }
    st
}

#[test]
fn in_window_verdicts_match_full_range() {
    let st = check_property(0x9E37_79B9_7F4A_7C15, 3000, 3.0, 0.05, 0.6);
    assert!(
        st.windows > 1500 && st.points > 30_000,
        "{} {}",
        st.windows,
        st.points
    );
    // Rounding-level differences are possible but rare (collinear runs at
    // the start of the extension): in practice the deviations are equal.
    assert!(
        st.exact * 1000 >= st.points * 999,
        "{} of {}",
        st.exact,
        st.points
    );
}

#[test]
fn in_window_verdicts_match_full_range_wide_x_tolerance() {
    // x half-widths of up to ~20 samples, local x tolerance up to 30 %,
    // narrow windows (often narrower than the x tolerance).
    let st = check_property(12345, 2000, 20.0, 0.3, 0.3);
    assert!(
        st.windows > 1000 && st.points > 10_000,
        "{} {}",
        st.windows,
        st.points
    );
    assert!(
        st.exact * 1000 >= st.points * 999,
        "{} of {}",
        st.exact,
        st.points
    );
}

/// Hourly daily temperature cycle over 6 days; the test is the same cycle
/// 2 h late. `atolx = 3 h`.
fn daily_cycle() -> (Vec<f64>, Vec<f64>, Vec<f64>, Tolerances) {
    let t: Vec<f64> = (0..=144).map(|h| h as f64 * 3600.0).collect();
    let temp =
        |s: f64| 10.0 + 5.0 * (2.0 * std::f64::consts::PI * (s - 14.0 * 3600.0) / 86400.0).cos();
    let y_ref: Vec<f64> = t.iter().map(|&s| temp(s)).collect();
    let y_test: Vec<f64> = t.iter().map(|&s| temp(s - 7200.0)).collect();
    let tol = Tolerances {
        atolx: 10800.0,
        atoly: 0.05,
        ..Tolerances::ZERO
    };
    (t, y_ref, y_test, tol)
}

#[test]
fn time_shift_within_atolx_passes_at_window_edges() {
    let (t, y_ref, y_test, tol) = daily_cycle();
    let full = compare(
        &t,
        &y_ref,
        &t,
        &y_test,
        &opts(tol, f64::NEG_INFINITY, f64::INFINITY),
    );
    // At the data start there is no earlier reference to cover the delay:
    // the full comparison fails there, and only there.
    assert_eq!(full.status, Status::Fail);
    let failing: Vec<f64> = (0..t.len())
        .filter(|&j| full.errors.1[j] != 0.0)
        .map(|j| t[j])
        .collect();
    assert!(
        !failing.is_empty() && failing.iter().all(|&x| x < 10800.0),
        "{failing:?}"
    );
    // A 2-day window in the middle: 49 judged points.
    let (lo, hi) = (2.0 * 86400.0, 4.0 * 86400.0);
    let win = compare(&t, &y_ref, &t, &y_test, &opts(tol, lo, hi));
    assert_eq!(win.status, Status::Pass);
    let s = crate::summarize(&win, &t, &opts(tol, lo, hi));
    assert_eq!((s.points_compared, s.points_outside), (49, 0));
    // Clipping the reference to the window (the former behaviour) makes
    // the first points of the window fail.
    let w = range_indices(&t, lo, hi);
    let clipped = compare(
        &t[w.clone()],
        &y_ref[w.clone()],
        &t,
        &y_test,
        &opts(tol, lo, hi),
    );
    assert_eq!(clipped.status, Status::Fail);
    // The tube reaches beyond the window by the extension.
    assert!(win.lower.0[0] < lo - 10800.0 && *win.upper.0.last().unwrap() > hi + 10800.0);
}

#[test]
fn window_narrower_than_x_tolerance() {
    let (t, y_ref, y_test, tol) = daily_cycle();
    // One hour wide, two reference samples, x tolerance three hours.
    let (lo, hi) = (2.5 * 86400.0, 2.5 * 86400.0 + 3600.0);
    let win = compare(&t, &y_ref, &t, &y_test, &opts(tol, lo, hi));
    assert_eq!(win.status, Status::Pass);
    let full = compare(
        &t,
        &y_ref,
        &t,
        &y_test,
        &opts(tol, f64::NEG_INFINITY, f64::INFINITY),
    );
    for j in range_indices(&t, lo, hi) {
        assert_eq!(win.errors.1[j].to_bits(), full.errors.1[j].to_bits());
    }
    // With a 30-minute tolerance the 2-hour delay fails, also here.
    let tight = Tolerances {
        atolx: 1800.0,
        ..tol
    };
    assert_eq!(
        compare(&t, &y_ref, &t, &y_test, &opts(tight, lo, hi)).status,
        Status::Fail
    );
}

#[test]
fn data_start_and_end_have_nothing_to_extend() {
    let (t, y_ref, y_test, tol) = daily_cycle();
    let full = compare(
        &t,
        &y_ref,
        &t,
        &y_test,
        &opts(tol, f64::NEG_INFINITY, f64::INFINITY),
    );
    let last = *t.last().unwrap();
    // Windows touching (or reaching past) the data start / end: the tube
    // starts / ends exactly where the full-range tube does, so the delayed
    // test still fails in the first hours of the data (as in the full
    // comparison) and passes at the end.
    for (lo, hi, status) in [
        (0.0, 86400.0, Status::Fail),
        (-1e6, 86400.0, Status::Fail),
        (5.0 * 86400.0, last, Status::Pass),
        (5.0 * 86400.0, 1e9, Status::Pass),
    ] {
        let win = compare(&t, &y_ref, &t, &y_test, &opts(tol, lo, hi));
        assert_eq!(win.status, status, "[{lo}, {hi}]");
        if lo <= 0.0 {
            assert_eq!(win.lower.0[0].to_bits(), full.lower.0[0].to_bits());
            assert_eq!(win.upper.1[0].to_bits(), full.upper.1[0].to_bits());
        } else {
            assert_eq!(win.lower.0.last(), full.lower.0.last());
            assert_eq!(win.upper.1.last(), full.upper.1.last());
        }
        for j in range_indices(&t, lo, hi) {
            assert_eq!(win.errors.1[j].to_bits(), full.errors.1[j].to_bits());
        }
    }
}

#[test]
fn window_partly_or_wholly_outside_the_data() {
    let (t, y_ref, y_test, tol) = daily_cycle();
    let last = *t.last().unwrap();
    // Partly outside on the left and right: compared on the overlap (the
    // delayed test fails at the data start, see above).
    let win = compare(&t, &y_ref, &t, &y_test, &opts(tol, -86400.0, 86400.0));
    assert_eq!(win.status, Status::Fail);
    let win = compare(
        &t,
        &y_ref,
        &t,
        &y_test,
        &opts(tol, -86400.0, 86400.0 + 3.0 * 3600.0),
    );
    assert_eq!(win.status, Status::Fail);
    let win = compare(&t, &y_ref, &t, &y_test, &opts(tol, 3.0 * 3600.0, 86400.0));
    assert_eq!(win.status, Status::Pass);
    let win = compare(
        &t,
        &y_ref,
        &t,
        &y_test,
        &opts(tol, last - 86400.0, last + 86400.0),
    );
    assert_eq!(win.status, Status::Pass);
    // Wholly outside: nothing to compare.
    let win = compare(
        &t,
        &y_ref,
        &t,
        &y_test,
        &opts(tol, last + 1.0, last + 86400.0),
    );
    assert_eq!(win.status, Status::EmptyRange);
    // Within the x tolerance of the data end but outside it: still empty.
    let win = compare(
        &t,
        &y_ref,
        &t,
        &y_test,
        &opts(tol, last + 1.0, last + 3600.0),
    );
    assert_eq!(win.status, Status::EmptyRange);
}

#[test]
fn range_relative_bases_are_the_window() {
    // Ramp 0..100 over x 0..100; rtoly = 1 % of the y range in the window
    // [0, 10] is 0.1 (of the whole reference it would be 1.0).
    let t: Vec<f64> = (0..=100).map(f64::from).collect();
    let y = t.clone();
    let tol = Tolerances {
        rtoly: 0.01,
        ..Tolerances::ZERO
    };
    let yt: Vec<f64> = t.iter().map(|v| v + 0.5).collect();
    assert_eq!(
        compare(&t, &y, &t, &yt, &opts(tol, 0.0, 10.0)).status,
        Status::Fail
    );
    assert_eq!(
        compare(
            &t,
            &y,
            &t,
            &yt,
            &opts(tol, f64::NEG_INFINITY, f64::INFINITY)
        )
        .status,
        Status::Pass
    );
}

#[test]
fn extension_cost_does_not_grow_with_the_reference() {
    let n = 2_000_000;
    let t: Vec<f64> = (0..n).map(|i| i as f64).collect();
    let tol = Tolerances {
        atolx: 5.0,
        ..Tolerances::ZERO
    };
    let (lo, hi) = (1_000_000.0, 1_000_010.0);
    let w = range_indices(&t, lo, hi);
    let y = vec![0.0; n];
    let dc = crate::tube::get_data_char(&t[w.clone()], &y[w.clone()]);
    let e = extended_indices(&t, w.clone(), lo, hi, dc, &tol);
    // 2 half-widths (10 samples) plus 3 samples on each side.
    assert_eq!(e, (w.start - 13)..(w.end + 13));
    // A local x tolerance of 50 % or more has no bounded reach: the whole
    // side is used.
    let wide = Tolerances {
        ltolx: 0.6,
        ..Tolerances::ZERO
    };
    assert_eq!(extended_indices(&t, w.clone(), lo, hi, dc, &wide), 0..n);
    // Windows at the data ends do not extend past them.
    let w0 = range_indices(&t, 0.0, 10.0);
    assert_eq!(extended_indices(&t, w0, 0.0, 10.0, dc, &tol), 0..24);
}
