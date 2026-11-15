## Why

The beta site (`https://beta.simtest-funnel.pages.dev/`) currently `<meta refresh>`-redirects
straight into the Rust API docs (`simtest_funnel_core`). There is no page that
shows what the library actually *does*, and nothing that exercises the published
`@simtest-js/funnel` package in a browser. A live, interactive demo turns the
landing page into a self-explaining showcase of the funnel comparison algorithm
and dogfoods the real WASM + TypeScript SDK surface.

## What Changes

- Replace the redirect landing page (`docs/index.html`) with a **navigation hub**
  linking to the GitHub repository, the live demo (`/demo`), and the three API
  doc trees (Rust, Python, JS).
- Add a **browser demo** under `/demo`: a Vite app that loads two committed CSV
  files (`time,x,y,z`), splits each into three `(time, value)` signals, runs the
  WASM `compare()` once per signal, and renders three Plotly funnel plots.
- Commit two **pregenerated CSV fixtures** (`reference.csv`, `test.csv`) and a
  **Python test** that regenerates and asserts their contents (no free-standing
  generator script) so the data is reproducible and verified in CI.
- Wire the demo build into the `publish-docs` release job so its output is
  assembled into `target/doc/demo/` before `wrangler pages deploy`.
- Plotly is loaded from a **CDN** (kept out of the SDK; injected via the existing
  `PlotlyLike` interface).

The three demonstrated signals (validated by spike at `atolx = atoly = 0.1`):

| Signal | Reference | Test | Outcome |
| --- | --- | --- | --- |
| x | `sin(2πt)` | `sin(2πt) + 0.05·sin(30πt)` | PASS — small ripple inside tube |
| y | `cos(2πt)·sin(100t)` | `cos(2πt)·sin(150t)` | PASS — frequency-insensitive (fails at `atolx=0`) |
| z | `sin(4πt)` | `sin(5πt)` | FAIL — errors detected |

## Capabilities

### New Capabilities
- `wasm-demo-site`: The deployed documentation site's landing page and the
  interactive in-browser funnel comparison demo, including the committed CSV
  fixtures, signal-splitting preprocessing, per-signal comparison, Plotly
  rendering, and the demo's inclusion in the release deploy pipeline.

### Modified Capabilities
<!-- None — no existing spec capabilities change requirements. -->

## Impact

- **New**: `examples/web/` (Vite demo app), `docs/index.html` rewritten as a nav
  hub, committed `reference.csv` / `test.csv` fixtures, a Python regeneration
  test under `tests/python/`.
- **Modified**: `.github/workflows/release.yml` (`publish-docs` job runs
  `make build-sdk` then `make demo` before deploy), `pnpm-workspace.yaml`
  (add `examples/*`), the `Makefile` (explicit `build-sdk`, `demo`, `demo-serve`
  recipes with dependencies + demo in the Biome lint scope), and `README.md`
  (document the demo build/run workflow).
- **Dependencies**: Plotly via CDN (no new runtime dependency in `@simtest-js/funnel`);
  Vite/dev tooling added to the example package only.
- **Deploy**: Visible at `beta.simtest-funnel.pages.dev` after the next beta
  prerelease triggers `publish-docs` (no change to release gating).
- **No changes** to `simtest-funnel-core`, the Python bindings, or the published
  SDK API surface.
