use pyo3::prelude::*;
use simtest_funnel_core::compare;

#[pyfunction]
fn compare_py() -> bool {
    compare()
}

#[pymodule]
#[pyo3(name = "_simtest_funnel")]
fn init_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compare_py, m)?)?;
    Ok(())
}
