//! # simtest-funnel-python
//!
//! Python bindings for the simtest-funnel trajectory comparison library.
//!
//! This crate uses [PyO3](https://pyo3.rs/) to expose [`simtest_funnel_core`]
//! as the native extension module `_simtest_funnel`, re-exported through the
//! namespace package `simtest.funnel`.

use pyo3::prelude::*;
use simtest_funnel_core::{compare, version};

/// Compare two trajectories using the Funnel algorithm.
///
/// Delegates to [`simtest_funnel_core::compare`].
#[pyfunction]
fn compare_py() -> bool {
    compare()
}

/// Returns the version of the underlying `simtest-funnel-core` crate.
///
/// Delegates to [`simtest_funnel_core::version`].
#[pyfunction]
fn version_py() -> &'static str {
    version()
}

/// Python module initialisation for `_simtest_funnel`.
#[pymodule]
#[pyo3(name = "_simtest_funnel")]
fn init_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compare_py, m)?)?;
    m.add_function(wrap_pyfunction!(version_py, m)?)?;
    Ok(())
}
