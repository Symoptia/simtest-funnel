//! # simtest-funnel-core
//!
//! Core trajectory comparison library that replicates the
//! [LBNL Funnel](https://github.com/lbl-srg/funnel) algorithm.
//!
//! This crate provides the pure-Rust implementation with no FFI dependencies.
//! It is re-exported through Python (via PyO3) and JavaScript/WASM (via wasm-bindgen)
//! binding layers.
//!
//! # Examples
//!
//! ```rust
//! let v = simtest_funnel_core::version();
//! assert!(!v.is_empty());
//!
//! let result = simtest_funnel_core::compare();
//! assert!(result);
//! ```

/// Returns the version of the `simtest-funnel-core` crate at compile time.
///
/// # Examples
///
/// ```rust
/// let v = simtest_funnel_core::version();
/// assert!(!v.is_empty());
/// ```
pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Compare two trajectories using the Funnel algorithm.
///
/// This is a placeholder that will accept reference and test trajectory data
/// and return whether they match within the configured tolerance.
///
/// # Returns
///
/// `true` if the trajectories match within tolerance, `false` otherwise.
///
/// # Examples
///
/// ```rust
/// let result = simtest_funnel_core::compare();
/// assert!(result);
/// ```
pub fn compare() -> bool {
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_compare() {
        assert!(compare());
    }

    #[test]
    fn test_version() {
        let v = version();
        assert!(!v.is_empty());
    }
}
