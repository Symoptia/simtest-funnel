/// Returns the version of the simtest-funnel-core crate.
pub fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

pub fn compare() -> bool {
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_compare() {
        assert!(compare());
    }

    #[test]
    fn test_version() {
        let v = version();
        assert!(!v.is_empty());
    }
}
