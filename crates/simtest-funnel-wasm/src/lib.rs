use simtest_funnel_core::compare as core_compare;
use wasm_bindgen::prelude::*;

#[wasm_bindgen]
pub fn compare() -> bool {
    core_compare()
}
