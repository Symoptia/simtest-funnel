# [1.0.0-beta.7](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.6...v1.0.0-beta.7) (2026-06-28)


### Bug Fixes

* **sdk:** ship self-contained dist with wasm in npm package ([c99121b](https://github.com/Symoptia/simtest-funnel/commit/c99121b3a162e4e686710cad644ef9f09654cc2f))

# [1.0.0-beta.6](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.5...v1.0.0-beta.6) (2026-06-28)


### Bug Fixes

* **cli:** emit signed errors and document LBNL divergence ([97d0fdf](https://github.com/Symoptia/simtest-funnel/commit/97d0fdfea9d73c199c84cd08414a109add435f24))
* **core:** restore range-asymmetry status classification ([8d431bc](https://github.com/Symoptia/simtest-funnel/commit/8d431bc184ee14b9a104de277ecbaaf4de2ceda5))


### Features

* **python:** add py.typed, stubs, and column dtype validation ([5f8e3c6](https://github.com/Symoptia/simtest-funnel/commit/5f8e3c6a3e1f96dfbb0f5a18d2cdec710f90722a))

# Unreleased

### ⚠ BREAKING CHANGES

* **cli:** `errors.csv` now contains **signed** deviations (positive
  above the upper bound, negative below the lower bound) instead of
  magnitudes. To restore LBNL-Funnel parity, apply `abs()` to the `y`
  column in consumer scripts.

### Bug Fixes

* **core:** restore range-asymmetry `Status` classification so that
  `MissingReference` / `MissingTest` are reachable from `compare`
  (Plan 02 §3.3 step 7).
* **cli:** emit signed errors and document the LBNL `errors.csv`
  format divergence.

### Tests

* **core:** corpus parity harness now enforces the Plan 02 §7.2
  tolerance (`max(1e-12, 1e-9 × max(|a|,|b|))`) on the error arrays
  (worst observed drift `~2e-14`). Bound-array parity continues to
  use a documented looser envelope
  (`max(1e-8, 1e-6 × max(|a|,|b|))`) pending a corner-algorithm
  `equ`-threshold fix; see plan 02.1 §10 Q1 for the follow-up.

### Documentation

* **python:** ship `py.typed` marker and a `_simtest_funnel.pyi`
  stub so `mypy --strict` works out of the box against
  `simtest.funnel`. The `compare_dataframes` wrapper now rejects
  non-numeric time / signal columns with a clear `TypeError`.
* **site:** publish `pdoc`-generated Python and `typedoc`-generated
  TypeScript API references under `target/doc/python/` and
  `target/doc/js/` respectively, deployed alongside the Rust
  rustdoc site on every release.
* **readmes:** synchronise the top-level, core, CLI, Python and
  SDK READMEs with the shipped `Status` enum, signed-error
  semantics and default tolerances; add a single
  "Differences from LBNL Funnel" section in the top-level README
  cross-linked from each crate README.

# [1.0.0-beta.5](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.4...v1.0.0-beta.5) (2026-04-21)


### Features

* implement Funnel trajectory comparison algorithm ([540dca8](https://github.com/Symoptia/simtest-funnel/commit/540dca87777076dc2af43920a5409cbabd89da60)), closes [hi#level](https://github.com/hi/issues/level)

# [1.0.0-beta.4](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.3...v1.0.0-beta.4) (2026-04-19)


### Bug Fixes

* **docs:** add API documentation and index page for docs site ([8c2cba3](https://github.com/Symoptia/simtest-funnel/commit/8c2cba3c3c2e57f5dacaf7d42715b51a20aa06e9))

# [1.0.0-beta.3](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.2...v1.0.0-beta.3) (2026-04-19)


### Bug Fixes

* **ci:** wire semantic-release outputs to publish jobs ([8453a69](https://github.com/Symoptia/simtest-funnel/commit/8453a69ecf53dc2c68e509bc3147597b2f861dc1))

# [1.0.0-beta.2](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.1...v1.0.0-beta.2) (2026-04-19)


### Features

* **core:** add version() function across all bindings ([fb9351a](https://github.com/Symoptia/simtest-funnel/commit/fb9351aa4726634b5884dd88a1768f80a3aac739))

# 1.0.0-beta.1 (2026-04-19)


### Bug Fixes

* fixed python version minimal dependency ([d5af739](https://github.com/Symoptia/simtest-funnel/commit/d5af7399d276ffdadaef25178cf262b3780a0001))


### Features

* **core:** phase 1 — Rust workspace & core crate scaffold ([c52069b](https://github.com/Symoptia/simtest-funnel/commit/c52069b9ca69966eed4913e92f265c255159d027))
* **python:** phase 2 — Python bindings scaffold ([82f2f57](https://github.com/Symoptia/simtest-funnel/commit/82f2f5785dd489343568a36968b7b4f9cf1667a5))
* **wasm:** phase 3 — WASM/JavaScript scaffold ([179f77a](https://github.com/Symoptia/simtest-funnel/commit/179f77a1c2c7caf4be4eb7af7ed7e98c2343ebbf))

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]
