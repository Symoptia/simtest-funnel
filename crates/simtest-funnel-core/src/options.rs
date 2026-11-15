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
///
/// A `Tolerances` value is always fully explicit and used verbatim.
/// It deliberately has no `Default` impl: use [`Tolerances::DEFAULT`]
/// (the library default), [`Tolerances::ZERO`] (explicit all-zero), or
/// [`PartialTolerances`] to give only some coefficients and have the
/// others filled by the per-axis rule.
#[derive(Debug, Clone, Copy, PartialEq)]
#[cfg_attr(feature = "json", derive(serde::Serialize))]
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

impl Tolerances {
    /// All six coefficients zero (the half-widths then fall back to the
    /// `1e-10` floor). This is how an explicit all-zero tolerance is
    /// spelled; it is *not* the library default.
    pub const ZERO: Tolerances = Tolerances {
        atolx: 0.0,
        atoly: 0.0,
        ltolx: 0.0,
        ltoly: 0.0,
        rtolx: 0.0,
        rtoly: 0.0,
    };

    /// Library default tolerances: `rtolx = rtoly = 2e-3` (0.2 % of the
    /// reference range on each axis, matching csv-compare's `-t 0.002`),
    /// all other coefficients zero. Equal to
    /// `PartialTolerances::default().resolve()`.
    pub const DEFAULT: Tolerances = Tolerances {
        atolx: 0.0,
        atoly: 0.0,
        ltolx: 0.0,
        ltoly: 0.0,
        rtolx: 2e-3,
        rtoly: 2e-3,
    };
}

/// Partially specified tolerances: each coefficient is either given
/// (`Some`, including `Some(0.0)`) or not given (`None`).
///
/// [`PartialTolerances::resolve`] turns them into effective
/// [`Tolerances`] with the per-axis rule used by every simtest-funnel
/// front end (Rust, Python, TypeScript, CLI):
///
/// - The x axis is `atolx`, `ltolx`, `rtolx`; the y axis is `atoly`,
///   `ltoly`, `rtoly`.
/// - If **no** coefficient of an axis is given, that axis gets the
///   default ([`Tolerances::DEFAULT`]: `rtol = 2e-3`, others zero).
/// - If **at least one** coefficient of an axis is given, the given
///   values are used and the other coefficients of that axis are zero.
/// - An explicit zero counts as given.
///
/// ```
/// use simtest_funnel_core::{PartialTolerances, Tolerances};
///
/// let t = PartialTolerances { atoly: Some(0.05), ..PartialTolerances::default() }.resolve();
/// // y given -> rtoly = 0; x not given -> rtolx = 2e-3.
/// assert_eq!(t, Tolerances { atoly: 0.05, rtolx: 2e-3, ..Tolerances::ZERO });
/// assert_eq!(PartialTolerances::default().resolve(), Tolerances::DEFAULT);
/// ```
///
/// With the `json` feature, absent keys and JSON `null` deserialize to
/// `None`.
#[derive(Debug, Clone, Copy, PartialEq, Default)]
#[cfg_attr(feature = "json", derive(serde::Serialize, serde::Deserialize))]
#[cfg_attr(feature = "json", serde(default))]
pub struct PartialTolerances {
    /// Absolute tolerance in x, if given.
    pub atolx: Option<f64>,
    /// Absolute tolerance in y, if given.
    pub atoly: Option<f64>,
    /// Local tolerance factor in x, if given.
    pub ltolx: Option<f64>,
    /// Local tolerance factor in y, if given.
    pub ltoly: Option<f64>,
    /// Range-relative tolerance in x, if given.
    pub rtolx: Option<f64>,
    /// Range-relative tolerance in y, if given.
    pub rtoly: Option<f64>,
}

/// Resolve one axis: `(atol, ltol, rtol)` given values plus the default
/// for that axis.
fn resolve_axis(
    atol: Option<f64>,
    ltol: Option<f64>,
    rtol: Option<f64>,
    default: (f64, f64, f64),
) -> (f64, f64, f64) {
    if atol.is_none() && ltol.is_none() && rtol.is_none() {
        default
    } else {
        (
            atol.unwrap_or(0.0),
            ltol.unwrap_or(0.0),
            rtol.unwrap_or(0.0),
        )
    }
}

impl PartialTolerances {
    /// Resolve into the six effective coefficients with the per-axis rule
    /// described on [`PartialTolerances`].
    pub fn resolve(&self) -> Tolerances {
        let d = Tolerances::DEFAULT;
        let (atolx, ltolx, rtolx) = resolve_axis(
            self.atolx,
            self.ltolx,
            self.rtolx,
            (d.atolx, d.ltolx, d.rtolx),
        );
        let (atoly, ltoly, rtoly) = resolve_axis(
            self.atoly,
            self.ltoly,
            self.rtoly,
            (d.atoly, d.ltoly, d.rtoly),
        );
        Tolerances {
            atolx,
            atoly,
            ltolx,
            ltoly,
            rtolx,
            rtoly,
        }
    }
}

impl From<Tolerances> for PartialTolerances {
    /// Every coefficient given; resolves back to exactly `t`.
    fn from(t: Tolerances) -> Self {
        Self {
            atolx: Some(t.atolx),
            atoly: Some(t.atoly),
            ltolx: Some(t.ltolx),
            ltoly: Some(t.ltoly),
            rtolx: Some(t.rtolx),
            rtoly: Some(t.rtoly),
        }
    }
}

