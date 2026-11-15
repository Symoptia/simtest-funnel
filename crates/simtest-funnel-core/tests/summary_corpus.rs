//! Violation summary consistency against a committed corpus case.
//!
//! The pinned values are shared with the Python (`tests/python`) and
//! TypeScript (`packages/sdk/tests`) suites to assert cross-language
//! parity of the summary.

#![cfg(feature = "json")]

use std::path::PathBuf;

use simtest_funnel_core::io::read_xy_csv;
use simtest_funnel_core::{compare, summarize, Options, Range, Status, Tolerances};

#[test]
fn fail1_summary_is_consistent_with_result() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/corpus/fail1");
    let (tr, yr) = read_xy_csv(&dir.join("trended.csv")).unwrap();
    let (tt, yt) = read_xy_csv(&dir.join("simulated.csv")).unwrap();
    let opts = Options {
        tolerances: Tolerances::DEFAULT,
        x_range: Range::default(),
    };
    let r = compare(&tr, &yr, &tt, &yt, &opts);
    let s = summarize(&tr, &opts, &r);
    assert_eq!(s.status, Status::Fail);

    // Consistency with the raw result.
    let (ex, ey) = &r.errors;
    let (lo, hi) = (tr[0], tr[tr.len() - 1]);
    let judged: Vec<(f64, f64)> = ex
        .iter()
        .zip(ey)
        .map(|(&x, &e)| (x, e))
        .filter(|&(x, _)| x >= lo && x <= hi)
        .collect();
    let outside = judged.iter().filter(|&&(_, e)| e != 0.0).count();
    assert_eq!(s.points_compared, judged.len());
    assert_eq!(s.points_outside, outside);
    assert_eq!(
        s.intervals.iter().map(|iv| iv.point_count).sum::<usize>(),
        outside
    );
    let max_abs = judged.iter().map(|&(_, e)| e.abs()).fold(0.0, f64::max);
    let w = s.worst.expect("fail has a worst deviation");
    assert_eq!(w.deviation.abs(), max_abs);
    assert!(s.intervals.windows(2).all(|p| p[0].end_x < p[1].start_x));

    // Pinned values (shared with the Python and TypeScript tests).
    assert_eq!(
        s.compared_range,
        Some(Range {
            lo: 54000.0,
            hi: 79200.0
        })
    );
    assert_eq!(s.intervals.len(), 35);
    let first = s.intervals[0];
    assert_eq!((first.start_x, first.end_x), (62435.0, 62530.0));
    assert_eq!(first.point_count, 20);
    assert_eq!(first.worst_deviation, 0.0023400000000000087);
    assert_eq!(first.worst_x, 62490.0);
    assert_eq!(w.x, 66925.0);
    assert_eq!(w.deviation, 0.019127999999996537);
    assert_eq!(w.tube_half_width_y, 0.003080000000001748);
    assert_eq!((s.points_compared, s.points_outside), (5041, 498));
    assert_eq!(s.fraction_of_points_outside, Some(0.09878992263439794));
    assert_eq!(s.fraction_of_span_outside, Some(0.0988095238095238));
}
