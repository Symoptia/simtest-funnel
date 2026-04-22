# simtest-funnel (CLI)

Command-line trajectory comparison tool based on the LBNL Funnel
algorithm. Drop-in compatible with the LBNL `funnel` CLI for input
flags; see **Differences from LBNL Funnel** below for behavioural
deltas on the output side.

Part of the [simtest-funnel](https://github.com/Symoptia/simtest-funnel)
workspace.

## Install

From a checkout of the workspace:

```bash
cargo install --path crates/simtest-funnel-cli
```

or run directly:

```bash
cargo run -p simtest-funnel-cli -- \
    --reference ref.csv --test test.csv --atoly 0.1
```

## Usage

All flags are optional if `--params <file.json>` is given. Resolution
order per field: (1) explicit CLI flag, (2) `--params` JSON value,
(3) built-in default.

```text
simtest-funnel --params cases/success1/param.json
```

Writes five CSV files into the output directory (default `results`):

- `reference.csv` — echoed reference `(x, y)`
- `test.csv` — echoed test `(x, y)`
- `lowerBound.csv` / `upperBound.csv` — funnel bounds
- `errors.csv` — signed deviations at each test x (see below)

## Exit codes

| Status               | Code |
|----------------------|------|
| `Pass`               | 0    |
| `Fail`               | 1    |
| `EmptyRange` / `InsufficientData` / `LengthMismatch` / `NonMonotonic` | 2 |
| `MissingReference`   | 3    |
| `MissingTest`        | 4    |
| internal / I/O error | 5    |

## Differences from LBNL Funnel

- **`errors.csv` contains signed deviations.** Positive values indicate
  the test point lies above the upper bound; negative values indicate
  it lies below the lower bound; zero indicates the point is inside the
  funnel. The LBNL `funnel` CLI writes magnitudes. To restore LBNL
  parity on the consumer side, apply `abs()` to the `y` column.
- **Non-zero exit codes for `MissingReference` / `MissingTest`.** The
  LBNL CLI returns `0` whenever the comparison completes without error;
  `simtest-funnel` reports range-asymmetry as separate exit codes (3
  and 4) so scripts can distinguish "inside funnel" from "one trajectory
  extends beyond the other".
- **Default tolerance.** The workspace default `rtolx = rtoly = 2e-3`
  matches the `csv-compare` project; the LBNL default is `0.0`. Pass
  the flags explicitly (or a `--params` file) when exact parity is
  required.
