//! CSV + JSON I/O helpers used by the CLI and test harnesses.
//!
//! Available only with the `json` feature.

use std::fs::{create_dir_all, File};
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::Path;

use serde::{Deserialize, Serialize};

/// `param.json` schema matching the LBNL Funnel CLI test fixtures
/// (see `/home/iakovn/projects/funnel/tests/*/param.json`).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParamFile {
    /// Test CSV filename (relative to the param.json directory).
    pub test: String,
    /// Reference CSV filename (relative to the param.json directory).
    pub reference: String,
    /// Output directory (defaults to `results`).
    #[serde(default = "default_output")]
    pub output: String,
    /// Absolute x tolerance.
    #[serde(default)]
    pub atolx: f64,
    /// Absolute y tolerance.
    #[serde(default)]
    pub atoly: f64,
    /// Local x tolerance.
    #[serde(default)]
    pub ltolx: f64,
    /// Local y tolerance.
    #[serde(default)]
    pub ltoly: f64,
    /// Range-relative x tolerance.
    #[serde(default)]
    pub rtolx: f64,
    /// Range-relative y tolerance.
    #[serde(default)]
    pub rtoly: f64,
}

fn default_output() -> String {
    "results".to_string()
}

/// Read a `param.json` file.
pub fn read_params(path: &Path) -> Result<ParamFile, ParamError> {
    let text = std::fs::read_to_string(path).map_err(ParamError::Io)?;
    let p: ParamFile = serde_json::from_str(&text).map_err(ParamError::Json)?;
    Ok(p)
}

/// Error type for `param.json` parsing.
#[derive(Debug)]
pub enum ParamError {
    /// I/O error while reading the file.
    Io(std::io::Error),
    /// JSON parse error.
    Json(serde_json::Error),
}

impl std::fmt::Display for ParamError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ParamError::Io(e) => write!(f, "io error: {e}"),
            ParamError::Json(e) => write!(f, "json error: {e}"),
        }
    }
}

impl std::error::Error for ParamError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            ParamError::Io(e) => Some(e),
            ParamError::Json(e) => Some(e),
        }
    }
}

/// Read a two-column CSV (optional `x,y` header). Returns
/// `(x_values, y_values)`. Blank lines are skipped; a `#` at column 0
/// marks a comment.
pub fn read_xy_csv(path: &Path) -> std::io::Result<(Vec<f64>, Vec<f64>)> {
    let f = File::open(path)?;
    let mut rdr = BufReader::new(f);
    let mut line = String::new();
    let mut x = Vec::new();
    let mut y = Vec::new();
    let mut first_data_line = true;
    loop {
        line.clear();
        let n = rdr.read_line(&mut line)?;
        if n == 0 {
            break;
        }
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let fields: Vec<&str> = trimmed.split(',').map(|s| s.trim()).collect();
        if fields.len() < 2 {
            return Err(std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("expected two-column CSV row, got: {trimmed}"),
            ));
        }
        // skip header row if first data line isn't numeric
        if first_data_line {
            first_data_line = false;
            if fields[0].parse::<f64>().is_err() {
                continue;
            }
        }
        let xv: f64 = fields[0].parse().map_err(|e| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("bad x value {:?}: {e}", fields[0]),
            )
        })?;
        let yv: f64 = fields[1].parse().map_err(|e| {
            std::io::Error::new(
                std::io::ErrorKind::InvalidData,
                format!("bad y value {:?}: {e}", fields[1]),
            )
        })?;
        x.push(xv);
        y.push(yv);
    }
    Ok((x, y))
}

/// Write a two-column CSV with the header `x,y` using `{:.16e}`.
pub fn write_xy_csv(path: &Path, x: &[f64], y: &[f64]) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        create_dir_all(parent)?;
    }
    let f = File::create(path)?;
    let mut w = BufWriter::new(f);
    writeln!(w, "x,y")?;
    for (xi, yi) in x.iter().zip(y.iter()) {
        writeln!(w, "{xi:.16e},{yi:.16e}")?;
    }
    w.flush()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn csv_round_trip() {
        let tmp = std::env::temp_dir().join("simtest_funnel_io_rt.csv");
        let x = vec![0.0, 1.5, 2.75];
        let y = vec![-1.0, 0.5, 3.0];
        write_xy_csv(&tmp, &x, &y).unwrap();
        let (xx, yy) = read_xy_csv(&tmp).unwrap();
        assert_eq!(xx, x);
        assert_eq!(yy, y);
    }
}
