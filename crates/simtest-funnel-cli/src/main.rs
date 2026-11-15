//! `simtest-funnel` CLI — drop-in replacement for the LBNL `funnel` CLI
//! with an additional `--params <file.json>` flag for loading all
//! arguments from a JSON file.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use anyhow::{Context, Result};
use clap::Parser;
use simtest_funnel_core::io::{read_params, read_xy_csv, write_xy_csv, ParamFile};
use simtest_funnel_core::{
    compare, status_message, Options, PartialTolerances, Range, Status, Tolerances,
};

/// Trajectory comparison CLI.
///
/// Each path field is taken from its flag, else from the `--params`
/// file. Each tolerance coefficient is taken from its flag (including an
/// explicit `0`), else from the `--params` file if the key is present;
/// the coefficients given that way are then resolved per axis by
/// `PartialTolerances::resolve` (an axis with no coefficient given gets
/// the default `rtol = 2e-3`; an axis with at least one given has its
/// other coefficients set to zero).
#[derive(Debug, Parser)]
#[command(
    name = "simtest-funnel",
    version,
    about = "Trajectory funnel comparison CLI.",
    long_about = "Trajectory funnel comparison CLI.\n\n\
        Writes five CSV files into --output: reference.csv, test.csv, \
        lowerBound.csv, upperBound.csv, and errors.csv. See the crate \
        README 'Differences from LBNL Funnel' section — in particular \
        errors.csv contains *signed* deviations, not magnitudes.\n\n\
        Tolerances are resolved per axis (x: atolx/ltolx/rtolx, y: \
        atoly/ltoly/rtoly). Each coefficient comes from its flag, else \
        from --params. An axis with no coefficient given uses the \
        default rtol = 2e-3; an axis with at least one coefficient given \
        uses zero for its other coefficients. An explicit 0 counts as \
        given."
)]
struct Args {
    /// JSON file with compare parameters (same shape as
    /// `funnel/tests/*/param.json`).
    #[arg(long)]
    params: Option<PathBuf>,

    /// Reference CSV path.
    #[arg(long)]
    reference: Option<PathBuf>,

    /// Test CSV path.
    #[arg(long)]
    test: Option<PathBuf>,

    /// Output directory (default `results`).
    #[arg(long)]
    output: Option<PathBuf>,

    /// Absolute x-tolerance.
    #[arg(long)]
    atolx: Option<f64>,
    /// Absolute y-tolerance.
    #[arg(long)]
    atoly: Option<f64>,
    /// Local x-tolerance.
    #[arg(long)]
    ltolx: Option<f64>,
    /// Local y-tolerance.
    #[arg(long)]
    ltoly: Option<f64>,
    /// Range-relative x-tolerance.
    #[arg(long)]
    rtolx: Option<f64>,
    /// Range-relative y-tolerance.
    #[arg(long)]
    rtoly: Option<f64>,
}

struct Resolved {
    reference: PathBuf,
    test: PathBuf,
    output: PathBuf,
    tolerances: Tolerances,
}

