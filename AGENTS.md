# AGENTS.md — simtest-funnel

## Project Overview

**simtest-funnel** is a trajectory comparison library that replicates the
[LBNL Funnel](https://github.com/lbl-srg/funnel) algorithm. The core logic
lives in Rust and is exposed to consumers through two binding layers:

- **Python** — via PyO3 / maturin as namespace package `simtest.funnel`
- **JavaScript / WASM** — via wasm-bindgen, published as `@simtest-js/funnel`

Repository: <https://github.com/Symoptia/simtest-funnel>

---

## Repo Map

```
simtest-funnel/
├── crates/
│   ├── simtest-funnel-core/       # Pure Rust library (crates.io)
│   ├── simtest-funnel-python/     # PyO3 bindings → simtest.funnel
│   └── simtest-funnel-wasm/       # wasm-bindgen bindings
├── packages/
│   └── sdk/                       # TypeScript wrapper → @simtest-js/funnel
├── tests/
│   └── python/                    # pytest integration tests
├── scripts/                       # Helper scripts (secrets, setup)
├── scratch/                       # Plans and working documents
├── .github/                       # CI workflows, Dependabot, copilot-instructions
├── Cargo.toml                     # Workspace root
├── pyproject.toml                 # Python project config (uv / maturin)
├── package.json                   # pnpm workspace root
├── Makefile                       # All dev commands
├── lefthook.yml                   # Git hooks (pre-commit, commit-msg)
├── LICENSE                        # MIT — 2026 Symoptia AB
├── CLA.md                         # Contributor License Agreement
└── CHANGELOG.md                   # Keep-a-Changelog format
```

---

## Quick Start

```bash
git clone https://github.com/Symoptia/simtest-funnel.git
cd simtest-funnel
devcontainer build --workspace-folder .
devcontainer exec --workspace-folder . -- make test
```

Or, if you already have the toolchain locally:

```bash
make build
make test
```

---

## Key Commands

All targets are defined in the `Makefile`:

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

## Code Organisation

### Rust Core (`crates/simtest-funnel-core/`)

Pure Rust implementation of the Funnel algorithm. No FFI dependencies.
Published to crates.io as `simtest-funnel-core`.

### Python Bindings (`crates/simtest-funnel-python/`)

Uses **PyO3** + **maturin** to produce a native extension module
`_simtest_funnel`, re-exported through the namespace package
`simtest.funnel`. The Python package is published to PyPI as
`simtest-funnel`.

### WASM Bindings (`crates/simtest-funnel-wasm/`)

Uses **wasm-bindgen** to compile the core to WebAssembly. The generated
`.wasm` + JS glue is consumed by the TypeScript SDK.

### TypeScript SDK (`packages/sdk/`)

Thin wrapper around the WASM output. Published to npm as
`@simtest-js/funnel`. Uses **Biome** for linting/formatting and
**vitest** for testing.

---

## Per-Language Workflow

When adding a new function:

1. **Rust** — implement in `crates/simtest-funnel-core/src/lib.rs`,
   add unit tests.
2. **Python** — expose via `#[pyfunction]` in
   `crates/simtest-funnel-python/src/lib.rs`, re-export in
   `python/simtest/funnel/__init__.py`, add pytest tests.
3. **JavaScript** — expose via `#[wasm_bindgen]` in
   `crates/simtest-funnel-wasm/src/lib.rs`, re-export in
   `packages/sdk/src/index.ts`, add vitest tests.

---

## Coding Conventions

### Rust

- `cargo clippy -- -D warnings` must pass with zero warnings.
- `cargo fmt --all` for formatting.
- All public items must be documented.

### Python

- Type annotations required; target `mypy --strict` compliance.
- Use `uv` as the package manager.

### JavaScript / TypeScript

- `biome check` must pass (lint + format).
- No `any` types.

### General

- No secrets or credentials in source.
- Prefer small, focused commits.

---

## Agent Rules

- Agents MUST use the GitHub CLI (`gh`) as necessary and MUST NOT defer
  GitHub actions (creating issues, PRs, managing secrets, etc.) to
  interactive or manual steps.
- Agents MUST ensure all linters pass (`make lint`) after any code change
  before committing or considering a task complete.

---

## Conventional Commits

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/).
Enforced by a `lefthook` commit-msg hook. Common prefixes:

| Prefix | Use |
| --- | --- |
| `feat` | New feature |
| `fix` | Bug fix |
| `chore` | Maintenance, tooling, deps |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `ci` | CI/CD changes |
| `refactor` | Code restructuring (no behaviour change) |

Format: `type(scope): description` — e.g. `feat(core): add tolerance parameter`

---

## Testing

Three test suites run in CI:

| Suite | Command | Framework |
| --- | --- | --- |
| Rust | `cargo test --workspace` | built-in |
| Python | `uv run python -m pytest tests/python/ -v` | pytest |
| JavaScript | `cd packages/sdk && pnpm test` | vitest |

Run all at once with `make test`.

---

## Releasing

Releases are automated via **semantic-release** on the `main` and `beta`
branches:

- Merging to `main` triggers a stable release.
- Merging to `beta` triggers a pre-release.
- Version bumps, changelogs, Git tags, and package publishing are handled
  automatically based on Conventional Commit messages.

---

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `maturin develop` fails | Ensure you're inside the devcontainer or have `uv`, `maturin`, and the correct Python version installed. |
| `wasm-pack build` fails | Check that `wasm-pack` is installed and target `wasm32-unknown-unknown` is available (`rustup target add wasm32-unknown-unknown`). |
| Lefthook hooks not running | Run `lefthook install` in the repo root. |
| `make test-js` fails with missing WASM | Run `make build` first to generate the WASM artifacts. |
| Clippy warnings block CI | Fix all warnings locally with `make lint-rust` before pushing. |
| Secrets check fails | Copy `.env.example` to `.env` and fill in required values, or configure GitHub Secrets. |
