//! `simtest-funnel` CLI — drop-in replacement for the LBNL `funnel` CLI
//! with an additional `--params <file.json>` flag for loading all
//! arguments from a JSON file.

use std::path::{Path, PathBuf};
use std::process::ExitCode;

use anyhow::{Context, Result};
use clap::Parser;
use simtest_funnel_core::io::{read_params, read_xy_csv, write_xy_csv, ParamFile};
use simtest_funnel_core::{compare, status_message, Options, Range, Status, Tolerances};

/// Trajectory comparison CLI.
///
/// Resolution order for each tolerance / path field:
///   1. explicit CLI flag (including `0.0`)
///   2. value from `--params` file if provided
///   3. `Options::default_options()` default
#[derive(Debug, Parser)]
#[command(
    name = "simtest-funnel",
    version,
    about = "Trajectory funnel comparison CLI.",
    long_about = "Trajectory funnel comparison CLI.\n\n\
        Writes five CSV files into --output: reference.csv, test.csv, \
        lowerBound.csv, upperBound.csv, and errors.csv. For drop-in \
        compatibility with the LBNL Funnel C CLI, errors.csv contains \
        absolute values of the signed deviations that the Rust API \
        otherwise returns."
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
    let resolve_f = |cli: Option<f64>, from_params: Option<f64>, default: f64| -> f64 {
        cli.unwrap_or_else(|| from_params.unwrap_or(default))
    };

    let def = Options::default_options().tolerances;
    let reference = resolve_path(
        args.reference,
        params.as_ref().map(|p| p.reference.as_str()),
    )
    .ok_or_else(|| anyhow::anyhow!("missing --reference (or params.reference)"))?;
    let test = resolve_path(args.test, params.as_ref().map(|p| p.test.as_str()))
        .ok_or_else(|| anyhow::anyhow!("missing --test (or params.test)"))?;
    let output = resolve_path(args.output, params.as_ref().map(|p| p.output.as_str()))
        .unwrap_or_else(|| PathBuf::from("results"));

    let tolerances = Tolerances {
        atolx: resolve_f(args.atolx, params.as_ref().map(|p| p.atolx), def.atolx),
        atoly: resolve_f(args.atoly, params.as_ref().map(|p| p.atoly), def.atoly),
        ltolx: resolve_f(args.ltolx, params.as_ref().map(|p| p.ltolx), def.ltolx),
        ltoly: resolve_f(args.ltoly, params.as_ref().map(|p| p.ltoly), def.ltoly),
        rtolx: resolve_f(args.rtolx, params.as_ref().map(|p| p.rtolx), def.rtolx),
        rtoly: resolve_f(args.rtoly, params.as_ref().map(|p| p.rtoly), def.rtoly),
    };
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
    let args = Args::parse();
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
    // C reference emits magnitudes; replicate that on disk for drop-in
    // compatibility.
    let errors_mag: Vec<f64> = result.errors.1.iter().map(|v| v.abs()).collect();
    write_xy_csv(&r.output.join("errors.csv"), &result.errors.0, &errors_mag)?;

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
