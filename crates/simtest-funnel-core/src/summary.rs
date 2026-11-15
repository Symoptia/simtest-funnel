//! Violation summary: a compact, deterministic description of how much
//! and where a comparison violated the tolerances it was run with.
//!
//! The summary is derived from an existing comparison (its reference
//! x-values, its [`Options`] and its [`CompareResult`]); it never
//! re-runs or alters the comparison. See [`summarize`].

use crate::compare::CompareResult;
use crate::errors::interpolate_clamped;
use crate::options::{Options, Range, Tolerances};
use crate::status::Status;

#[cfg(feature = "json")]
use serde::Serialize;

/// Side of the tube on which a violation lies.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(feature = "json", derive(Serialize), serde(rename_all = "lowercase"))]
pub enum Direction {
    /// The test trajectory lies above the upper bound (positive deviation).
    Above,
    /// The test trajectory lies below the lower bound (negative deviation).
    Below,
}

impl Direction {
    /// Lower-case name: `"above"` or `"below"`.
    pub fn as_str(self) -> &'static str {
        match self {
            Direction::Above => "above",
            Direction::Below => "below",
        }
    }
}

/// A maximal run of consecutive judged test points that lie outside the
/// tube on the same side.
#[derive(Debug, Clone, Copy, PartialEq)]
#[cfg_attr(feature = "json", derive(Serialize))]
pub struct ViolationInterval {
    /// x of the first test point of the run.
    pub start_x: f64,
    /// x of the last test point of the run (equal to `start_x` for a
    /// single-point violation).
    pub end_x: f64,
    /// Side of the tube the run lies on.
    pub direction: Direction,
    /// Number of test points in the run (at least 1).
    pub point_count: usize,
    /// Signed deviation with the largest magnitude within the run
    /// (first occurrence on ties).
    pub worst_deviation: f64,
    /// x at which `worst_deviation` occurs.
    pub worst_x: f64,
}

/// The overall worst deviation of a comparison.
#[derive(Debug, Clone, Copy, PartialEq)]
#[cfg_attr(feature = "json", derive(Serialize))]
pub struct WorstDeviation {
    /// x at which the worst deviation occurs.
    pub x: f64,
    /// Signed deviation with the largest magnitude over all judged test
    /// points (first occurrence on ties).
    pub deviation: f64,
    /// Tube half-width in y at `x`: half the vertical distance between the
    /// upper and lower bound, both linearly interpolated at `x`. `NaN` only
    /// if the result carries no bounds.
    pub tube_half_width_y: f64,
}

/// Summary of how much the tolerances of a comparison were violated.
///
/// A test point is *judged* when its x lies in the effective range
/// `[max(x_range.lo, t_ref[0]), min(x_range.hi, t_ref[last])]` — the same
/// points that decide [`Status::Fail`]. Only judged points contribute to
/// intervals, the worst deviation and the shares.
#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "json", derive(Serialize))]
pub struct ViolationSummary {
    /// Comparison status, unchanged.
    pub status: Status,
    /// Tolerances echoed from the options passed to [`summarize`]: the six
    /// effective (resolved) coefficients, never partial input.
    pub tolerances: Tolerances,
    /// Requested x-range echoed from the options (may be infinite).
    pub x_range: Range,
    /// `[first judged x, last judged x]`; `None` if no point was judged.
    pub compared_range: Option<Range>,
    /// Violation intervals in increasing x order.
    pub intervals: Vec<ViolationInterval>,
    /// Overall worst deviation; `None` if no judged point is outside.
    pub worst: Option<WorstDeviation>,
    /// Number of judged test points.
    pub points_compared: usize,
    /// Number of judged test points outside the tube.
    pub points_outside: usize,
    /// `points_outside / points_compared`; `None` if no point was judged.
    pub fraction_of_points_outside: Option<f64>,
    /// Share of the compared range outside the tube. Each judged point
    /// represents the x-length halfway to its neighbouring judged points
    /// (clamped at the ends); the share is the represented length of the
    /// points outside divided by the compared range length. Equal to
    /// `fraction_of_points_outside` when the compared range has zero length;
    /// `None` if no point was judged.
    pub fraction_of_span_outside: Option<f64>,
}

fn did_not_compare(status: Status) -> bool {
    matches!(
        status,
        Status::NonMonotonic
            | Status::LengthMismatch
            | Status::EmptyRange
            | Status::BufferTooSmall
            | Status::InsufficientData
    )
}

