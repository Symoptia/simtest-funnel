# [1.0.0-beta.16](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.15...v1.0.0-beta.16) (2026-11-22)


### Features

* **core:** default to no x tolerance ([1f12013](https://github.com/Symoptia/simtest-funnel/commit/1f120135ccf22dd8e16ddc2548a0d08303247c4c))

# [1.0.0-beta.15](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.14...v1.0.0-beta.15) (2026-11-22)


### Features

* add cancellation and time limits for comparisons ([1b01256](https://github.com/Symoptia/simtest-funnel/commit/1b012560ca5ab439206234620b8468de165a51b9))

# [1.0.0-beta.14](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.13...v1.0.0-beta.14) (2026-11-22)


### Features

* **mcp:** downsample tube bounds and restrict plot output directories ([17fe592](https://github.com/Symoptia/simtest-funnel/commit/17fe5927748771e45439b510141c126ae603fd58))


### Performance Improvements

* **core:** edit tube curves through a gap buffer in remove_loop ([731fd5a](https://github.com/Symoptia/simtest-funnel/commit/731fd5a73c7ef0f06cb2f1002125ee298d003041))

# [1.0.0-beta.13](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.12...v1.0.0-beta.13) (2026-11-15)


### Bug Fixes

* **core:** judge coverage within the x-range and align API shapes ([ddfbcd6](https://github.com/Symoptia/simtest-funnel/commit/ddfbcd68a2e368e373dbef0fbe36645a2fcaf97b))
* **mcp:** harden CSV reading, bound output size and make snippets portable ([fb5b634](https://github.com/Symoptia/simtest-funnel/commit/fb5b6348d54b19c5c57e63da4e28d0c3b75f3f8a))


### Features

* **mcp:** add plot tool ([e6637a6](https://github.com/Symoptia/simtest-funnel/commit/e6637a6bce412c06425fa4a4717ce5055639a80f))

# [1.0.0-beta.12](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.11...v1.0.0-beta.12) (2026-11-15)


### Features

* **core:** add min/max signal downsampling ([da766eb](https://github.com/Symoptia/simtest-funnel/commit/da766ebf4d4134f67d623652f4a065ca52883abc))
* **core:** add violation summary and align default tolerances ([2a3f3d6](https://github.com/Symoptia/simtest-funnel/commit/2a3f3d676aa5bd357b8b8faf1d8701e12851f037))
* **mcp:** add local MCP server for funnel comparisons ([29064b6](https://github.com/Symoptia/simtest-funnel/commit/29064b62f0c0e7539dae1965c8dd33f73cdb91f1))

# [1.0.0-beta.11](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.10...v1.0.0-beta.11) (2026-11-15)


### Bug Fixes

* **deps:** upgrade pyo3 and numpy to 0.30 ([d8d72bc](https://github.com/Symoptia/simtest-funnel/commit/d8d72bcbf24000751f3895664084a651ddac4553))

# [1.0.0-beta.10](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.9...v1.0.0-beta.10) (2026-06-28)


### Features

* **demo:** add in-browser funnel comparison demo landing page ([797ba5d](https://github.com/Symoptia/simtest-funnel/commit/797ba5dbc08e109fa4f995a7bf529fe014d1c36b))

# [1.0.0-beta.9](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.8...v1.0.0-beta.9) (2026-06-28)


### Bug Fixes

* **ci:** use pnpm run docs to avoid npm builtin docs command ([d678d65](https://github.com/Symoptia/simtest-funnel/commit/d678d65f34868413df953ae77ac0325d88283de1))

# [1.0.0-beta.8](https://github.com/Symoptia/simtest-funnel/compare/v1.0.0-beta.7...v1.0.0-beta.8) (2026-06-28)


### Bug Fixes

* **ci:** install wasm-pack in publish-docs so typedoc build succeeds ([b4b7d67](https://github.com/Symoptia/simtest-funnel/commit/b4b7d670fcad9314d224d102a067a6f6845e4b7f))

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
