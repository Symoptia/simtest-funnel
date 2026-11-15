//! Output downsampling: reduce a signal to a bounded number of points for
//! plots and reports while keeping each region's extremes and
//! caller-pinned points. See [`downsample_min_max`].
//!
//! Downsampling is post-processing only. It is never applied by
//! [`crate::compare()`] or [`crate::summarize()`]; comparisons and
//! violation summaries are always computed on full-resolution signals.

use std::fmt;

/// Samples kept by [`downsample_min_max`], in input order.
///
/// `x[k] == input_x[indices[k]]` and `y[k] == input_y[indices[k]]` for
/// every `k`; `indices` is strictly increasing.
#[derive(Debug, Clone, PartialEq)]
pub struct Downsampled {
    /// Indices of the kept samples into the input arrays.
    pub indices: Vec<usize>,
    /// x-values of the kept samples.
    pub x: Vec<f64>,
    /// y-values of the kept samples.
    pub y: Vec<f64>,
}

/// Invalid input to [`downsample_min_max`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DownsampleError {
    /// `x` and `y` have different lengths.
    LengthMismatch {
        /// Length of `x`.
        x_len: usize,
        /// Length of `y`.
        y_len: usize,
    },
    /// The bucket count is zero.
    ZeroBuckets,
    /// An x-value is NaN or infinite.
    NonFiniteX {
        /// Index of the first non-finite x-value.
        index: usize,
    },
    /// The x-values decrease somewhere (equal consecutive values are allowed).
    NonMonotonic {
        /// First index `i` with `x[i] < x[i - 1]`.
        index: usize,
    },
}

impl fmt::Display for DownsampleError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            DownsampleError::LengthMismatch { x_len, y_len } => {
                write!(f, "length mismatch: x has {x_len} values but y has {y_len}")
            }
            DownsampleError::ZeroBuckets => f.write_str("buckets must be at least 1"),
            DownsampleError::NonFiniteX { index } => {
                write!(f, "non-finite x-value at index {index}")
            }
            DownsampleError::NonMonotonic { index } => {
                write!(f, "non-monotonic x: x[{index}] < x[{}]", index - 1)
            }
        }
    }
}

impl std::error::Error for DownsampleError {}

fn validate(x: &[f64], y: &[f64], buckets: usize) -> Result<(), DownsampleError> {
    if x.len() != y.len() {
        return Err(DownsampleError::LengthMismatch {
            x_len: x.len(),
            y_len: y.len(),
        });
    }
    if buckets == 0 {
        return Err(DownsampleError::ZeroBuckets);
    }
    if let Some(index) = x.iter().position(|v| !v.is_finite()) {
        return Err(DownsampleError::NonFiniteX { index });
    }
    if let Some(i) = x.windows(2).position(|w| w[1] < w[0]) {
        return Err(DownsampleError::NonMonotonic { index: i + 1 });
    }
    Ok(())
}

/// Maps x-values to equal-width bucket indices over `[x_first, x_last]`.
struct Bucketer {
    x0: f64,
    span: f64,
    halve: bool,
    buckets: usize,
}

impl Bucketer {
    fn new(x0: f64, x_last: f64, buckets: usize) -> Self {
        let span = x_last - x0;
        if span.is_finite() {
            Bucketer {
                x0,
                span,
                halve: false,
                buckets,
            }
        } else {
            // The difference of two finite values overflowed; halving both
            // operands keeps every step finite and monotone.
            Bucketer {
                x0,
                span: x_last * 0.5 - x0 * 0.5,
                halve: true,
                buckets,
            }
        }
    }

    /// `min(B - 1, floor((x - x0) / span * B))`; 0 when the span is 0.
    fn bucket(&self, x: f64) -> usize {
        if self.span <= 0.0 {
            return 0;
        }
        let offset = if self.halve {
            x * 0.5 - self.x0 * 0.5
        } else {
            x - self.x0
        };
        let b = self.buckets as f64;
        let f = (offset / self.span * b).floor();
        if f >= b {
            self.buckets - 1
        } else {
            // `f >= 0` because x >= x0; the cast saturates.
            (f as usize).min(self.buckets - 1)
        }
    }
}

/// Index of the sample nearest to `p` (ties go to the lower x) in the
/// non-decreasing, non-empty `x`.
fn nearest(x: &[f64], p: f64) -> usize {
    let j = x.partition_point(|&v| v < p);
    if j == 0 {
        0
    } else if j == x.len() {
        x.len() - 1
    } else if p - x[j - 1] <= x[j] - p {
        j - 1
    } else {
        j
    }
}

