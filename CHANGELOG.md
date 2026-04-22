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
