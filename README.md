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

const result = compare(tRef, yRef, tRef, yTest, {
  tolerances: { atoly: 0.05 },
});
console.log(result.status === Status.Pass ? "pass" : "fail");
```

### Rust

```rust
use simtest_funnel_core::{compare, Options, Status, Tolerances};

fn main() {
    let t_ref: Vec<f64> = (0..=100).map(|i| i as f64 / 100.0).collect();
    let y_ref: Vec<f64> = t_ref
        .iter()
        .map(|t| (2.0 * std::f64::consts::PI * t).sin())
        .collect();
    let y_test: Vec<f64> = y_ref.iter().map(|y| y + 0.01).collect();

    let opts = Options {
        tolerances: Tolerances { atoly: 0.05, ..Default::default() },
        ..Default::default()
    };
    let r = compare(&t_ref, &y_ref, &t_ref, &y_test, &opts);
    assert_eq!(r.status, Status::Pass);
}
```

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
  x-range. LBNL returns `0` in both cases. Validation errors use
  codes `10..14` (`NonMonotonic`, `LengthMismatch`, `EmptyRange`,
  `BufferTooSmall`, `InsufficientData`).
- **Non-zero CLI exit codes.** The CLI maps the `Status` enum onto
  distinct exit codes (`0/1/2/3/4/5`) so shells can distinguish
  "inside the funnel" from "range asymmetry" — see
  [`crates/simtest-funnel-cli/README.md`](crates/simtest-funnel-cli/README.md).
- **Default tolerance `rtolx = rtoly = 2e-3`.** Matches the
  `csv-compare` project; LBNL defaults to `0.0`. Pass the flags
  (or `--params`) explicitly when exact LBNL parity is required.

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
| `make test-python` | `pytest tests/python/` |
| `make test-js` | vitest (JavaScript/TypeScript) |
| `make docs-python` | Build the pdoc site under `target/doc/python` |
| `make docs-js` | Build the typedoc site under `target/doc/js` |
| `make lint` | Run all linters |
| `make lint-rust` | Clippy + `cargo fmt` check |
| `make lint-js` | Biome check (JavaScript/TypeScript) |
| `make fmt` | Auto-format all code |
| `make fmt-rust` | `cargo fmt --all` |
| `make fmt-js` | Biome format write |
| `make clean` | Remove all build artifacts |
| `make check-secrets` | Validate `.env` vars and GitHub Secrets |

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
# simtest-funnel

[![CI](https://github.com/Symoptia/simtest-funnel/actions/workflows/ci.yml/badge.svg)](https://github.com/Symoptia/simtest-funnel/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/simtest-funnel)](https://pypi.org/project/simtest-funnel/)
[![npm](https://img.shields.io/npm/v/@simtest-js/funnel)](https://www.npmjs.com/package/@simtest-js/funnel)
[![crates.io](https://img.shields.io/crates/v/simtest-funnel-core)](https://crates.io/crates/simtest-funnel-core)

A trajectory comparison library that replicates the
[LBNL Funnel](https://github.com/lbl-srg/funnel) algorithm.
Written in Rust with production-ready bindings for **Python** and
**JavaScript / WebAssembly**.

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
simtest-funnel-core = "0.1"
```

---

## Quick Start

### Python

```python
from simtest.funnel import compare

result = compare()
print(result)
```

### JavaScript / TypeScript

```ts
import { compare } from "@simtest-js/funnel";

const result = compare();
console.log(result);
```

### Rust

```rust
use simtest_funnel_core::compare;

fn main() {
    let result = compare();
    println!("{result}");
}
```

---

## Developer Commands

All common tasks are available through `make`:

| Target | Description |
| --- | --- |
| `make help` | Show all targets with descriptions |
| `make build` | Build Rust workspace + maturin develop + pnpm build |
| `make test` | Run all three language test suites |
| `make test-rust` | `cargo test --workspace` |
| `make test-python` | `pytest tests/python/` |
| `make test-js` | vitest (JavaScript/TypeScript) |
| `make lint` | Run all linters |
| `make lint-rust` | Clippy + `cargo fmt` check |
| `make lint-js` | Biome check (JavaScript/TypeScript) |
| `make fmt` | Auto-format all code |
| `make fmt-rust` | `cargo fmt --all` |
| `make fmt-js` | Biome format write |
| `make clean` | Remove all build artifacts |
| `make check-secrets` | Validate `.env` vars and GitHub Secrets |

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