/// Reduce a signal to the lowest and highest sample of each of `buckets`
/// equal-width x-buckets, plus the first and last sample and the samples
/// selected by `pinned_x`.
///
/// Intended for output only (plots, reports, agent responses): never feed
/// the result back into [`crate::compare()`].
///
/// **Buckets.** The x-extent `[x[0], x[n-1]]` is split into `buckets`
/// buckets of equal x-width; sample `i` falls in bucket
/// `min(B - 1, floor((x[i] - x[0]) / (x[n-1] - x[0]) * B))` (all samples in
/// bucket 0 when the extent has zero width). For every non-empty bucket the
/// first sample with the lowest y and the first sample with the highest y
/// are kept (once if they coincide). NaN y-values are never selected as
/// extremes.
///
/// **Pins.** Each finite pin keeps the sample with the nearest x (ties
/// between two neighbours go to the lower x) and every other sample with
/// exactly that x-value (repeated event time points). Pins outside the
/// extent therefore select the first or last sample; NaN pins are ignored.
/// The intended pins are the `worst_x` of every
/// [`crate::ViolationInterval`] of the comparison's summary, so a plot of
/// the result never hides a violation the full data contains.
///
/// **Size.** For `n` samples the result has at most
/// `min(n, 2 * buckets + 2 + M)` samples, where `M` is the number of
/// samples selected by pins (at most the number of distinct finite pins
/// when `x` is strictly increasing). If `n <= 2 * buckets` every sample is
/// returned unchanged (pins have no effect).
///
/// The result is in input order with no duplicates.
///
/// # Errors
///
/// Validation runs first, also for small inputs:
/// [`DownsampleError::LengthMismatch`] if `x.len() != y.len()`,
/// [`DownsampleError::ZeroBuckets`] if `buckets == 0`,
/// [`DownsampleError::NonFiniteX`] for a NaN or infinite x-value and
/// [`DownsampleError::NonMonotonic`] if `x` decreases anywhere.
///
/// # Example
///
/// ```
/// use simtest_funnel_core::downsample_min_max;
///
/// let x: Vec<f64> = (0..10).map(f64::from).collect();
/// let y = [0.0, 5.0, 1.0, 2.0, 9.0, 3.0, 4.0, 8.0, 6.0, 7.0];
/// let d = downsample_min_max(&x, &y, 2, &[]).unwrap();
/// assert_eq!(d.indices, vec![0, 4, 5, 7, 9]);
/// let d = downsample_min_max(&x, &y, 2, &[2.2]).unwrap();
/// assert_eq!(d.indices, vec![0, 2, 4, 5, 7, 9]);
/// ```
pub fn downsample_min_max(
    x: &[f64],
    y: &[f64],
    buckets: usize,
    pinned_x: &[f64],
) -> Result<Downsampled, DownsampleError> {
    validate(x, y, buckets)?;
    let n = x.len();
    if n <= buckets.saturating_mul(2) {
        return Ok(Downsampled {
            indices: (0..n).collect(),
            x: x.to_vec(),
            y: y.to_vec(),
        });
    }

    let mut keep = vec![false; n];
    keep[0] = true;
    keep[n - 1] = true;

    // Buckets are contiguous index runs: the bucket index is monotone in x.
    let bucketer = Bucketer::new(x[0], x[n - 1], buckets);
    let mut i = 0;
    while i < n {
        let k = bucketer.bucket(x[i]);
        let mut lo: Option<usize> = None;
        let mut hi: Option<usize> = None;
        while i < n && bucketer.bucket(x[i]) == k {
            let v = y[i];
            if !v.is_nan() {
                if lo.is_none_or(|j| v < y[j]) {
                    lo = Some(i);
                }
                if hi.is_none_or(|j| v > y[j]) {
                    hi = Some(i);
                }
            }
            i += 1;
        }
        for j in [lo, hi].into_iter().flatten() {
            keep[j] = true;
        }
    }

    for &p in pinned_x {
        if p.is_nan() {
            continue;
        }
        let xv = x[nearest(x, p)];
        let first = x.partition_point(|&v| v < xv);
        let last = x.partition_point(|&v| v <= xv);
        for flag in &mut keep[first..last] {
            *flag = true;
        }
    }

    let indices: Vec<usize> = (0..n).filter(|&j| keep[j]).collect();
    Ok(Downsampled {
        x: indices.iter().map(|&j| x[j]).collect(),
        y: indices.iter().map(|&j| y[j]).collect(),
        indices,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn example() -> (Vec<f64>, Vec<f64>) {
        let x: Vec<f64> = (0..10).map(f64::from).collect();
        let y = vec![0.0, 5.0, 1.0, 2.0, 9.0, 3.0, 4.0, 8.0, 6.0, 7.0];
        (x, y)
    }

    fn idx(x: &[f64], y: &[f64], b: usize, pins: &[f64]) -> Vec<usize> {
        downsample_min_max(x, y, b, pins).unwrap().indices
    }

    #[test]
    fn two_buckets_keep_extremes() {
        let (x, y) = example();
        assert_eq!(idx(&x, &y, 2, &[]), vec![0, 4, 5, 7, 9]);
    }

    #[test]
    fn pin_keeps_nearest_sample() {
        let (x, y) = example();
        assert_eq!(idx(&x, &y, 2, &[2.2]), vec![0, 2, 4, 5, 7, 9]);
    }

    #[test]
    fn midway_pin_goes_to_lower_x() {
        let (x, y) = example();
        // Indices 2 and 3 are not extremes; 2.5 is midway.
        assert_eq!(idx(&x, &y, 2, &[2.5]), vec![0, 2, 4, 5, 7, 9]);
    }

    #[test]
    fn pin_on_repeated_x_keeps_all_samples_at_that_x() {
        let x = [0.0, 1.0, 2.0, 3.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0];
        let y = [0.0, 1.0, 0.5, 0.4, 0.6, 0.5, 0.5, 0.5, 0.5, 1.0];
        let without = idx(&x, &y, 2, &[]);
        assert!(!without.contains(&3) && !without.contains(&4));
        let with = idx(&x, &y, 2, &[3.1]);
        assert!(with.contains(&3) && with.contains(&4));
    }

    #[test]
    fn out_of_range_nan_and_duplicate_pins_have_no_extra_effect() {
        let (x, y) = example();
        let base = idx(&x, &y, 2, &[]);
        assert_eq!(
            idx(
                &x,
                &y,
                2,
                &[-5.0, 100.0, f64::NAN, f64::INFINITY, f64::NEG_INFINITY]
            ),
            base
        );
        assert_eq!(idx(&x, &y, 2, &[2.2, 2.2, 2.0]), idx(&x, &y, 2, &[2.2]));
    }

    #[test]
    fn ties_keep_first_occurrence() {
        // One bucket containing all: y min 1 first at 2, max 3 first at 4.
        let x: Vec<f64> = (0..7).map(f64::from).collect();
        let y = [2.0, 2.0, 1.0, 1.0, 3.0, 3.0, 2.0];
        assert_eq!(idx(&x, &y, 1, &[]), vec![0, 2, 4, 6]);
    }

    #[test]
    fn nan_is_never_an_extreme() {
        let x: Vec<f64> = (0..6).map(f64::from).collect();
        let y = [1.5, f64::NAN, 2.0, 1.0, f64::NAN, 1.7];
        assert_eq!(idx(&x, &y, 1, &[]), vec![0, 2, 3, 5]);
        // An all-NaN interior keeps only the endpoints.
        let y = [0.5, f64::NAN, f64::NAN, f64::NAN, f64::NAN, 0.7];
        assert_eq!(idx(&x, &y, 1, &[]), vec![0, 5]);
        // NaN endpoints are still kept.
        let y = [f64::NAN, 1.0, 2.0, 3.0, 4.0, f64::NAN];
        assert_eq!(idx(&x, &y, 1, &[]), vec![0, 1, 4, 5]);
    }

    #[test]
    fn endpoints_kept_when_not_extremes() {
        let x: Vec<f64> = (0..8).map(f64::from).collect();
        let y = [5.0, 0.0, 10.0, 5.0, 5.0, 0.0, 10.0, 5.0];
        let d = idx(&x, &y, 2, &[]);
        assert_eq!(d, vec![0, 1, 2, 5, 6, 7]);
    }

    #[test]
    fn empty_buckets_contribute_nothing() {
        // Samples clustered at both ends; middle buckets empty.
        let x = [0.0, 0.1, 0.2, 0.3, 9.7, 9.8, 9.9, 10.0];
        let y = [0.0, 3.0, 1.0, 2.0, 2.0, 1.0, 3.0, 0.0];
        let d = downsample_min_max(&x, &y, 3, &[]).unwrap();
        assert_eq!(d.indices, vec![0, 1, 6, 7]);
    }

    #[test]
    fn zero_span_puts_everything_in_one_bucket() {
        let x = [1.0; 6];
        let y = [3.0, 1.0, 4.0, 1.0, 5.0, 2.0];
        assert_eq!(idx(&x, &y, 2, &[]), vec![0, 1, 4, 5]);
        // A pin on a constant-x signal selects every sample.
        assert_eq!(idx(&x, &y, 2, &[1.0]), (0..6).collect::<Vec<_>>());
    }

    #[test]
    fn huge_extent_does_not_overflow() {
        let x = [-1e308, -1e300, 0.0, 1e300, 1e308];
        let y = [0.0, 1.0, -1.0, 2.0, 0.0];
        let d = downsample_min_max(&x, &y, 1, &[]).unwrap();
        assert_eq!(d.indices, vec![0, 2, 3, 4]);
        let d = downsample_min_max(&x, &y, 2, &[]).unwrap();
        assert!(d.indices.windows(2).all(|w| w[0] < w[1]));
    }

    #[test]
    fn small_signals_are_unchanged() {
        let x: Vec<f64> = (0..8).map(f64::from).collect();
        let y = [3.0, 1.0, 4.0, 1.0, 5.0, 9.0, 2.0, 6.0];
        let d = downsample_min_max(&x, &y, 4, &[100.0]).unwrap();
        assert_eq!(d.indices, (0..8).collect::<Vec<_>>());
        assert_eq!((d.x, d.y), (x.clone(), y.to_vec()));
        let e = downsample_min_max(&[], &[], 1, &[]).unwrap();
        assert!(e.indices.is_empty() && e.x.is_empty() && e.y.is_empty());
        let one = downsample_min_max(&[2.0], &[3.0], 1, &[]).unwrap();
        assert_eq!((one.indices, one.x, one.y), (vec![0], vec![2.0], vec![3.0]));
        // Huge bucket counts saturate rather than overflow.
        assert_eq!(idx(&x, &y, usize::MAX, &[]).len(), 8);
    }

    #[test]
    fn validation_errors() {
        assert_eq!(
            downsample_min_max(&[0.0, 1.0, 2.0], &[0.0, 1.0], 1, &[]),
            Err(DownsampleError::LengthMismatch { x_len: 3, y_len: 2 })
        );
        assert_eq!(
            downsample_min_max(&[0.0, 2.0, 1.0], &[0.0; 3], 1, &[]),
            Err(DownsampleError::NonMonotonic { index: 2 })
        );
        assert_eq!(
            downsample_min_max(&[0.0, f64::NAN], &[0.0; 2], 1, &[]),
            Err(DownsampleError::NonFiniteX { index: 1 })
        );
        assert_eq!(
            downsample_min_max(&[f64::INFINITY], &[0.0], 1, &[]),
            Err(DownsampleError::NonFiniteX { index: 0 })
        );
        assert_eq!(
            downsample_min_max(&[0.0], &[0.0], 0, &[]),
            Err(DownsampleError::ZeroBuckets)
        );
        // Equal consecutive x-values are allowed.
        assert!(downsample_min_max(&[0.0, 0.0, 1.0], &[0.0; 3], 1, &[]).is_ok());
        assert_eq!(
            DownsampleError::NonMonotonic { index: 2 }.to_string(),
            "non-monotonic x: x[2] < x[1]"
        );
        assert_eq!(
            DownsampleError::ZeroBuckets.to_string(),
            "buckets must be at least 1"
        );
        assert_eq!(
            DownsampleError::LengthMismatch { x_len: 3, y_len: 2 }.to_string(),
            "length mismatch: x has 3 values but y has 2"
        );
        assert_eq!(
            DownsampleError::NonFiniteX { index: 1 }.to_string(),
            "non-finite x-value at index 1"
        );
    }

    #[test]
    fn output_size_bound_and_values_match_indices() {
        // Deterministic pseudo-random, strongly non-uniform sampling.
        let n = 5000;
        let mut s: u64 = 0x2545_F491_4F6C_DD1D;
        let mut next = || {
            s ^= s << 13;
            s ^= s >> 7;
            s ^= s << 17;
            (s >> 11) as f64 / (1u64 << 53) as f64
        };
        let mut x = Vec::with_capacity(n);
        let mut acc = 0.0;
        for _ in 0..n {
            let r = next();
            acc += r * r * r;
            x.push(acc);
        }
        let y: Vec<f64> = (0..n).map(|_| next() - 0.5).collect();
        let pins: Vec<f64> = (0..35).map(|_| next() * acc).collect();
        for b in [1usize, 2, 7, 50, 333] {
            let d = downsample_min_max(&x, &y, b, &pins).unwrap();
            assert!(d.indices.len() <= (2 * b + 2 + pins.len()).min(n));
            assert!(d.indices.windows(2).all(|w| w[0] < w[1]));
            assert_eq!(d.indices.first(), Some(&0));
            assert_eq!(d.indices.last(), Some(&(n - 1)));
            for (k, &j) in d.indices.iter().enumerate() {
                assert_eq!(d.x[k], x[j]);
                assert_eq!(d.y[k], y[j]);
            }
            let unpinned = downsample_min_max(&x, &y, b, &[]).unwrap();
            assert!(unpinned.indices.len() <= 2 * b + 2);
        }
    }
}
