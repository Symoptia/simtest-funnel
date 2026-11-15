//! # simtest-funnel-python
//!
//! Python bindings for the simtest-funnel trajectory comparison library.
//!
//! Exposes `compare`, `summarize`, `downsample_min_max`, `default_options`,
//! `status_message`, and the `Status` integer constants through PyO3 as the
//! native extension module `_simtest_funnel`, re-exported through the
//! namespace package `simtest.funnel`.

use numpy::{IntoPyArray, PyArray1, PyReadonlyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};
use simtest_funnel_core::{
    compare as core_compare, downsample_min_max as core_downsample_min_max, status_message,
    summarize as core_summarize, CompareResult, Options, PartialTolerances, Range, Status,
    Tolerances,
};

fn dict_get_f64(d: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<f64>> {
    match d.get_item(key)? {
        Some(v) if !v.is_none() => Ok(Some(v.extract::<f64>()?)),
        _ => Ok(None),
    }
}

/// Parse a tolerances dict into partially specified tolerances: a missing
/// key or `None` is "not given"; any number (including `0.0`) is given.
/// Resolution (per-axis defaults) happens in the Rust core.
fn parse_tolerances(obj: &Bound<'_, PyAny>) -> PyResult<PartialTolerances> {
    let d: Bound<'_, PyDict> = obj.extract()?;
    Ok(PartialTolerances {
        atolx: dict_get_f64(&d, "atolx")?,
        atoly: dict_get_f64(&d, "atoly")?,
        ltolx: dict_get_f64(&d, "ltolx")?,
        ltoly: dict_get_f64(&d, "ltoly")?,
        rtolx: dict_get_f64(&d, "rtolx")?,
        rtoly: dict_get_f64(&d, "rtoly")?,
    })
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

/// Parse the options dict. `None`, a missing `tolerances` key or
/// `tolerances=None` all mean "no coefficient given" and resolve to
/// `Options::default_options()` tolerances.
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
            opts.tolerances = parse_tolerances(&t)?.resolve();
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

/// Default options (resolved: six explicit tolerance values).
#[pyfunction]
fn default_options(py: Python<'_>) -> PyResult<Bound<'_, PyDict>> {
    let o = Options::default_options();
    let d = PyDict::new(py);
    d.set_item("tolerances", tolerances_dict(py, &o.tolerances)?)?;
    d.set_item("x_range", range_dict(py, &o.x_range)?)?;
    Ok(d)
}

fn status_from_code(code: i32) -> PyResult<Status> {
    Ok(match code {
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
    })
}

#[pyfunction]
fn status_message_py(code: i32) -> PyResult<&'static str> {
    Ok(status_message(status_from_code(code)?))
}

fn xy_to_vecs(
    x: PyReadonlyArray1<'_, f64>,
    y: PyReadonlyArray1<'_, f64>,
) -> PyResult<(Vec<f64>, Vec<f64>)> {
    Ok((x.as_slice()?.to_vec(), y.as_slice()?.to_vec()))
}

fn range_dict<'py>(py: Python<'py>, r: &Range) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("lo", r.lo)?;
    d.set_item("hi", r.hi)?;
    Ok(d)
}

fn tolerances_dict<'py>(py: Python<'py>, t: &Tolerances) -> PyResult<Bound<'py, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("atolx", t.atolx)?;
    d.set_item("atoly", t.atoly)?;
    d.set_item("ltolx", t.ltolx)?;
    d.set_item("ltoly", t.ltoly)?;
    d.set_item("rtolx", t.rtolx)?;
    d.set_item("rtoly", t.rtoly)?;
    Ok(d)
}

