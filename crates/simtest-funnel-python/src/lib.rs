use pyo3::prelude::*;
use simtest_funnel_core::{compare, version};

#[pyfunction]
fn compare_py() -> bool {
    compare()
}

#[pyfunction]
fn version_py() -> &'static str {
    version()
}

#[pymodule]
#[pyo3(name = "_simtest_funnel")]
fn init_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compare_py, m)?)?;
    m.add_function(wrap_pyfunction!(version_py, m)?)?;
    Ok(())
}