/// Half-open inclusive x-range used to clip the trajectories before
/// comparison. The default is `(-inf, +inf)` which selects the full
/// reference span.
#[derive(Debug, Clone, Copy, PartialEq)]
#[cfg_attr(feature = "json", derive(serde::Serialize))]
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
///
/// `tolerances` holds the six *effective* coefficients and is used
/// verbatim. To apply the default / per-axis rule to partially specified
/// input, build it with [`PartialTolerances::resolve`].
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Options {
    /// Tolerance coefficients; see [`Tolerances`].
    pub tolerances: Tolerances,
    /// X-range used to clip both trajectories before comparison.
    pub x_range: Range,
}

impl Options {
    /// Library default options: [`Tolerances::DEFAULT`]
    /// (`rtolx = rtoly = 2e-3`, all other coefficients zero; matches
    /// csv-compare's `-t 0.002`) and `x_range = (-inf, +inf)`. Identical
    /// to options built from `PartialTolerances::default().resolve()`.
    pub fn default_options() -> Self {
        Self {
            tolerances: Tolerances::DEFAULT,
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

    fn p() -> PartialTolerances {
        PartialTolerances::default()
    }

    #[test]
    fn nothing_given_resolves_to_default() {
        assert_eq!(p().resolve(), Tolerances::DEFAULT);
        assert_eq!(Options::default().tolerances, p().resolve());
    }

    #[test]
    fn only_atoly_given_keeps_x_default() {
        let t = PartialTolerances {
            atoly: Some(0.05),
            ..p()
        }
        .resolve();
        assert_eq!(
            t,
            Tolerances {
                atolx: 0.0,
                atoly: 0.05,
                ltolx: 0.0,
                ltoly: 0.0,
                rtolx: 2e-3,
                rtoly: 0.0,
            }
        );
    }

    #[test]
    fn only_ltolx_given_keeps_y_default() {
        let t = PartialTolerances {
            ltolx: Some(0.01),
            ..p()
        }
        .resolve();
        assert_eq!(
            t,
            Tolerances {
                ltolx: 0.01,
                rtoly: 2e-3,
                ..Tolerances::ZERO
            }
        );
    }

    #[test]
    fn one_coefficient_per_axis() {
        let t = PartialTolerances {
            atolx: Some(0.1),
            atoly: Some(0.1),
            ..p()
        }
        .resolve();
        assert_eq!(
            t,
            Tolerances {
                atolx: 0.1,
                atoly: 0.1,
                ..Tolerances::ZERO
            }
        );
    }

    #[test]
    fn explicit_zero_counts_as_given() {
        let t = PartialTolerances {
            atolx: Some(0.0),
            atoly: Some(0.05),
            ..p()
        }
        .resolve();
        assert_eq!(
            t,
            Tolerances {
                atoly: 0.05,
                ..Tolerances::ZERO
            }
        );
        let all_zero = PartialTolerances::from(Tolerances::ZERO).resolve();
        assert_eq!(all_zero, Tolerances::ZERO);
    }

    #[test]
    fn fully_explicit_round_trips() {
        let t = Tolerances {
            atolx: 0.1,
            atoly: 0.2,
            ltolx: 0.3,
            ltoly: 0.4,
            rtolx: 0.5,
            rtoly: 0.6,
        };
        assert_eq!(PartialTolerances::from(t).resolve(), t);
    }

    /// Step-edge case shared with the Python, TypeScript and CLI tests:
    /// the test step is delayed by 0.001 in x, so it passes only when the
    /// x axis keeps a non-zero tolerance.
    fn step_edge_status(tol: Tolerances) -> crate::Status {
        let clip = |v: f64| v.clamp(0.0, 1.0);
        let t: Vec<f64> = (0..=100).map(|i| i as f64 / 100.0).collect();
        let y_ref: Vec<f64> = t.iter().map(|x| clip((x - 0.49) / 0.01)).collect();
        let y_test: Vec<f64> = t.iter().map(|x| clip((x - 0.491) / 0.01)).collect();
        let opts = Options {
            tolerances: tol,
            x_range: Range::default(),
        };
        crate::compare(&t, &y_ref, &t, &y_test, &opts).status
    }

    #[test]
    fn step_edge_verdicts_follow_resolution() {
        use crate::Status;
        let only_y = PartialTolerances {
            atoly: Some(0.05),
            ..p()
        };
        let y_and_zero_x = PartialTolerances {
            atolx: Some(0.0),
            ..only_y
        };
        assert_eq!(step_edge_status(only_y.resolve()), Status::Pass);
        assert_eq!(step_edge_status(y_and_zero_x.resolve()), Status::Fail);
        assert_eq!(step_edge_status(p().resolve()), Status::Pass);
    }

    #[cfg(feature = "json")]
    #[test]
    fn json_absent_and_null_are_not_given() {
        let t: PartialTolerances =
            serde_json::from_str(r#"{"atoly": 0.05, "atolx": null}"#).unwrap();
        assert_eq!(
            t,
            PartialTolerances {
                atoly: Some(0.05),
                ..p()
            }
        );
        let z: PartialTolerances = serde_json::from_str(r#"{"atolx": 0}"#).unwrap();
        assert_eq!(z.atolx, Some(0.0));
    }

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