/// Violation summary of an existing comparison. Marshals the result
/// arrays back into a core `CompareResult` and returns the core summary as
/// a dict (absent values are `None`).
#[pyfunction]
#[pyo3(signature = (
    t_reference, status, lower_x, lower_y, upper_x, upper_y, errors_x, errors_y, options=None
))]
#[allow(clippy::too_many_arguments)]
fn summarize<'py>(
    py: Python<'py>,
    t_reference: PyReadonlyArray1<'py, f64>,
    status: i32,
    lower_x: PyReadonlyArray1<'py, f64>,
    lower_y: PyReadonlyArray1<'py, f64>,
    upper_x: PyReadonlyArray1<'py, f64>,
    upper_y: PyReadonlyArray1<'py, f64>,
    errors_x: PyReadonlyArray1<'py, f64>,
    errors_y: PyReadonlyArray1<'py, f64>,
    options: Option<&Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyDict>> {
    let opts = parse_options(options)?;
    let result = CompareResult {
        status: status_from_code(status)?,
        lower: xy_to_vecs(lower_x, lower_y)?,
        upper: xy_to_vecs(upper_x, upper_y)?,
        errors: xy_to_vecs(errors_x, errors_y)?,
    };
    let s = core_summarize(t_reference.as_slice()?, &opts, &result);

    let out = PyDict::new(py);
    out.set_item("status", s.status as i32)?;
    out.set_item("tolerances", tolerances_dict(py, &s.tolerances)?)?;
    out.set_item("x_range", range_dict(py, &s.x_range)?)?;
    match &s.compared_range {
        Some(r) => out.set_item("compared_range", range_dict(py, r)?)?,
        None => out.set_item("compared_range", py.None())?,
    }
    let intervals = PyList::empty(py);
    for iv in &s.intervals {
        let d = PyDict::new(py);
        d.set_item("start_x", iv.start_x)?;
        d.set_item("end_x", iv.end_x)?;
        d.set_item("direction", iv.direction.as_str())?;
        d.set_item("point_count", iv.point_count)?;
        d.set_item("worst_deviation", iv.worst_deviation)?;
        d.set_item("worst_x", iv.worst_x)?;
        intervals.append(d)?;
    }
    out.set_item("intervals", intervals)?;
    match &s.worst {
        Some(w) => {
            let d = PyDict::new(py);
            d.set_item("x", w.x)?;
            d.set_item("deviation", w.deviation)?;
            d.set_item("tube_half_width_y", w.tube_half_width_y)?;
            out.set_item("worst", d)?;
        }
        None => out.set_item("worst", py.None())?,
    }
    out.set_item("points_compared", s.points_compared)?;
    out.set_item("points_outside", s.points_outside)?;
    out.set_item("fraction_of_points_outside", s.fraction_of_points_outside)?;
    out.set_item("fraction_of_span_outside", s.fraction_of_span_outside)?;
    Ok(out)
}

/// `(indices, x, y)` arrays returned by [`downsample_min_max`].
type DownsampledArrays<'py> = (
    Bound<'py, PyArray1<usize>>,
    Bound<'py, PyArray1<f64>>,
    Bound<'py, PyArray1<f64>>,
);

/// Min/max-per-bucket downsampling of a signal, computed by the core.
/// Returns `(indices, x, y)` as numpy arrays. Invalid input (including
/// `buckets < 1`) raises `ValueError` with the core's error message.
#[pyfunction]
#[pyo3(signature = (x, y, buckets, pinned_x))]
fn downsample_min_max<'py>(
    py: Python<'py>,
    x: PyReadonlyArray1<'py, f64>,
    y: PyReadonlyArray1<'py, f64>,
    buckets: i64,
    pinned_x: PyReadonlyArray1<'py, f64>,
) -> PyResult<DownsampledArrays<'py>> {
    // Negative counts must not wrap; they get the core's zero-bucket error.
    let buckets = usize::try_from(buckets).unwrap_or(0);
    let d = core_downsample_min_max(x.as_slice()?, y.as_slice()?, buckets, pinned_x.as_slice()?)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok((
        d.indices.into_pyarray(py),
        d.x.into_pyarray(py),
        d.y.into_pyarray(py),
    ))
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
    m.add_function(wrap_pyfunction!(downsample_min_max, m)?)?;
    m.add_function(wrap_pyfunction!(status_message_py, m)?)?;
    m.add_function(wrap_pyfunction!(summarize, m)?)?;
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
