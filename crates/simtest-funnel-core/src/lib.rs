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
}
