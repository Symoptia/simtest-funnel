//! Differential tests: the gap-buffer `remove_loop` must produce
//! bit-identical results to the former `Vec`-based implementation, which
//! is kept here verbatim as the reference.

use super::*;
use crate::errors::compute_errors;
use crate::options::Tolerances;
use crate::tube::{get_data_char, tube_halfwidths};
use std::panic::{catch_unwind, AssertUnwindSafe};

/// Verbatim copy of the former `Vec`-based `remove_loop`.
pub(super) fn remove_loop_vec(x: &mut Vec<f64>, y: &mut Vec<f64>, curve: Curve) {
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

/// Reference `build_bounds` using [`remove_loop_vec`].
fn build_bounds_vec(
    t_ref: &[f64],
    y_ref: &[f64],
    half_x: &[f64],
    half_y: &[f64],
    mag_x: f64,
) -> (Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>) {
    let mut x_norm: Vec<f64> = t_ref.to_vec();
    let mut hx_norm: Vec<f64> = half_x.to_vec();
    normalize(&mut x_norm, mag_x);
    normalize(&mut hx_norm, mag_x);
    let (mut lx, mut ly) = build_corner_curve(&x_norm, y_ref, &hx_norm, half_y, Curve::Lower);
    let (mut ux, mut uy) = build_corner_curve(&x_norm, y_ref, &hx_norm, half_y, Curve::Upper);
    remove_loop_vec(&mut lx, &mut ly, Curve::Lower);
    remove_loop_vec(&mut ux, &mut uy, Curve::Upper);
    denormalize(&mut lx, mag_x);
    denormalize(&mut ux, mag_x);
    (lx, ly, ux, uy)
}

/// Deterministic xorshift64 generator (no external dependencies).
struct Rng(u64);

impl Rng {
    fn new(seed: u64) -> Self {
        Rng(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1)
    }
    fn next_u64(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
    /// Uniform in [0, 1).
    fn uni(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64
    }
    fn below(&mut self, n: usize) -> usize {
        (self.next_u64() % n as u64) as usize
    }
    fn normal(&mut self) -> f64 {
        let u1 = self.uni().max(1e-300);
        let u2 = self.uni();
        (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos()
    }
}

fn bits(v: &[f64]) -> Vec<u64> {
    v.iter().map(|f| f.to_bits()).collect()
}

/// Sampling grid of `n` points on `[t0, t0 + span]`.
fn grid(rng: &mut Rng, kind: usize, n: usize, t0: f64, span: f64) -> Vec<f64> {
    match kind {
        // uniform
        0 => (0..n)
            .map(|i| t0 + span * i as f64 / (n - 1) as f64)
            .collect(),
        // random non-uniform increments
        1 => {
            let inc: Vec<f64> = (0..n - 1).map(|_| rng.uni() + 1e-3).collect();
            let total: f64 = inc.iter().sum();
            let mut t = vec![t0];
            for d in inc {
                let last = *t.last().unwrap();
                t.push(last + span * d / total);
            }
            t
        }
        // uniform with repeated x values (events / zero-length steps)
        2 => {
            let mut t: Vec<f64> = (0..n)
                .map(|i| t0 + span * i as f64 / (n - 1) as f64)
                .collect();
            for i in 1..n {
                if rng.uni() < 0.15 {
                    t[i] = t[i - 1];
                }
            }
            t
        }
        // clustered: mixture of dense and sparse stretches, some spacings
        // below the 1e-10 equality threshold
        _ => {
            let mut t = vec![t0];
            for _ in 1..n {
                let last = *t.last().unwrap();
                let d = match rng.below(4) {
                    0 => 1e-12,
                    1 => span / n as f64 * 0.01,
                    2 => span / n as f64,
                    _ => span / n as f64 * 3.0,
                };
                t.push(last + d);
            }
            t
        }
    }
}

/// Signal of the given kind sampled at `t`.
fn signal(rng: &mut Rng, kind: usize, t: &[f64], noise: f64) -> Vec<f64> {
    let n = t.len();
    let mut y: Vec<f64> = match kind {
        0 => t.iter().map(|&x| x.sin()).collect(),
        1 => t.iter().map(|&x| (3.0 * x).sin() * 5.0 + 2.0).collect(),
        // steps
        2 => {
            let mut level = 0.0;
            t.iter()
                .map(|_| {
                    if rng.uni() < 0.02 {
                        level = (rng.uni() - 0.5) * 4.0;
                    }
                    level
                })
                .collect()
        }
        // random walk
        3 => {
            let mut v = 0.0;
            (0..n)
                .map(|_| {
                    v += rng.normal() * 0.1;
                    v
                })
                .collect()
        }
        // square wave
        4 => t
            .iter()
            .map(|&x| if (x * 0.7).sin() >= 0.0 { 1.0 } else { -1.0 })
            .collect(),
        // sawtooth
        5 => t.iter().map(|&x| (x * 1.3).rem_euclid(1.0)).collect(),
        // constant
        6 => vec![0.25; n],
        // quantised sine (many equal y and equal slopes)
        7 => t.iter().map(|&x| ((x.sin()) * 8.0).round() / 8.0).collect(),
        // large offset / magnitude
        8 => t.iter().map(|&x| 1e4 + 1e3 * (0.2 * x).cos()).collect(),
        // pure noise
        _ => (0..n).map(|_| rng.normal()).collect(),
    };
    if noise > 0.0 {
        for v in y.iter_mut() {
            *v += noise * rng.normal();
        }
    }
    y
}

fn tolerances(rng: &mut Rng, kind: usize) -> Tolerances {
    let r = [1e-4, 5e-4, 2e-3, 1e-2, 5e-2, 0.2][rng.below(6)];
    match kind {
        0 => Tolerances::DEFAULT,
        1 => Tolerances {
            rtolx: r,
            rtoly: r,
            ..Tolerances::ZERO
        },
        2 => Tolerances {
            rtolx: r,
            rtoly: [1e-4, 2e-3, 3e-2][rng.below(3)],
            ..Tolerances::ZERO
        },
        3 => Tolerances {
            atolx: rng.uni() * 0.5,
            atoly: rng.uni() * 0.5,
            ..Tolerances::ZERO
        },
        4 => Tolerances {
            ltolx: r,
            ltoly: r,
            ..Tolerances::ZERO
        },
        5 => Tolerances::ZERO,
        _ => Tolerances {
            atolx: rng.uni() * 0.01,
            atoly: rng.uni() * 0.01,
            ltolx: rng.uni() * 0.01,
            ltoly: rng.uni() * 0.01,
            rtolx: rng.uni() * 0.01,
            rtoly: rng.uni() * 0.01,
        },
    }
}

/// Compare `build_bounds` and the full `compare` output against the
/// reference pipeline built on [`build_bounds_vec`]. Returns whether the
/// public-API comparison ran (`compare` did not reject the input).
fn check_case(t: &[f64], y: &[f64], tt: &[f64], yt: &[f64], tol: Tolerances, label: &str) -> bool {
    let dc = get_data_char(t, y);
    let (hx, hy) = tube_halfwidths(t, y, dc, &tol);
    let (rlx, rly, rux, ruy) = build_bounds_vec(t, y, &hx, &hy, dc.mag_x);
    let (rex, rey) = compute_errors(tt, yt, &rlx, &rly, &rux, &ruy);

    let opts = crate::Options {
        tolerances: tol,
        ..crate::Options::default()
    };
    // Stage level: always comparable.
    let (nlx, nly, nux, nuy) = build_bounds(t, y, &hx, &hy, dc.mag_x);
    assert_eq!(bits(&nlx), bits(&rlx), "bounds lower x differs: {label}");
    assert_eq!(bits(&nly), bits(&rly), "bounds lower y differs: {label}");
    assert_eq!(bits(&nux), bits(&rux), "bounds upper x differs: {label}");
    assert_eq!(bits(&nuy), bits(&ruy), "bounds upper y differs: {label}");

    // Public API level, unless `compare` rejects the input up front
    // (e.g. a 2-point reference with a repeated x is an empty range).
    let r = crate::compare(t, y, tt, yt, &opts);
    if r.lower.0.is_empty() {
        return false;
    }
    assert_eq!(bits(&r.lower.0), bits(&rlx), "lower x differs: {label}");
    assert_eq!(bits(&r.lower.1), bits(&rly), "lower y differs: {label}");
    assert_eq!(bits(&r.upper.0), bits(&rux), "upper x differs: {label}");
    assert_eq!(bits(&r.upper.1), bits(&ruy), "upper y differs: {label}");
    assert_eq!(bits(&r.errors.0), bits(&rex), "errors x differs: {label}");
    assert_eq!(bits(&r.errors.1), bits(&rey), "errors y differs: {label}");
    true
}

#[test]
fn differential_generated_inputs() {
    let sizes = [2usize, 3, 4, 5, 8, 17, 50, 200, 1000, 4000];
    let noises = [0.0, 1e-4, 1e-2, 0.05, 0.5];
    let mut cases = 0usize;
    let mut api_cases = 0usize;
    let mut seed = 1u64;
    for &n in &sizes {
        for grid_kind in 0..4 {
            for sig_kind in 0..10 {
                for &noise in &noises {
                    // keep the large sizes to a subset to bound runtime
                    if n >= 1000 && matches!(seed % 3, 1 | 2) {
                        seed += 1;
                        continue;
                    }
                    let mut rng = Rng::new(seed);
                    seed += 1;
                    let span = [1.0, 10.0, 100.0, 1e4][rng.below(4)];
                    let t0 = [0.0, -5.0, 3.0, 1e6][rng.below(4)];
                    let t = grid(&mut rng, grid_kind, n, t0, span);
                    let y = signal(&mut rng, sig_kind, &t, noise);
                    let tol_kind = rng.below(7);
                    let tol = tolerances(&mut rng, tol_kind);
                    // test trajectory: same grid, different grid, or wider
                    let (tt, yt) = match rng.below(4) {
                        0 => (t.clone(), y.iter().map(|v| v + 1e-3).collect()),
                        1 => {
                            let m = (n / 2).max(2);
                            let tt = grid(&mut rng, 1, m, t0, span);
                            let yt = signal(&mut rng, sig_kind, &tt, noise);
                            (tt, yt)
                        }
                        2 => {
                            let m = n * 2 + 1;
                            let tt = grid(&mut rng, 0, m, t0 - 0.1 * span, span * 1.2);
                            let yt = signal(&mut rng, sig_kind, &tt, noise * 2.0);
                            (tt, yt)
                        }
                        _ => {
                            let tt = grid(&mut rng, 2, n.max(2), t0, span);
                            let yt = signal(&mut rng, 9, &tt, 0.0);
                            (tt, yt)
                        }
                    };
                    let label = format!(
                        "n={n} grid={grid_kind} sig={sig_kind} noise={noise} seed={}",
                        seed - 1
                    );
                    api_cases += usize::from(check_case(&t, &y, &tt, &yt, tol, &label));
                    cases += 1;
                }
            }
        }
    }
    assert!(cases > 1000, "too few cases: {cases}");
    assert!(
        api_cases * 10 > cases * 9,
        "too few API cases: {api_cases}/{cases}"
    );
}

#[test]
fn differential_long_noisy_signals() {
    // The workload that motivated the gap buffer: many loops per curve.
    for (seed, &(n, noise, rtol)) in [
        (20_000usize, 0.05, 2e-3),
        (20_000, 0.5, 2e-3),
        (20_000, 0.05, 2e-2),
        (20_000, 0.01, 1e-4),
        (50_000, 0.05, 2e-3),
    ]
    .iter()
    .enumerate()
    {
        let mut rng = Rng::new(1000 + seed as u64);
        let t = grid(&mut rng, 0, n, 0.0, 100.0);
        let y = signal(&mut rng, 0, &t, noise);
        let yt: Vec<f64> = y.iter().map(|v| v + 1e-3).collect();
        let tol = Tolerances {
            rtolx: rtol,
            rtoly: rtol,
            ..Tolerances::ZERO
        };
        let label = format!("long n={n} noise={noise}");
        assert!(check_case(&t, &y, &t, &yt, tol, &label));
    }
}

/// Run `f`, returning its result or `None` if it panicked.
fn outcome<F: FnOnce() -> (Vec<f64>, Vec<f64>)>(f: F) -> Option<(Vec<u64>, Vec<u64>)> {
    catch_unwind(AssertUnwindSafe(f))
        .ok()
        .map(|(x, y)| (bits(&x), bits(&y)))
}

#[test]
fn differential_remove_loop_arbitrary_polylines() {
    // Feed both implementations arbitrary polylines (not only corner
    // curves): random walks in x with frequent backward steps, ties and
    // duplicated points. Both must agree exactly, including on panics.
    let mut cases = 0usize;
    for seed in 0..4000u64 {
        let mut rng = Rng::new(50_000 + seed);
        let long = rng.below(10) == 0;
        let n = 2 + rng.below(if long { 400 } else { 40 });
        let back_p = [0.0, 0.1, 0.3, 0.5][rng.below(4)];
        let mut x = Vec::with_capacity(n);
        let mut y = Vec::with_capacity(n);
        let (mut cx, mut cy) = (0.0f64, 0.0f64);
        for _ in 0..n {
            match rng.below(10) {
                0 => {}                  // duplicate point
                1 => cy += rng.normal(), // vertical segment
                _ => {
                    let step = rng.uni();
                    cx += if rng.uni() < back_p {
                        -step * 2.0
                    } else {
                        step
                    };
                    cy += rng.normal();
                }
            }
            if rng.below(8) == 0 {
                cx = (cx * 4.0).round() / 4.0; // exact ties in x
            }
            x.push(cx);
            y.push(cy);
        }
        for curve in [Curve::Lower, Curve::Upper] {
            let (x1, y1) = (x.clone(), y.clone());
            let (x2, y2) = (x.clone(), y.clone());
            let reference = outcome(move || {
                let (mut a, mut b) = (x1, y1);
                remove_loop_vec(&mut a, &mut b, curve);
                (a, b)
            });
            let new = outcome(move || {
                let (mut a, mut b) = (x2, y2);
                remove_loop(&mut a, &mut b, curve);
                (a, b)
            });
            assert_eq!(new, reference, "seed={seed} curve={curve:?}");
            cases += 1;
        }
    }
    assert_eq!(cases, 8000);
}

#[cfg(feature = "json")]
#[test]
fn differential_lbnl_corpus() {
    use crate::io::{read_params, read_xy_csv};
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/corpus");
    let mut cases = 0usize;
    for entry in std::fs::read_dir(&root).expect("corpus dir") {
        let dir = entry.expect("corpus entry").path();
        let param_path = dir.join("param.json");
        if !param_path.exists() {
            continue;
        }
        let p = read_params(&param_path).expect("param.json");
        let (t, y) = read_xy_csv(&dir.join(&p.reference)).expect("reference csv");
        let (tt, yt) = read_xy_csv(&dir.join(&p.test)).expect("test csv");
        let tol = Tolerances {
            atolx: p.atolx.unwrap_or(0.0),
            atoly: p.atoly.unwrap_or(0.0),
            ltolx: p.ltolx.unwrap_or(0.0),
            ltoly: p.ltoly.unwrap_or(0.0),
            rtolx: p.rtolx.unwrap_or(0.0),
            rtoly: p.rtoly.unwrap_or(0.0),
        };
        let label = dir.display().to_string();
        assert!(check_case(&t, &y, &tt, &yt, tol, &label), "{label}");
        // Also with reference and test swapped, and with default tolerances.
        assert!(check_case(&tt, &yt, &t, &y, tol, &label), "{label} swapped");
        assert!(check_case(&t, &y, &tt, &yt, Tolerances::DEFAULT, &label));
        cases += 1;
    }
    assert_eq!(cases, 17);
}
