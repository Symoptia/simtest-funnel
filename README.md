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
