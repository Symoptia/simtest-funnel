# simtest-funnel

[![CI](https://github.com/Symoptia/simtest-funnel/actions/workflows/ci.yml/badge.svg)](https://github.com/Symoptia/simtest-funnel/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/simtest-funnel)](https://pypi.org/project/simtest-funnel/)
[![npm](https://img.shields.io/npm/v/@simtest-js/funnel)](https://www.npmjs.com/package/@simtest-js/funnel)
[![crates.io](https://img.shields.io/crates/v/simtest-funnel-core)](https://crates.io/crates/simtest-funnel-core)

A trajectory comparison library that replicates the
[LBNL Funnel](https://github.com/lbl-srg/funnel) algorithm.
Written in Rust with production-ready bindings for **Python** and
**JavaScript / WebAssembly**.

API references (published to Cloudflare Pages on each release):

- Rust core — `simtest_funnel_core/` (cargo doc)
- Python — `python/` (pdoc, `simtest.funnel`)
- JavaScript / TypeScript — `js/` (typedoc, `@simtest-js/funnel`)

---

## Installation

### Python

```bash
pip install simtest-funnel
```

### JavaScript / TypeScript

```bash
pnpm add @simtest-js/funnel
```

### Rust

Add the core crate to your `Cargo.toml`:

```toml
[dependencies]
simtest-funnel-core = "1"
```

---

## Quick Start

### Python

```python
import numpy as np
from simtest.funnel import Options, Tolerances, compare

t_ref = np.linspace(0.0, 1.0, 101)
y_ref = np.sin(2 * np.pi * t_ref)
t_test = t_ref
y_test = y_ref + 0.01

# Only a y tolerance: rtoly = 0; no x (time) tolerance unless given.
result = compare(
    t_ref, y_ref, t_test, y_test,
    Options(tolerances=Tolerances(atoly=0.05)),
)
print(result.status)  # 0 == Pass, -1 == Fail, 1/2 == MissingReference/Test
```

### JavaScript / TypeScript

```ts
import { compare, Status } from "@simtest-js/funnel";

const tRef = Float64Array.from({ length: 101 }, (_, i) => i / 100);
const yRef = tRef.map((t) => Math.sin(2 * Math.PI * t));
const yTest = yRef.map((y) => y + 0.01);

// Only a y tolerance: rtoly = 0; no x (time) tolerance unless given.
const result = compare(tRef, yRef, tRef, yTest, {
  tolerances: { atoly: 0.05 },
});
console.log(result.status === Status.Pass ? "pass" : "fail");
```

### Rust

```rust
use simtest_funnel_core::{compare, Options, PartialTolerances, Status};

fn main() {
    let t_ref: Vec<f64> = (0..=100).map(|i| i as f64 / 100.0).collect();
    let y_ref: Vec<f64> = t_ref
        .iter()
        .map(|t| (2.0 * std::f64::consts::PI * t).sin())
        .collect();
    let y_test: Vec<f64> = y_ref.iter().map(|y| y + 0.01).collect();

    // Only a y tolerance: rtoly = ltoly = 0; no x (time) tolerance unless given.
    let opts = Options {
        tolerances: PartialTolerances { atoly: Some(0.05), ..Default::default() }.resolve(),
        ..Default::default()
    };
    let r = compare(&t_ref, &y_ref, &t_ref, &y_test, &opts);
    assert_eq!(r.status, Status::Pass);
}
```

### Time (x) tolerance

By default there is **no tolerance in x**: only the y axis has a default
(`rtoly = 2e-3`, 0.2 % of the reference value range). With zero x
tolerance the tube's x half-width is the `1e-10` floor, so each test
point is checked only against the y band around the reference at the
same x, and a test curve that is shifted or delayed in time fails at
steep edges and switching events even when the shift is tiny. Give
`atolx` (time units, e.g. `atolx = 0.5` for half a second) when such
shifts are acceptable. A range-relative `rtolx` grows with the length of
the record rather than with how fast the signal changes (with
`rtolx = 2e-3`, 15 days of data allow 43 minutes of shift, a year
17.5 hours), which is why there is no x default.

### Stopping a long comparison

Comparisons are fast (a million noisy samples in a fraction of a second),
but some inputs (nearly noise-free signals with a wide tube in x) grow
quadratically. Rust callers can use `compare_cancellable` with a
`CancelToken` (cancel from another thread and/or a deadline) or
`compare_with_check`; Python's `compare` releases the interpreter lock,
accepts `timeout=` and `cancel=` and is interrupted by Ctrl-C. See the
[core README](crates/simtest-funnel-core/README.md#cancellation) and the
[Python package README](crates/simtest-funnel-python/python/simtest/funnel/README.md#time-limits-cancellation-and-ctrl-c).
The TypeScript API has no cancellation yet.

---

## Differences from LBNL Funnel

`simtest-funnel` is behaviourally compatible with the LBNL Funnel
algorithm on the input side, but deliberately diverges on a few output
semantics. Scripts that consume the LBNL `funnel` output should be
aware of the following:

- **Signed errors.** The `errors` array from the library (and
  `errors.csv` from the CLI) contains **signed** deviations: positive
  when the test point lies above the upper bound, negative when it
  lies below the lower bound, zero inside the funnel. LBNL Funnel
  writes magnitudes. Apply `abs()` on the consumer side to restore
  parity.
- **Richer `Status` enum.** In addition to `Pass` (`0`) and `Fail`
  (`-1`), `simtest-funnel` reports `MissingReference` (`1`) and
  `MissingTest` (`2`) when one trajectory extends past the other's
  x-range. Coverage is judged within the requested `x_range`: both
  x-extents are clipped to it first, so restricting `x_range` to the
  overlap of the two trajectories (e.g. reference `0..1`, test `0..1.1`,
  `x_range = [0, 1]`) yields `Pass`/`Fail` instead. LBNL returns `0` in
  both cases. Validation errors use
  codes `10..14` (`NonMonotonic`, `LengthMismatch`, `EmptyRange`,
  `BufferTooSmall`, `InsufficientData`).
- **Non-zero CLI exit codes.** The CLI maps the `Status` enum onto
  distinct exit codes (`0/1/2/3/4/5`) so shells can distinguish
  "inside the funnel" from "range asymmetry" — see
  [`crates/simtest-funnel-cli/README.md`](crates/simtest-funnel-cli/README.md).
- **Default tolerance `rtoly = 2e-3`, no x tolerance, resolved per
  axis.** LBNL defaults every coefficient to `0.0`; simtest-funnel
  defaults only the y axis to `rtoly = 2e-3` (0.2 % of the reference
  value range). In every simtest-funnel API (Rust, Python, TypeScript,
  CLI) the coefficients you give are resolved per axis (x:
  `atolx`/`ltolx`/`rtolx`, y: `atoly`/`ltoly`/`rtoly`): an axis with no
  coefficient given gets its default (x: all zero; y: `rtoly = 2e-3`);
  an axis with at least one coefficient given uses zero for its other
  coefficients; an explicit `0` counts as given. For exact LBNL parity
  give at least one y coefficient (e.g. `atoly = 0`). This also applies
  to CLI `--params` files: they use the LBNL `param.json` keys, but a
  missing y tolerance key is resolved per axis instead of meaning `0`.

The core and CLI READMEs cross-link back to this section.

---

## Developer Commands

All common tasks are available through `make`:

| Target | Description |
| --- | --- |
| `make help` | Show all targets with descriptions |
| `make build` | Build Rust workspace + maturin develop + pnpm build |
| `make test` | Run all three language test suites |
| `make test-rust` | `cargo test --workspace` |
| `make test-python` | `pytest tests/python/` + `python/simtest-funnel-mcp/tests` |
| `make test-js` | vitest (JavaScript/TypeScript) |
| `make docs-python` | Build the pdoc site under `target/doc/python` |
| `make docs-js` | Build the typedoc site under `target/doc/js` |
| `make build-sdk` | Build the `@simtest-js/funnel` SDK (wasm glue + dist) |
| `make demo` | Build the browser demo into `target/doc/demo/` |
| `make demo-serve` | Run the demo dev server (Vite) for local preview |
| `make lint` | Run all linters |
| `make lint-rust` | Clippy + `cargo fmt` check |
| `make lint-js` | Biome check (JavaScript/TypeScript) |
| `make lint-python` | mypy --strict (`simtest-funnel-mcp`) |
| `make fmt` | Auto-format all code |
| `make fmt-rust` | `cargo fmt --all` |
| `make fmt-js` | Biome format write |
| `make clean` | Remove all build artifacts |
| `make check-secrets` | Validate `.env` vars and GitHub Secrets |

---

## MCP server for AI agents

[`python/simtest-funnel-mcp`](python/simtest-funnel-mcp) is a local
[MCP](https://modelcontextprotocol.io) server (stdio) with three tools,
`describe_signals(path)`, `compare_signals(reference_path, test_path=None, ...)` and
`plot_signals(reference_path, column, ...)`, that let agents such as
Claude Code or Claude Desktop run funnel comparisons on local CSV files with
explicit tolerances, without the samples entering the model's context.
`plot_signals` draws one comparison (reference, test, tube, violations), returns
a small PNG preview the model can look at, and optionally writes an SVG or PNG
file for documents; it is the only tool that writes, only the file it is
asked for, and only inside a workspace root declared by the client (Claude
Code) or an output directory configured with `--output-dir DIR` /
`SIMTEST_FUNNEL_MCP_OUTPUT_DIR` (needed for Claude Desktop).
Comparisons run off the server's event loop and are limited to `time_limit`
seconds per call (default 60); on timeout `compare_signals` returns the
finished columns and lists the rest as not completed. Reference and test may be
differently named columns of one file or two (`pairs`, `test_column`), files
may start with a preamble (`header_line`), and time columns may be ISO 8601
date-times (read as seconds since the epoch, x tolerances in seconds).

```bash
claude mcp add simtest-funnel -- uvx simtest-funnel-mcp      # once published to PyPI
claude mcp add simtest-funnel -- uv run --directory "$PWD" --quiet simtest-funnel-mcp  # from this checkout
```

This repository ships a [`.mcp.json`](.mcp.json) that starts the server from
the workspace with `uv run`. See the [package README](python/simtest-funnel-mcp/README.md)
for the tools, the tolerance coefficients, where plot files may be written,
and Claude Desktop configuration.

---

## Browser demo

An interactive in-browser demo lives in [`examples/web`](examples/web). It loads
two committed CSV fixtures (`time,x,y,z`), runs the funnel comparison via
WebAssembly (`@simtest-js/funnel`), and renders three Plotly funnel plots.

```bash
make demo-serve   # local dev server (Vite) at http://localhost:5173
make demo         # build into target/doc/demo/ (as deployed under /demo)
```

The demo resolves the **local** workspace SDK (`workspace:*`), so `make demo`
builds the SDK first (via `make build-sdk`). The fixtures are generated from the
formulas in [`tests/python/tools/demo_signals.py`](tests/python/tools/demo_signals.py)
and verified by `tests/python/test_demo_fixtures.py`.

---

## Conventional Commits

This repository enforces [Conventional Commits](https://www.conventionalcommits.org/).
A `lefthook` commit-msg hook validates every commit message. Common prefixes:

- `feat:` — new feature
- `fix:` — bug fix
- `chore:` — maintenance / tooling
- `docs:` — documentation only
- `test:` — adding or updating tests
- `ci:` — CI/CD changes

---

## License

[MIT](LICENSE) — Copyright 2026 Symoptia AB
