//! # simtest-funnel-core
//!
//! Core trajectory comparison library that replicates the
//! [LBNL Funnel](https://github.com/lbl-srg/funnel) algorithm.
//!
//! This crate provides the pure-Rust implementation with no FFI
//! dependencies. It is re-exported through Python (via PyO3) and
//! JavaScript/WASM (via wasm-bindgen) binding layers.
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
pub(crate) mod tube;

pub use compare::{compare, compare_into, estimate_capacities, Capacities, CompareResult, Outputs};
pub use options::{Options, Range, Tolerances};
pub use status::{message as status_message, Status};

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
