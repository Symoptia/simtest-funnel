//! Options, tolerances, and x-range for the Funnel comparison API.
//!
//! See plan `scratch/02-base-algorithm.md` §3.2.1 and §3.3.

/// Per-direction tolerance coefficients.
///
/// At each reference point `i` the effective half-width in each direction is:
///
/// ```text
/// half_x[i] = max(max(atolx, rtolx*range_x), ltolx*|t_ref[i]|).max(1e-10)
/// half_y[i] = max(max(atoly, rtoly*range_y), ltoly*|y_ref[i]|).max(1e-10)
/// ```
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Tolerances {
    /// Absolute tolerance in x.
    pub atolx: f64,
    /// Absolute tolerance in y.
    pub atoly: f64,
    /// Local tolerance factor (relative to `|t_ref[i]|`) in x.
    pub ltolx: f64,
    /// Local tolerance factor (relative to `|y_ref[i]|`) in y.
    pub ltoly: f64,
    /// Range-relative tolerance (relative to `range_x`) in x.
    pub rtolx: f64,
    /// Range-relative tolerance (relative to `range_y`) in y.
    pub rtoly: f64,
}

impl Default for Tolerances {
    fn default() -> Self {
        Self {
            atolx: 0.0,
            atoly: 0.0,
            ltolx: 0.0,
            ltoly: 0.0,
            rtolx: 0.0,
            rtoly: 0.0,
        }
    }
}

/// Half-open inclusive x-range used to clip the trajectories before
/// comparison. The default is `(-inf, +inf)` which selects the full
/// reference span.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Range {
    /// Low end of the range.
    pub lo: f64,
    /// High end of the range.
    pub hi: f64,
}

impl Default for Range {
    fn default() -> Self {
        Self {
            lo: f64::NEG_INFINITY,
            hi: f64::INFINITY,
        }
    }
}

/// Compare options.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Options {
    /// Tolerance coefficients; see [`Tolerances`].
    pub tolerances: Tolerances,
    /// X-range used to clip both trajectories before comparison.
    pub x_range: Range,
}

impl Options {
    /// Library default options. Matches csv-compare's `-t 0.002` default
    /// via `rtolx = rtoly = 2e-3`; all other coefficients are zero and
    /// `x_range` is `(-inf, +inf)`.
    pub fn default_options() -> Self {
        Self {
            tolerances: Tolerances {
                rtolx: 2e-3,
                rtoly: 2e-3,
                ..Tolerances::default()
            },
            x_range: Range::default(),
        }
    }
}

impl Default for Options {
    fn default() -> Self {
        Self::default_options()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_options_returns_2e_3_rtol() {
        let o = Options::default_options();
        assert_eq!(o.tolerances.rtolx, 2e-3);
        assert_eq!(o.tolerances.rtoly, 2e-3);
        assert_eq!(o.tolerances.atolx, 0.0);
        assert_eq!(o.tolerances.atoly, 0.0);
        assert_eq!(o.tolerances.ltolx, 0.0);
        assert_eq!(o.tolerances.ltoly, 0.0);
        assert_eq!(o.x_range.lo, f64::NEG_INFINITY);
        assert_eq!(o.x_range.hi, f64::INFINITY);
    }
}
