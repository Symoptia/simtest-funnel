//! # simtest-funnel-wasm
//!
//! WebAssembly bindings for the simtest-funnel trajectory comparison library.
//!
//! This crate exposes the [`simtest_funnel_core`] API to JavaScript/TypeScript
//! consumers through [`wasm-bindgen`](https://rustwasm.github.io/wasm-bindgen/).
//! The generated `.wasm` + JS glue is consumed by the TypeScript SDK
//! (`@simtest-js/funnel`).

use simtest_funnel_core::compare as core_compare;
use simtest_funnel_core::version as core_version;
use wasm_bindgen::prelude::*;

/// Compare two trajectories using the Funnel algorithm (WASM binding).
///
/// Delegates to [`simtest_funnel_core::compare`].
///
/// # Returns
///
/// `true` if the trajectories match within tolerance, `false` otherwise.
#[wasm_bindgen]
pub fn compare() -> bool {
    core_compare()
}

/// Returns the version of the underlying `simtest-funnel-core` crate.
///
/// Delegates to [`simtest_funnel_core::version`].
#[wasm_bindgen]
pub fn version() -> String {
    core_version().to_string()
}
