//! WebAssembly bindings for simtest-funnel.

use js_sys::Float64Array;
use serde::{Deserialize, Serialize};
use simtest_funnel_core::{
    compare as core_compare, version as core_version, Options, Range, Tolerances,
};
use wasm_bindgen::prelude::*;

#[derive(Debug, Serialize, Deserialize, Default, Clone, Copy)]
#[serde(rename_all = "camelCase")]
struct JsTolerances {
    #[serde(default)]
    atolx: f64,
    #[serde(default)]
    atoly: f64,
    #[serde(default)]
    ltolx: f64,
    #[serde(default)]
    ltoly: f64,
    #[serde(default)]
    rtolx: f64,
    #[serde(default)]
    rtoly: f64,
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

#[derive(Debug, Serialize, Deserialize, Default, Clone, Copy)]
#[serde(rename_all = "camelCase")]
struct JsOptions {
    #[serde(default)]
    tolerances: JsTolerances,
    #[serde(default)]
    x_range: JsRange,
}

impl From<JsOptions> for Options {
    fn from(o: JsOptions) -> Self {
        Options {
            tolerances: Tolerances {
                atolx: o.tolerances.atolx,
                atoly: o.tolerances.atoly,
                ltolx: o.tolerances.ltolx,
                ltoly: o.tolerances.ltoly,
                rtolx: o.tolerances.rtolx,
                rtoly: o.tolerances.rtoly,
            },
            x_range: Range {
                lo: o.x_range.lo,
                hi: o.x_range.hi,
            },
        }
    }
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
    let opts: JsOptions = if options.is_undefined() || options.is_null() {
        JsOptions::default()
    } else {
        serde_wasm_bindgen::from_value(options).map_err(|e| JsValue::from_str(&e.to_string()))?
    };
    let rx = typed_array_to_vec(reference_x);
    let ry = typed_array_to_vec(reference_y);
    let tx = typed_array_to_vec(test_x);
    let ty = typed_array_to_vec(test_y);
    let r = core_compare(&rx, &ry, &tx, &ty, &opts.into());
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

/// Returns default Options as a JS object.
#[wasm_bindgen(js_name = defaultOptions)]
pub fn default_options() -> JsValue {
    let o = JsOptions {
        tolerances: JsTolerances {
            rtolx: 2e-3,
            rtoly: 2e-3,
            ..Default::default()
        },
        x_range: JsRange::default(),
    };
    serde_wasm_bindgen::to_value(&o).unwrap_or(JsValue::NULL)
}

/// Returns the core crate version.
#[wasm_bindgen]
pub fn version() -> String {
    core_version().to_string()
}
