use simtest_funnel_core::compare as core_compare;
use simtest_funnel_core::version as core_version;
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub fn compare() -> bool {
    core_compare()
}

#[wasm_bindgen]
pub fn version() -> String {
    core_version().to_string()
}
