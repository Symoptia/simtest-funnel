//! Cancellation of running comparisons (`compare_cancellable`,
//! `compare_with_check`).
//!
//! The slow input is the shape that is still quadratic after the
//! `remove_loop` gap buffer: a nearly noise-free signal with a wide tube in
//! x (`rtolx = 0.1`), whose backward loops each span thousands of corners.
//! 100k samples take about 0.8 s in a release build and several seconds in
//! a debug build; the tests only ever run it until it is cancelled.

use simtest_funnel_core::{
    compare, compare_cancellable, compare_with_check, CancelToken, Cancelled, CompareResult,
    Options, Status,
};
use std::time::{Duration, Instant};

/// Deterministic xorshift noise in `[-0.5, 0.5)`.
fn noise(n: usize, seed: u64) -> Vec<f64> {
    let mut s = seed;
    (0..n)
        .map(|_| {
            s ^= s << 13;
            s ^= s >> 7;
            s ^= s << 17;
            (s >> 11) as f64 / (1u64 << 53) as f64 - 0.5
        })
        .collect()
}

/// Sine on `[0, 10]` with 0.1 % noise, reference and test with different
/// noise.
fn signals(n: usize) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let t: Vec<f64> = (0..n).map(|i| i as f64 / n as f64 * 10.0).collect();
    let a = noise(n, 0x9E37_79B9_7F4A_7C15);
    let b = noise(n, 0xD1B5_4A32_D192_ED03);
    let y_ref = t.iter().zip(&a).map(|(x, e)| x.sin() + 1e-3 * e).collect();
    let y_tst = t.iter().zip(&b).map(|(x, e)| x.sin() + 1e-3 * e).collect();
    (t, y_ref, y_tst)
}

fn wide_x() -> Options {
    let mut o = Options::default();
    o.tolerances.rtolx = 0.1;
    o
}

/// Bounds, deviations and status compared bit for bit.
fn assert_bit_identical(a: &CompareResult, b: &CompareResult) {
    let bits = |v: &[f64]| v.iter().map(|x| x.to_bits()).collect::<Vec<_>>();
    assert_eq!(a.status, b.status);
    assert_eq!(bits(&a.lower.0), bits(&b.lower.0));
    assert_eq!(bits(&a.lower.1), bits(&b.lower.1));
    assert_eq!(bits(&a.upper.0), bits(&b.upper.0));
    assert_eq!(bits(&a.upper.1), bits(&b.upper.1));
    assert_eq!(bits(&a.errors.0), bits(&b.errors.0));
    assert_eq!(bits(&a.errors.1), bits(&b.errors.1));
}

#[test]
fn unfired_token_gives_identical_result() {
    // Noisy, wide in x: many loop removals and many checkpoints.
    let (t, yr, yt) = signals(5_000);
    let opts = wide_x();
    let plain = compare(&t, &yr, &t, &yt, &opts);
    let token = CancelToken::new().with_timeout(Duration::from_secs(3600));
    let tok = compare_cancellable(&t, &yr, &t, &yt, &opts, &token).expect("not cancelled");
    assert_bit_identical(&plain, &tok);
    let mut calls = 0usize;
    let chk = compare_with_check(&t, &yr, &t, &yt, &opts, || {
        calls += 1;
        Ok(())
    })
    .expect("not cancelled");
    assert_bit_identical(&plain, &chk);
    assert!(calls >= 7, "checkpoints between phases: {calls}");
}

#[test]
fn deadline_in_the_past_does_no_work() {
    let (t, yr, yt) = signals(100_000);
    let token = CancelToken::new().with_deadline(Instant::now() - Duration::from_millis(1));
    let start = Instant::now();
    let r = compare_cancellable(&t, &yr, &t, &yt, &wide_x(), &token);
    assert_eq!(r.err(), Some(Cancelled::DeadlineExceeded));
    assert!(
        start.elapsed() < Duration::from_millis(200),
        "{:?}",
        start.elapsed()
    );
}

#[test]
fn already_cancelled_token_does_no_work() {
    let (t, yr, yt) = signals(100_000);
    let token = CancelToken::new();
    token.cancel();
    let r = compare_cancellable(&t, &yr, &t, &yt, &wide_x(), &token);
    assert_eq!(r.err(), Some(Cancelled::Requested));
}

#[test]
fn deadline_stops_a_slow_comparison_promptly() {
    let (t, yr, yt) = signals(100_000);
    let opts = wide_x();
    let limit = Duration::from_millis(50);
    let start = Instant::now();
    let token = CancelToken::new().with_timeout(limit);
    let r = compare_cancellable(&t, &yr, &t, &yt, &opts, &token);
    let took = start.elapsed();
    // Takes >= 0.8 s in release when not stopped.
    assert_eq!(r.err(), Some(Cancelled::DeadlineExceeded));
    assert!(took >= limit);
    assert!(took < Duration::from_millis(500), "stopped after {took:?}");
}

#[test]
fn flag_set_from_another_thread_stops_the_comparison() {
    let (t, yr, yt) = signals(100_000);
    let opts = wide_x();
    let token = CancelToken::new();
    let remote = token.clone();
    let start = Instant::now();
    let canceller = std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(50));
        remote.cancel();
    });
    let r = compare_cancellable(&t, &yr, &t, &yt, &opts, &token);
    let took = start.elapsed();
    canceller.join().unwrap();
    assert_eq!(r.err(), Some(Cancelled::Requested));
    assert!(took < Duration::from_millis(500), "stopped after {took:?}");
}

#[test]
fn check_error_is_returned_and_stops_further_calls() {
    let (t, yr, yt) = signals(100_000);
    let mut calls = 0usize;
    let r = compare_with_check(&t, &yr, &t, &yt, &wide_x(), || {
        calls += 1;
        if calls == 20 {
            Err(Cancelled::Requested)
        } else {
            Ok(())
        }
    });
    assert_eq!(r.err(), Some(Cancelled::Requested));
    assert_eq!(calls, 20);
}

#[test]
fn invalid_input_reports_status_even_when_cancelled() {
    let token = CancelToken::new();
    token.cancel();
    let r = compare_cancellable(
        &[0.0, 1.0, 2.0],
        &[0.0, 1.0],
        &[0.0, 1.0],
        &[0.0, 1.0],
        &Options::default(),
        &token,
    )
    .expect("validation precedes cancellation");
    assert_eq!(r.status, Status::LengthMismatch);
    let r = compare_with_check(
        &[0.0, 2.0, 1.0],
        &[0.0, 1.0, 2.0],
        &[0.0, 1.0, 2.0],
        &[0.0, 1.0, 2.0],
        &Options::default(),
        || panic!("check must not be called for invalid input"),
    )
    .unwrap();
    assert_eq!(r.status, Status::NonMonotonic);
}
