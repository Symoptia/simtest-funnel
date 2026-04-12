use wasm_bindgen::prelude::*;
use simtest_funnel_core::compare as core_compare;

#[wasm_bindgen]
pub fn compare() -> bool {
    core_compare()
}
