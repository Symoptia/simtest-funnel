//! Downsampling a failing corpus case keeps every violation visible when
//! the summary's worst points are pinned.
//!
//! The pinned values are shared with the Python (`tests/python`) and
//! TypeScript (`packages/sdk/tests`) suites to assert cross-language
//! parity of the downsampling.

#![cfg(feature = "json")]

use std::path::PathBuf;

use simtest_funnel_core::io::read_xy_csv;
use simtest_funnel_core::{compare, downsample_min_max, summarize, Options, Range, Tolerances};

#[test]
fn fail1_hard_downsampling_keeps_every_violation() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/corpus/fail1");
    let (tr, yr) = read_xy_csv(&dir.join("trended.csv")).unwrap();
    let (tt, yt) = read_xy_csv(&dir.join("simulated.csv")).unwrap();
    // The tolerances of the corpus case (param.json), given explicitly so
    // the pinned values do not depend on the library default.
    let opts = Options {
        tolerances: Tolerances {
            rtolx: 2e-3,
            rtoly: 2e-3,
            ..Tolerances::ZERO
        },
        x_range: Range::default(),
    };
    let r = compare(&tr, &yr, &tt, &yt, &opts);
    let s = summarize(&r, &tr, &opts);
    assert!(s.intervals.len() > 1);

    let buckets = 50;
    let pins: Vec<f64> = s.intervals.iter().map(|iv| iv.worst_x).collect();
    let d = downsample_min_max(&tt, &yt, buckets, &pins).unwrap();

    // Size bound and a hard reduction.
    assert!(d.indices.len() <= 2 * buckets + 2 + pins.len());
    assert!(d.indices.len() * 20 < tt.len());

    // The errors are on the test grid, so indices select deviations too.
    assert_eq!(r.errors.0, tt);
    for iv in &s.intervals {
        let kept_violation = d.indices.iter().any(|&j| {
            let x = tt[j];
            x >= iv.start_x && x <= iv.end_x && r.errors.1[j] != 0.0
        });
        assert!(
            kept_violation,
            "interval [{}, {}] lost all its violating points",
            iv.start_x, iv.end_x
        );
    }

    // Without pins, hard downsampling does lose violations: the pins matter.
    let unpinned = downsample_min_max(&tt, &yt, buckets, &[]).unwrap();
    let lost = s
        .intervals
        .iter()
        .filter(|iv| {
            !unpinned
                .indices
                .iter()
                .any(|&j| tt[j] >= iv.start_x && tt[j] <= iv.end_x && r.errors.1[j] != 0.0)
        })
        .count();
    assert!(lost > 0);

    // Post-processing only: comparison and summary are unchanged.
    let r2 = compare(&tr, &yr, &tt, &yt, &opts);
    assert_eq!(r2.status, r.status);
    assert_eq!(
        (&r2.lower, &r2.upper, &r2.errors),
        (&r.lower, &r.upper, &r.errors)
    );
    assert_eq!(summarize(&r2, &tr, &opts), s);

    // Pinned values (shared with the Python and TypeScript tests).
    assert_eq!(tt.len(), 5041);
    assert_eq!(pins.len(), 35);
    assert_eq!(d.indices.len(), 117);
    assert_eq!(d.indices.iter().sum::<usize>(), 311003);
    assert_eq!(&d.indices[..8], &[0, 101, 202, 303, 404, 504, 605, 706]);
    assert_eq!(&d.indices[d.indices.len() - 4..], &[4939, 4940, 5029, 5040]);
    for (k, &j) in d.indices.iter().enumerate() {
        assert_eq!((d.x[k], d.y[k]), (tt[j], yt[j]));
    }
}