fn resolve(args: Args) -> Result<Resolved> {
    let params: Option<ParamFile> = args
        .params
        .as_deref()
        .map(|p| read_params(p).with_context(|| format!("reading {}", p.display())))
        .transpose()?;
    let params_dir: Option<PathBuf> = args
        .params
        .as_deref()
        .and_then(|p| p.parent().map(Path::to_path_buf));

    let resolve_path = |cli: Option<PathBuf>, from_params: Option<&str>| -> Option<PathBuf> {
        if let Some(p) = cli {
            return Some(p);
        }
        if let Some(name) = from_params {
            if let Some(dir) = &params_dir {
                return Some(dir.join(name));
            }
            return Some(PathBuf::from(name));
        }
        None
    };
    let reference = resolve_path(
        args.reference,
        params.as_ref().map(|p| p.reference.as_str()),
    )
    .ok_or_else(|| anyhow::anyhow!("missing --reference (or params.reference)"))?;
    let test = resolve_path(args.test, params.as_ref().map(|p| p.test.as_str()))
        .ok_or_else(|| anyhow::anyhow!("missing --test (or params.test)"))?;
    let output = resolve_path(args.output, params.as_ref().map(|p| p.output.as_str()))
        .unwrap_or_else(|| PathBuf::from("results"));

    let from_file = params
        .as_ref()
        .map(ParamFile::tolerances)
        .unwrap_or_default();
    let tolerances = PartialTolerances {
        atolx: args.atolx.or(from_file.atolx),
        atoly: args.atoly.or(from_file.atoly),
        ltolx: args.ltolx.or(from_file.ltolx),
        ltoly: args.ltoly.or(from_file.ltoly),
        rtolx: args.rtolx.or(from_file.rtolx),
        rtoly: args.rtoly.or(from_file.rtoly),
    }
    .resolve();
    Ok(Resolved {
        reference,
        test,
        output,
        tolerances,
    })
}

fn status_label(s: Status) -> &'static str {
    match s {
        Status::Pass => "pass",
        Status::Fail => "fail",
        Status::MissingReference => "missing_reference",
        Status::MissingTest => "missing_test",
        Status::NonMonotonic => "non_monotonic",
        Status::LengthMismatch => "length_mismatch",
        Status::EmptyRange => "empty_range",
        Status::BufferTooSmall => "buffer_too_small",
        Status::InsufficientData => "insufficient_data",
    }
}

fn exit_code_for(s: Status) -> u8 {
    match s {
        Status::Pass => 0,
        Status::Fail => 1,
        Status::MissingReference => 3,
        Status::MissingTest => 4,
        Status::NonMonotonic
        | Status::LengthMismatch
        | Status::EmptyRange
        | Status::BufferTooSmall
        | Status::InsufficientData => 2,
    }
}

fn run() -> Result<(Status, PathBuf)> {
    run_args(Args::parse())
}

fn run_args(args: Args) -> Result<(Status, PathBuf)> {
    let r = resolve(args)?;
    let (t_ref, y_ref) =
        read_xy_csv(&r.reference).with_context(|| format!("reading {}", r.reference.display()))?;
    let (t_test, y_test) =
        read_xy_csv(&r.test).with_context(|| format!("reading {}", r.test.display()))?;

    let opts = Options {
        tolerances: r.tolerances,
        x_range: Range::default(),
    };
    let result = compare(&t_ref, &y_ref, &t_test, &y_test, &opts);

    // Always write the mirror CSVs (matches the C CLI behaviour).
    std::fs::create_dir_all(&r.output)?;
    write_xy_csv(&r.output.join("reference.csv"), &t_ref, &y_ref)?;
    write_xy_csv(&r.output.join("test.csv"), &t_test, &y_test)?;
    write_xy_csv(
        &r.output.join("lowerBound.csv"),
        &result.lower.0,
        &result.lower.1,
    )?;
    write_xy_csv(
        &r.output.join("upperBound.csv"),
        &result.upper.0,
        &result.upper.1,
    )?;
    // `errors.csv` contains signed deviations (positive above upper
    // bound, negative below lower bound). This differs from the LBNL
    // `funnel` CLI, which writes magnitudes. See the crate README
    // 'Differences from LBNL Funnel' section.
    write_xy_csv(
        &r.output.join("errors.csv"),
        &result.errors.0,
        &result.errors.1,
    )?;

    Ok((result.status, r.output))
}

