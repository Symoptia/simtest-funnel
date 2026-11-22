//! # simtest-funnel-core
//!
//! Core trajectory comparison library that replicates the
//! [LBNL Funnel](https://github.com/lbl-srg/funnel) algorithm.
//!
//! This crate provides the pure-Rust implementation with no FFI
//! dependencies. It is re-exported through Python (via PyO3) and
//! JavaScript/WASM (via wasm-bindgen) binding layers.
//!
//! Tolerances: [`Options::default()`] uses [`Tolerances::DEFAULT`]
//! (`rtoly = 2e-3`, no tolerance in x). Partially specified tolerances are expressed
//! with [`PartialTolerances`] and resolved per axis by
//! [`PartialTolerances::resolve`]; every front end uses that rule.
//!
//! Cancellation: [`compare()`] cannot be interrupted;
//! [`compare_cancellable`] (with a [`CancelToken`]: shared flag plus
//! optional deadline) and [`compare_with_check`] (caller-supplied check)
//! stop a running comparison and return `Err(`[`Cancelled`]`)`. See the
//! [`cancel`] module.
//!
//! Output downsampling for plots and reports (never applied to comparison
//! inputs) is provided by [`downsample_min_max`].
//!
//! See `scratch/02-base-algorithm.md` for the design plan.

#![warn(missing_docs)]

pub mod cancel;
pub mod compare;
pub(crate) mod corners;
pub mod downsample;
pub(crate) mod errors;
#[cfg(feature = "json")]
pub mod io;
pub mod options;
pub mod status;
pub mod summary;
pub(crate) mod tube;
pub(crate) mod window;

pub use cancel::{CancelToken, Cancelled};
pub use compare::{
    compare, compare_cancellable, compare_into, compare_with_check, estimate_capacities,
    Capacities, CompareResult, Outputs,
};
pub use downsample::{downsample_min_max, DownsampleError, Downsampled};
pub use options::{Options, PartialTolerances, Range, Tolerances};
pub use status::{message as status_message, Status};
pub use summary::{summarize, Direction, ViolationInterval, ViolationSummary, WorstDeviation};

/// Returns the version of the `simtest-funnel-core` crate at compile time.
pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_version() {
        let v = version();
        assert!(!v.is_empty());
    }
}
