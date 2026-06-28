//! # simtest-funnel-python
//!
//! Python bindings for the simtest-funnel trajectory comparison library.
//!
//! Exposes `compare`, `default_options`, `status_message`, and the
//! `Status` integer constants through PyO3 as the native extension
//! module `_simtest_funnel`, re-exported through the namespace package
//! `simtest.funnel`.

use numpy::{IntoPyArray, PyReadonlyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};
use simtest_funnel_core::{
    compare as core_compare, status_message, Options, Range, Status, Tolerances,
};

fn dict_get_f64(d: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<f64>> {
    match d.get_item(key)? {
        Some(v) if !v.is_none() => Ok(Some(v.extract::<f64>()?)),
        _ => Ok(None),
    }
}

fn parse_tolerances(obj: &Bound<'_, PyAny>) -> PyResult<Tolerances> {
    let d: Bound<'_, PyDict> = obj.extract()?;
    let mut t = Tolerances::default();
    if let Some(v) = dict_get_f64(&d, "atolx")? {
        t.atolx = v;
    }
    if let Some(v) = dict_get_f64(&d, "atoly")? {
        t.atoly = v;
    }
    if let Some(v) = dict_get_f64(&d, "ltolx")? {
        t.ltolx = v;
    }
    if let Some(v) = dict_get_f64(&d, "ltoly")? {
        t.ltoly = v;
    }
    if let Some(v) = dict_get_f64(&d, "rtolx")? {
        t.rtolx = v;
    }
    if let Some(v) = dict_get_f64(&d, "rtoly")? {
        t.rtoly = v;
    }
    Ok(t)
}

fn parse_range(obj: &Bound<'_, PyAny>) -> PyResult<Range> {
    let d: Bound<'_, PyDict> = obj.extract()?;
    let mut r = Range::default();
    if let Some(v) = dict_get_f64(&d, "lo")? {
        r.lo = v;
    }
    if let Some(v) = dict_get_f64(&d, "hi")? {
        r.hi = v;
    }
    Ok(r)
}

fn parse_options(py_options: Option<&Bound<'_, PyAny>>) -> PyResult<Options> {
    let Some(obj) = py_options else {
        return Ok(Options::default_options());
    };
    if obj.is_none() {
        return Ok(Options::default_options());
    }
    let d: Bound<'_, PyDict> = obj
        .extract()
        .map_err(|_| PyValueError::new_err("options must be a dict or None"))?;
    let mut opts = Options::default_options();
    if let Some(t) = d.get_item("tolerances")? {
        if !t.is_none() {
            opts.tolerances = parse_tolerances(&t)?;
        }
    }
    if let Some(r) = d.get_item("x_range")? {
        if !r.is_none() {
            opts.x_range = parse_range(&r)?;
        }
    }
    Ok(opts)
}

#[pyfunction]
#[pyo3(signature = (t_reference, y_reference, t_test, y_test, options=None))]
fn compare<'py>(
    py: Python<'py>,
    t_reference: PyReadonlyArray1<'py, f64>,
    y_reference: PyReadonlyArray1<'py, f64>,
    t_test: PyReadonlyArray1<'py, f64>,
    y_test: PyReadonlyArray1<'py, f64>,
    options: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let opts = parse_options(options)?;
    let t_ref = t_reference.as_slice()?;
    let y_ref = y_reference.as_slice()?;
    let t_tst = t_test.as_slice()?;
    let y_tst = y_test.as_slice()?;

    let r = core_compare(t_ref, y_ref, t_tst, y_tst, &opts);

    let out = PyDict::new(py);
    out.set_item("status", r.status as i32)?;

    let lower_t = PyTuple::new(
        py,
        &[
            r.lower.0.into_pyarray(py).into_any(),
            r.lower.1.into_pyarray(py).into_any(),
        ],
    )?;
    let upper_t = PyTuple::new(
        py,
        &[
            r.upper.0.into_pyarray(py).into_any(),
            r.upper.1.into_pyarray(py).into_any(),
        ],
    )?;
    let errors_t = PyTuple::new(
        py,
        &[
            r.errors.0.into_pyarray(py).into_any(),
            r.errors.1.into_pyarray(py).into_any(),
        ],
    )?;
    out.set_item("lower", lower_t)?;
    out.set_item("upper", upper_t)?;
    out.set_item("errors", errors_t)?;
    Ok(out)
}

#[pyfunction]
fn default_options(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let o = Options::default_options();
    let tol = PyDict::new(py);
    tol.set_item("atolx", o.tolerances.atolx)?;
    tol.set_item("atoly", o.tolerances.atoly)?;
    tol.set_item("ltolx", o.tolerances.ltolx)?;
    tol.set_item("ltoly", o.tolerances.ltoly)?;
    tol.set_item("rtolx", o.tolerances.rtolx)?;
    tol.set_item("rtoly", o.tolerances.rtoly)?;
    let rng = PyDict::new(py);
    rng.set_item("lo", o.x_range.lo)?;
    rng.set_item("hi", o.x_range.hi)?;
    let d = PyDict::new(py);
    d.set_item("tolerances", tol)?;
    d.set_item("x_range", rng)?;
    Ok(d)
}

#[pyfunction]
fn status_message_py(code: i32) -> PyResult<&'static str> {
    let s = match code {
        0 => Status::Pass,
        -1 => Status::Fail,
        1 => Status::MissingReference,
        2 => Status::MissingTest,
        10 => Status::NonMonotonic,
        11 => Status::LengthMismatch,
        12 => Status::EmptyRange,
        13 => Status::BufferTooSmall,
        14 => Status::InsufficientData,
        _ => {
            return Err(PyValueError::new_err(format!(
                "unknown status code: {code}"
            )))
        }
    };
    Ok(status_message(s))
}

#[pyfunction]
fn version() -> &'static str {
    simtest_funnel_core::version()
}

#[pymodule]
#[pyo3(name = "_simtest_funnel")]
fn init_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compare, m)?)?;
    m.add_function(wrap_pyfunction!(default_options, m)?)?;
    m.add_function(wrap_pyfunction!(status_message_py, m)?)?;
    m.add_function(wrap_pyfunction!(version, m)?)?;

    m.add("STATUS_PASS", 0_i32)?;
    m.add("STATUS_FAIL", -1_i32)?;
    m.add("STATUS_MISSING_REFERENCE", 1_i32)?;
    m.add("STATUS_MISSING_TEST", 2_i32)?;
    m.add("STATUS_NON_MONOTONIC", 10_i32)?;
    m.add("STATUS_LENGTH_MISMATCH", 11_i32)?;
    m.add("STATUS_EMPTY_RANGE", 12_i32)?;
    m.add("STATUS_BUFFER_TOO_SMALL", 13_i32)?;
    m.add("STATUS_INSUFFICIENT_DATA", 14_i32)?;
    Ok(())
}