fn main() -> ExitCode {
    match run() {
        Ok((s, _)) => {
            println!("status={}", status_label(s));
            if s != Status::Pass {
                eprintln!("{}", status_message(s));
            }
            ExitCode::from(exit_code_for(s))
        }
        Err(e) => {
            eprintln!("error: {e:#}");
            ExitCode::from(5)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn resolved_tolerances(argv: &[&str]) -> Tolerances {
        let mut full = vec!["simtest-funnel", "--reference", "r.csv", "--test", "t.csv"];
        full.extend_from_slice(argv);
        resolve(Args::try_parse_from(full).unwrap())
            .unwrap()
            .tolerances
    }

    fn write_params(name: &str, json: &str) -> PathBuf {
        let p = std::env::temp_dir().join(format!(
            "simtest_funnel_cli_{}_{name}.json",
            std::process::id()
        ));
        std::fs::write(&p, json).unwrap();
        p
    }

    /// Step-edge case shared with the Rust core, Python and TypeScript
    /// tests: the test step is delayed by 0.001 in x.
    fn step_edge_status(tolerance_flags: &[&str]) -> Status {
        let dir = std::env::temp_dir().join(format!(
            "simtest_funnel_cli_step_{}_{}",
            std::process::id(),
            tolerance_flags.join("_")
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let clip = |v: f64| v.clamp(0.0, 1.0);
        let t: Vec<f64> = (0..=100).map(|i| i as f64 / 100.0).collect();
        let y_ref: Vec<f64> = t.iter().map(|x| clip((x - 0.49) / 0.01)).collect();
        let y_test: Vec<f64> = t.iter().map(|x| clip((x - 0.491) / 0.01)).collect();
        write_xy_csv(&dir.join("r.csv"), &t, &y_ref).unwrap();
        write_xy_csv(&dir.join("t.csv"), &t, &y_test).unwrap();
        let (r, t, out) = (dir.join("r.csv"), dir.join("t.csv"), dir.join("out"));
        let mut argv = vec![
            "simtest-funnel",
            "--reference",
            r.to_str().unwrap(),
            "--test",
            t.to_str().unwrap(),
            "--output",
            out.to_str().unwrap(),
        ];
        argv.extend_from_slice(tolerance_flags);
        let (status, _) = run_args(Args::try_parse_from(argv).unwrap()).unwrap();
        std::fs::remove_dir_all(&dir).ok();
        status
    }

    #[test]
    fn step_edge_verdicts_follow_resolution() {
        assert_eq!(step_edge_status(&["--atoly", "0.05"]), Status::Pass);
        assert_eq!(
            step_edge_status(&["--atoly", "0.05", "--atolx", "0"]),
            Status::Fail
        );
        assert_eq!(step_edge_status(&[]), Status::Pass);
    }

    #[test]
    fn no_tolerance_given_uses_default() {
        assert_eq!(resolved_tolerances(&[]), Tolerances::DEFAULT);
    }

    #[test]
    fn flag_only_on_y_keeps_x_default() {
        assert_eq!(
            resolved_tolerances(&["--atoly", "0.05"]),
            Tolerances {
                atoly: 0.05,
                rtolx: 2e-3,
                ..Tolerances::ZERO
            }
        );
    }

    #[test]
    fn explicit_zero_flag_counts_as_given() {
        assert_eq!(
            resolved_tolerances(&["--atoly", "0.05", "--atolx", "0"]),
            Tolerances {
                atoly: 0.05,
                ..Tolerances::ZERO
            }
        );
    }

    #[test]
    fn params_without_tolerance_keys_uses_default() {
        let p = write_params("empty", r#"{"test": "t.csv", "reference": "r.csv"}"#);
        let t = resolved_tolerances(&["--params", p.to_str().unwrap()]);
        std::fs::remove_file(&p).ok();
        assert_eq!(t, Tolerances::DEFAULT);
    }

    #[test]
    fn flag_and_params_combined() {
        let p = write_params(
            "combined",
            r#"{"test": "t.csv", "reference": "r.csv", "atolx": 0.1, "atoly": 0.1}"#,
        );
        let t = resolved_tolerances(&["--params", p.to_str().unwrap(), "--rtoly", "0.01"]);
        std::fs::remove_file(&p).ok();
        assert_eq!(
            t,
            Tolerances {
                atolx: 0.1,
                atoly: 0.1,
                rtoly: 0.01,
                ..Tolerances::ZERO
            }
        );
    }
}
