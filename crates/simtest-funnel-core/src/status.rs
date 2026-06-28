//! Status codes returned by the compare API.
//!
//! See plan `scratch/02-base-algorithm.md` §3.2.1.

/// Unified status returned by [`crate::compare()`] and [`crate::compare_into`].
#[repr(i32)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Status {
    /// All test points within the common x-range are inside the funnel.
    Pass = 0,
    /// At least one test point within the common x-range lies outside
    /// the lower/upper envelope.
    Fail = -1,
    /// Inside the common x-range the comparison passed, but the test
    /// trajectory extends beyond the reference x-range.
    MissingReference = 1,
    /// Inside the common x-range the comparison passed, but the
    /// reference trajectory extends beyond the test x-range.
    MissingTest = 2,
    /// Reference or test `x` array is not monotonically non-decreasing.
    NonMonotonic = 10,
    /// `x` and `y` arrays have different lengths for reference or test.
    LengthMismatch = 11,
    /// The `x_range` option does not intersect the reference or test
    /// data, or intersects only one of them.
    EmptyRange = 12,
    /// A caller-provided output buffer was too small.
    BufferTooSmall = 13,
    /// Reference or test trajectory has fewer than two points after
    /// the `x_range` filter.
    InsufficientData = 14,
}

/// Human-readable message for a status code. Stable across releases.
pub fn message(s: Status) -> &'static str {
    match s {
        Status::Pass => "pass: all test points inside the funnel",
        Status::Fail => "fail: test points outside the funnel",
        Status::MissingReference => "missing reference: test x-range extends past reference",
        Status::MissingTest => "missing test: reference x-range extends past test",
        Status::NonMonotonic => "non-monotonic x: reference or test x array is not non-decreasing",
        Status::LengthMismatch => "length mismatch: x and y arrays differ in length",
        Status::EmptyRange => "empty range: x_range does not intersect reference or test data",
        Status::BufferTooSmall => "buffer too small: caller-provided output buffer undersized",
        Status::InsufficientData => "insufficient data: fewer than two points after x_range filter",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const ALL: &[Status] = &[
        Status::Pass,
        Status::Fail,
        Status::MissingReference,
        Status::MissingTest,
        Status::NonMonotonic,
        Status::LengthMismatch,
        Status::EmptyRange,
        Status::BufferTooSmall,
        Status::InsufficientData,
    ];

    #[test]
    fn message_is_nonempty_for_every_variant() {
        for s in ALL {
            assert!(!message(*s).is_empty());
        }
    }

    #[test]
    fn repr_i32_matches_documented_codes() {
        assert_eq!(Status::Pass as i32, 0);
        assert_eq!(Status::Fail as i32, -1);
        assert_eq!(Status::MissingReference as i32, 1);
        assert_eq!(Status::MissingTest as i32, 2);
        assert_eq!(Status::NonMonotonic as i32, 10);
        assert_eq!(Status::LengthMismatch as i32, 11);
        assert_eq!(Status::EmptyRange as i32, 12);
        assert_eq!(Status::BufferTooSmall as i32, 13);
        assert_eq!(Status::InsufficientData as i32, 14);
    }

    #[test]
    fn display_roundtrip_via_message_fn() {
        // Ensure messages are distinct per variant.
        let mut seen = std::collections::HashSet::new();
        for s in ALL {
            let m = message(*s);
            assert!(seen.insert(m), "duplicate message for {:?}: {}", s, m);
        }
    }
}