/// `|candidate| > |current|`: strict, so the first occurrence wins ties.
#[inline]
fn is_worse(candidate: f64, current: f64) -> bool {
    candidate.abs() > current.abs()
}

fn tube_half_width_at(result: &CompareResult, x: f64) -> f64 {
    let ln = result.lower.0.len().min(result.lower.1.len());
    let un = result.upper.0.len().min(result.upper.1.len());
    if ln == 0 || un == 0 {
        return f64::NAN;
    }
    let lo = interpolate_clamped(&result.lower.0[..ln], &result.lower.1[..ln], &[x]);
    let up = interpolate_clamped(&result.upper.0[..un], &result.upper.1[..un], &[x]);
    0.5 * (up[0] - lo[0])
}

/// Summarize how much a comparison violated its tolerances.
///
/// `t_ref` and `opts` must be the reference x-values and options that were
/// passed to [`crate::compare()`] to produce `result`. The argument order
/// `(result, t_ref, opts)` is the same in the Python and TypeScript APIs. Only the first and
/// last value of `t_ref` are used (to delimit the effective range); test
/// x-values and deviations are taken from `result.errors`.
///
/// For validation statuses ([`Status::NonMonotonic`],
/// [`Status::LengthMismatch`], [`Status::EmptyRange`],
/// [`Status::BufferTooSmall`], [`Status::InsufficientData`]) — or whenever
/// no test point is judged — the summary carries only the status and the
/// echoed settings: no intervals, no worst deviation, no compared range,
/// zero counts and `None` shares.
pub fn summarize(result: &CompareResult, t_ref: &[f64], opts: &Options) -> ViolationSummary {
    let mut s = ViolationSummary {
        status: result.status,
        tolerances: opts.tolerances,
        x_range: opts.x_range,
        compared_range: None,
        intervals: Vec::new(),
        worst: None,
        points_compared: 0,
        points_outside: 0,
        fraction_of_points_outside: None,
        fraction_of_span_outside: None,
    };
    if did_not_compare(result.status) {
        return s;
    }
    let (Some(&ref_lo), Some(&ref_hi)) = (t_ref.first(), t_ref.last()) else {
        return s;
    };
    let eff_lo = opts.x_range.lo.max(ref_lo);
    let eff_hi = opts.x_range.hi.min(ref_hi);

    // Judged points: (x, deviation), in test order (x non-decreasing).
    let n = result.errors.0.len().min(result.errors.1.len());
    let judged: Vec<(f64, f64)> = (0..n)
        .map(|j| (result.errors.0[j], result.errors.1[j]))
        .filter(|&(x, _)| x >= eff_lo && x <= eff_hi)
        .collect();
    let m = judged.len();
    if m == 0 {
        return s;
    }
    let first_x = judged[0].0;
    let last_x = judged[m - 1].0;
    let span = last_x - first_x;

    let mut outside_len = 0.0_f64;
    let mut current: Option<ViolationInterval> = None;
    let mut worst: Option<(f64, f64)> = None; // (x, deviation)

    for (k, &(x, e)) in judged.iter().enumerate() {
        if e == 0.0 {
            if let Some(iv) = current.take() {
                s.intervals.push(iv);
            }
            continue;
        }
        s.points_outside += 1;
        let prev_x = if k == 0 { first_x } else { judged[k - 1].0 };
        let next_x = if k + 1 == m { last_x } else { judged[k + 1].0 };
        outside_len += 0.5 * (next_x - prev_x);

        if worst.is_none_or(|(_, w)| is_worse(e, w)) {
            worst = Some((x, e));
        }

        let dir = if e > 0.0 {
            Direction::Above
        } else {
            Direction::Below
        };
        match current.as_mut() {
            Some(iv) if iv.direction == dir => {
                iv.end_x = x;
                iv.point_count += 1;
                if is_worse(e, iv.worst_deviation) {
                    iv.worst_deviation = e;
                    iv.worst_x = x;
                }
            }
            _ => {
                if let Some(iv) = current.take() {
                    s.intervals.push(iv);
                }
                current = Some(ViolationInterval {
                    start_x: x,
                    end_x: x,
                    direction: dir,
                    point_count: 1,
                    worst_deviation: e,
                    worst_x: x,
                });
            }
        }
    }
    if let Some(iv) = current.take() {
        s.intervals.push(iv);
    }

    s.points_compared = m;
    s.compared_range = Some(Range {
        lo: first_x,
        hi: last_x,
    });
    let point_frac = s.points_outside as f64 / m as f64;
    s.fraction_of_points_outside = Some(point_frac);
    s.fraction_of_span_outside = Some(if span > 0.0 {
        outside_len / span
    } else {
        point_frac
    });
    s.worst = worst.map(|(x, deviation)| WorstDeviation {
        x,
        deviation,
        tube_half_width_y: tube_half_width_at(result, x),
    });
    s
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::compare::compare;

    fn atoly(v: f64) -> Options {
        Options {
            tolerances: Tolerances {
                atoly: v,
                ..Tolerances::ZERO
            },
            x_range: Range::default(),
        }
    }

    /// Hand-built result with a flat tube `[-1, 1]` over `[0, xmax]`.
    fn flat(xs: &[f64], errs: &[f64], status: Status) -> CompareResult {
        let xmax = *xs.last().unwrap();
        CompareResult {
            status,
            lower: (vec![0.0, xmax], vec![-1.0, -1.0]),
            upper: (vec![0.0, xmax], vec![1.0, 1.0]),
            errors: (xs.to_vec(), errs.to_vec()),
        }
    }

    #[test]
    fn one_excursion_above() {
        let xs = [0.0, 1.0, 2.0, 3.0, 4.0];
        let r = flat(&xs, &[0.0, 0.2, 0.5, 0.1, 0.0], Status::Fail);
        let s = summarize(&r, &xs, &atoly(1.0));
        assert_eq!(s.status, Status::Fail);
        assert_eq!(s.intervals.len(), 1);
        let iv = s.intervals[0];
        assert_eq!((iv.start_x, iv.end_x), (1.0, 3.0));
        assert_eq!(iv.direction, Direction::Above);
        assert_eq!(iv.point_count, 3);
        assert_eq!((iv.worst_deviation, iv.worst_x), (0.5, 2.0));
        let w = s.worst.unwrap();
        assert_eq!((w.x, w.deviation, w.tube_half_width_y), (2.0, 0.5, 1.0));
        assert_eq!(s.points_compared, 5);
        assert_eq!(s.points_outside, 3);
        assert_eq!(s.fraction_of_points_outside, Some(0.6));
        // points 1,2,3 each represent length 1 out of span 4.
        assert_eq!(s.fraction_of_span_outside, Some(0.75));
        assert_eq!(s.compared_range, Some(Range { lo: 0.0, hi: 4.0 }));
    }

    #[test]
    fn sign_flip_splits_intervals() {
        let xs = [0.0, 1.0, 2.0, 3.0];
        let r = flat(&xs, &[0.0, 0.3, -0.4, 0.0], Status::Fail);
        let s = summarize(&r, &xs, &atoly(1.0));
        assert_eq!(s.intervals.len(), 2);
        assert_eq!(s.intervals[0].direction, Direction::Above);
        assert_eq!(s.intervals[1].direction, Direction::Below);
        assert_eq!(s.worst.unwrap().deviation, -0.4);
    }

    #[test]
    fn boundary_single_point_violations() {
        let xs = [0.0, 1.0, 2.0, 3.0];
        let r = flat(&xs, &[-0.2, 0.0, 0.0, 0.1], Status::Fail);
        let s = summarize(&r, &xs, &atoly(1.0));
        assert_eq!(s.intervals.len(), 2);
        let a = s.intervals[0];
        assert_eq!((a.start_x, a.end_x, a.point_count), (0.0, 0.0, 1));
        let b = s.intervals[1];
        assert_eq!((b.start_x, b.end_x, b.point_count), (3.0, 3.0, 1));
        // each end point represents 0.5 of span 3.
        assert_eq!(s.fraction_of_span_outside, Some(1.0 / 3.0));
    }

    #[test]
    fn span_share_weights_by_spacing() {
        let xs = [0.0, 1.0, 2.0, 4.0];
        let r = flat(&xs, &[0.0, 0.0, 0.0, 0.5], Status::Fail);
        let s = summarize(&r, &xs, &atoly(1.0));
        assert_eq!(s.fraction_of_points_outside, Some(0.25));
        assert_eq!(s.fraction_of_span_outside, Some(0.25));
    }

    #[test]
    fn all_outside_shares_are_one() {
        let xs = [0.0, 1.0, 3.0];
        let r = flat(&xs, &[0.5, 0.5, 0.5], Status::Fail);
        let s = summarize(&r, &xs, &atoly(1.0));
        assert_eq!(s.fraction_of_points_outside, Some(1.0));
        assert_eq!(s.fraction_of_span_outside, Some(1.0));
    }

    #[test]
    fn zero_length_range_falls_back_to_point_share() {
        let xs = [1.0, 1.0];
        let r = flat(&xs, &[0.0, 0.5], Status::Fail);
        let s = summarize(&r, &xs, &atoly(1.0));
        assert_eq!(s.compared_range, Some(Range { lo: 1.0, hi: 1.0 }));
        assert_eq!(s.fraction_of_span_outside, Some(0.5));
    }

    #[test]
    fn ties_pick_first_occurrence() {
        let xs = [0.0, 1.0, 2.0];
        let r = flat(&xs, &[0.5, -0.5, 0.5], Status::Fail);
        let s = summarize(&r, &xs, &atoly(1.0));
        let w = s.worst.unwrap();
        assert_eq!((w.x, w.deviation), (0.0, 0.5));
    }

    #[test]
    fn out_of_range_deviations_ignored() {
        // Test extends beyond the reference; compare gives MissingReference
        // with non-zero errors outside the reference extent.
        let t = [1.0, 2.0, 3.0];
        let y = [1.0, 2.0, 3.0];
        let tt = [0.0, 1.0, 2.0, 3.0, 4.0];
        let yt = [5.0, 1.0, 2.0, 3.0, 9.0];
        let opts = atoly(0.5);
        let r = compare(&t, &y, &tt, &yt, &opts);
        assert_eq!(r.status, Status::MissingReference);
        assert!(r.errors.1.iter().any(|&e| e != 0.0));
        let s = summarize(&r, &t, &opts);
        assert!(s.intervals.is_empty());
        assert!(s.worst.is_none());
        assert_eq!(s.points_compared, 3);
        assert_eq!(s.points_outside, 0);
        assert_eq!(s.fraction_of_span_outside, Some(0.0));
        assert_eq!(s.compared_range, Some(Range { lo: 1.0, hi: 3.0 }));
    }

    #[test]
    fn coverage_window_consistent_with_status() {
        // Test covers 0..1.1, reference 0..1. With x_range [0, 1] the
        // coverage check passes and the summary judges exactly the test
        // points inside the window.
        let t = [0.0, 0.5, 1.0];
        let y = [0.0, 0.5, 1.0];
        let tt = [0.0, 0.25, 0.5, 0.75, 1.0, 1.1];
        let yt = [0.0, 0.25, 0.5, 0.75, 1.0, 5.0];
        let opts = Options {
            x_range: Range { lo: 0.0, hi: 1.0 },
            ..atoly(0.1)
        };
        let r = compare(&t, &y, &tt, &yt, &opts);
        assert_eq!(r.status, Status::Pass);
        let s = summarize(&r, &t, &opts);
        assert_eq!(s.points_compared, 5);
        assert_eq!(s.points_outside, 0);
        assert_eq!(s.compared_range, Some(Range { lo: 0.0, hi: 1.0 }));
        // Unbounded: the same data is MissingReference, still no violation.
        let r = compare(&t, &y, &tt, &yt, &atoly(0.1));
        assert_eq!(r.status, Status::MissingReference);
        assert_eq!(summarize(&r, &t, &atoly(0.1)).points_outside, 0);
    }

    #[test]
    fn x_range_restricts_judged_points() {
        let xs = [0.0, 1.0, 2.0, 3.0, 4.0];
        let r = flat(&xs, &[0.9, 0.0, 0.0, 0.0, 0.0], Status::Fail);
        let opts = Options {
            x_range: Range { lo: 1.0, hi: 3.0 },
            ..atoly(1.0)
        };
        let s = summarize(&r, &xs, &opts);
        assert_eq!(s.x_range, Range { lo: 1.0, hi: 3.0 });
        assert_eq!(s.compared_range, Some(Range { lo: 1.0, hi: 3.0 }));
        assert_eq!(s.points_compared, 3);
        assert!(s.intervals.is_empty());
    }

    #[test]
    fn pass_has_no_violations() {
        let t = [0.0, 1.0, 2.0, 3.0];
        let y = [0.0, 1.0, 2.0, 3.0];
        let opts = atoly(0.5);
        let r = compare(&t, &y, &t, &y, &opts);
        let s = summarize(&r, &t, &opts);
        assert_eq!(s.status, Status::Pass);
        assert!(s.intervals.is_empty());
        assert!(s.worst.is_none());
        assert_eq!(s.fraction_of_points_outside, Some(0.0));
        assert_eq!(s.fraction_of_span_outside, Some(0.0));
        assert_eq!(s.tolerances.atoly, 0.5);
    }

    #[test]
    fn echoes_resolved_partial_tolerances() {
        let t = [0.0, 1.0, 2.0, 3.0];
        let y = [0.0, 1.0, 2.0, 3.0];
        let opts = Options {
            tolerances: crate::options::PartialTolerances {
                atoly: Some(0.2),
                ..Default::default()
            }
            .resolve(),
            x_range: Range::default(),
        };
        let r = compare(&t, &y, &t, &y, &opts);
        let s = summarize(&r, &t, &opts);
        assert_eq!(
            s.tolerances,
            Tolerances {
                atoly: 0.2,
                rtolx: 2e-3,
                ..Tolerances::ZERO
            }
        );
        let s_default = summarize(&r, &t, &Options::default());
        assert_eq!(s_default.tolerances, Tolerances::DEFAULT);
    }

    #[test]
    fn validation_status_yields_empty_summary() {
        let t = [0.0, 2.0, 1.0];
        let y = [0.0, 1.0, 2.0];
        let opts = atoly(0.5);
        let r = compare(&t, &y, &[0.0, 1.0, 2.0], &y, &opts);
        assert_eq!(r.status, Status::NonMonotonic);
        let s = summarize(&r, &t, &opts);
        assert_eq!(s.status, Status::NonMonotonic);
        assert_eq!(s.tolerances, opts.tolerances);
        assert_eq!(s.x_range, opts.x_range);
        assert!(s.intervals.is_empty());
        assert!(s.worst.is_none());
        assert!(s.compared_range.is_none());
        assert_eq!((s.points_compared, s.points_outside), (0, 0));
        assert!(s.fraction_of_points_outside.is_none());
        assert!(s.fraction_of_span_outside.is_none());
    }

    #[test]
    fn real_compare_worst_matches_errors_and_half_width() {
        let t = [0.0, 1.0, 2.0, 3.0, 4.0];
        let y = [1.0, 1.0, 1.0, 1.0, 1.0];
        let yt = [1.0, 1.0, 1.5, 1.0, 1.0];
        let opts = atoly(0.2);
        let r = compare(&t, &y, &t, &yt, &opts);
        assert_eq!(r.status, Status::Fail);
        let before = (r.errors.clone(), r.lower.clone(), r.upper.clone());
        let s = summarize(&r, &t, &opts);
        assert_eq!(before, (r.errors.clone(), r.lower.clone(), r.upper.clone()));
        let w = s.worst.unwrap();
        assert_eq!(w.x, 2.0);
        assert!((w.deviation - 0.3).abs() < 1e-12);
        assert!((w.tube_half_width_y - 0.2).abs() < 1e-12);
        assert_eq!(s, summarize(&r, &t, &opts));
    }

    #[test]
    fn missing_bounds_give_nan_half_width() {
        let r = CompareResult {
            status: Status::Fail,
            lower: (vec![], vec![]),
            upper: (vec![], vec![]),
            errors: (vec![0.0, 1.0], vec![0.5, 0.0]),
        };
        let s = summarize(&r, &[0.0, 1.0], &atoly(0.1));
        assert!(s.worst.unwrap().tube_half_width_y.is_nan());
    }

    #[cfg(feature = "json")]
    #[test]
    fn json_serialisation() {
        let xs = [0.0, 1.0, 2.0];
        let r = flat(&xs, &[0.0, 0.5, 0.0], Status::Fail);
        let s = summarize(&r, &xs, &atoly(1.0));
        let j = serde_json::to_string(&s).unwrap();
        assert!(j.contains("\"status\":\"Fail\""), "{j}");
        assert!(j.contains("\"direction\":\"above\""), "{j}");
        assert!(j.contains("\"x_range\":{\"lo\":null,\"hi\":null}"), "{j}");
        assert!(j.contains("\"fraction_of_span_outside\":0.5"), "{j}");
    }
}
