//! WebAssembly bindings for simtest-funnel.

use js_sys::Float64Array;
use serde::{Deserialize, Serialize};
use simtest_funnel_core::{
    compare as core_compare, summarize as core_summarize, version as core_version, CompareResult,
    Options, PartialTolerances, Range, Status, Tolerances,
};
use wasm_bindgen::prelude::*;

/// Tolerances as given by the caller: a missing, `undefined` or `null`
/// field is "not given"; any number (including `0`) is given.
#[derive(Debug, Deserialize, Default, Clone, Copy)]
#[serde(rename_all = "camelCase", default)]
struct JsTolerancesIn {
    atolx: Option<f64>,
    atoly: Option<f64>,
    ltolx: Option<f64>,
    ltoly: Option<f64>,
    rtolx: Option<f64>,
    rtoly: Option<f64>,
}

impl From<JsTolerancesIn> for PartialTolerances {
    fn from(t: JsTolerancesIn) -> Self {
        PartialTolerances {
            atolx: t.atolx,
            atoly: t.atoly,
            ltolx: t.ltolx,
            ltoly: t.ltoly,
            rtolx: t.rtolx,
            rtoly: t.rtoly,
        }
    }
}

/// The six resolved tolerance values, as returned to JS.
#[derive(Debug, Serialize, Clone, Copy)]
#[serde(rename_all = "camelCase")]
struct JsTolerances {
    atolx: f64,
    atoly: f64,
    ltolx: f64,
    ltoly: f64,
    rtolx: f64,
    rtoly: f64,
}

impl From<Tolerances> for JsTolerances {
    fn from(t: Tolerances) -> Self {
        JsTolerances {
            atolx: t.atolx,
            atoly: t.atoly,
            ltolx: t.ltolx,
            ltoly: t.ltoly,
            rtolx: t.rtolx,
            rtoly: t.rtoly,
        }
    }
}

#[derive(Debug, Serialize, Deserialize, Clone, Copy)]
#[serde(rename_all = "camelCase")]
struct JsRange {
    lo: f64,
    hi: f64,
}

impl Default for JsRange {
    fn default() -> Self {
        Self {
            lo: f64::NEG_INFINITY,
            hi: f64::INFINITY,
        }
    }
}

#[derive(Debug, Deserialize, Default, Clone, Copy)]
#[serde(rename_all = "camelCase")]
struct JsOptionsIn {
    #[serde(default)]
    tolerances: Option<JsTolerancesIn>,
    #[serde(default)]
    x_range: Option<JsRange>,
}

impl From<JsOptionsIn> for Options {
    /// Tolerances are resolved per axis by the core
    /// (`PartialTolerances::resolve`); absent tolerances mean defaults.
    fn from(o: JsOptionsIn) -> Self {
        Options {
            tolerances: PartialTolerances::from(o.tolerances.unwrap_or_default()).resolve(),
            x_range: o
                .x_range
                .map(|r| Range { lo: r.lo, hi: r.hi })
                .unwrap_or_default(),
        }
    }
}

