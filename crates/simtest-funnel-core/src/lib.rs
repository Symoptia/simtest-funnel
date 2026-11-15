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
//! (`rtolx = rtoly = 2e-3`). Partially specified tolerances are expressed
//! with [`PartialTolerances`] and resolved per axis by
//! [`PartialTolerances::resolve`]; every front end uses that rule.
//!
//! See `scratch/02-base-algorithm.md` for the design plan.

#![warn(missing_docs)]

pub mod compare;
pub(crate) mod corners;
pub(crate) mod errors;
#[cfg(feature = "json")]
pub mod io;
pub mod options;
pub mod status;
pub mod summary;
pub(crate) mod tube;

pub use compare::{compare, compare_into, estimate_capacities, Capacities, CompareResult, Outputs};
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