/// Parse JS options; `undefined` / `null` means "no options" (defaults).
fn parse_options(options: JsValue) -> Result<Options, JsValue> {
    let o: JsOptionsIn = if options.is_undefined() || options.is_null() {
        JsOptionsIn::default()
    } else {
        serde_wasm_bindgen::from_value(options).map_err(|e| JsValue::from_str(&e.to_string()))?
    };
    Ok(o.into())
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct JsOptionsOut {
    tolerances: JsTolerances,
    x_range: JsRange,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct JsCompareResult {
    status: i32,
    lower_x: Vec<f64>,
    lower_y: Vec<f64>,
    upper_x: Vec<f64>,
    upper_y: Vec<f64>,
    errors_x: Vec<f64>,
    errors_y: Vec<f64>,
}

fn typed_array_to_vec(a: &Float64Array) -> Vec<f64> {
    let mut v = vec![0.0_f64; a.length() as usize];
    a.copy_to(&mut v);
    v
}

/// Compare `test` against `reference`.
#[wasm_bindgen]
pub fn compare(
    reference_x: &Float64Array,
    reference_y: &Float64Array,
    test_x: &Float64Array,
    test_y: &Float64Array,
    options: JsValue,
) -> Result<JsValue, JsValue> {
    let opts = parse_options(options)?;
    let rx = typed_array_to_vec(reference_x);
    let ry = typed_array_to_vec(reference_y);
    let tx = typed_array_to_vec(test_x);
    let ty = typed_array_to_vec(test_y);
    let r = core_compare(&rx, &ry, &tx, &ty, &opts);
    let out = JsCompareResult {
        status: r.status as i32,
        lower_x: r.lower.0,
        lower_y: r.lower.1,
        upper_x: r.upper.0,
        upper_y: r.upper.1,
        errors_x: r.errors.0,
        errors_y: r.errors.1,
    };
    serde_wasm_bindgen::to_value(&out).map_err(|e| JsValue::from_str(&e.to_string()))
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct JsViolationInterval {
    start_x: f64,
    end_x: f64,
    direction: &'static str,
    point_count: usize,
    worst_deviation: f64,
    worst_x: f64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct JsWorstDeviation {
    x: f64,
    deviation: f64,
    tube_half_width_y: f64,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct JsViolationSummary {
    status: i32,
    tolerances: JsTolerances,
    x_range: JsRange,
    compared_range: Option<JsRange>,
    intervals: Vec<JsViolationInterval>,
    worst: Option<JsWorstDeviation>,
    points_compared: usize,
    points_outside: usize,
    fraction_of_points_outside: Option<f64>,
    fraction_of_span_outside: Option<f64>,
}

fn status_from_code(code: i32) -> Result<Status, JsValue> {
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
        _ => return Err(JsValue::from_str(&format!("unknown status code: {code}"))),
    })
}

fn js_range(r: &Range) -> JsRange {
    JsRange { lo: r.lo, hi: r.hi }
}

/// Violation summary of an existing comparison. The result arrays are
/// marshalled back into a core `CompareResult`; the summary itself is
/// computed by the Rust core. Absent values are `null`.
#[wasm_bindgen]
#[allow(clippy::too_many_arguments)]
pub fn summarize(
    reference_x: &Float64Array,
    status: i32,
    lower_x: &Float64Array,
    lower_y: &Float64Array,
    upper_x: &Float64Array,
    upper_y: &Float64Array,
    errors_x: &Float64Array,
    errors_y: &Float64Array,
    options: JsValue,
) -> Result<JsValue, JsValue> {
    let opts = parse_options(options)?;
    let result = CompareResult {
        status: status_from_code(status)?,
        lower: (typed_array_to_vec(lower_x), typed_array_to_vec(lower_y)),
        upper: (typed_array_to_vec(upper_x), typed_array_to_vec(upper_y)),
        errors: (typed_array_to_vec(errors_x), typed_array_to_vec(errors_y)),
    };
    let s = core_summarize(&typed_array_to_vec(reference_x), &opts, &result);
    let out = JsViolationSummary {
        status: s.status as i32,
        tolerances: s.tolerances.into(),
        x_range: js_range(&s.x_range),
        compared_range: s.compared_range.as_ref().map(js_range),
        intervals: s
            .intervals
            .iter()
            .map(|iv| JsViolationInterval {
                start_x: iv.start_x,
                end_x: iv.end_x,
                direction: iv.direction.as_str(),
                point_count: iv.point_count,
                worst_deviation: iv.worst_deviation,
                worst_x: iv.worst_x,
            })
            .collect(),
        worst: s.worst.map(|w| JsWorstDeviation {
            x: w.x,
            deviation: w.deviation,
            tube_half_width_y: w.tube_half_width_y,
        }),
        points_compared: s.points_compared,
        points_outside: s.points_outside,
        fraction_of_points_outside: s.fraction_of_points_outside,
        fraction_of_span_outside: s.fraction_of_span_outside,
    };
    let ser = serde_wasm_bindgen::Serializer::new().serialize_missing_as_null(true);
    out.serialize(&ser)
        .map_err(|e| JsValue::from_str(&e.to_string()))
}

/// Returns the default options as a JS object with all six tolerance
/// values explicit (`Options::default_options()` from the core).
#[wasm_bindgen(js_name = defaultOptions)]
pub fn default_options() -> JsValue {
    let o = Options::default_options();
    let out = JsOptionsOut {
        tolerances: o.tolerances.into(),
        x_range: js_range(&o.x_range),
    };
    serde_wasm_bindgen::to_value(&out).unwrap_or(JsValue::NULL)
}

/// Returns the core crate version.
#[wasm_bindgen]
pub fn version() -> String {
    core_version().to_string()
}
