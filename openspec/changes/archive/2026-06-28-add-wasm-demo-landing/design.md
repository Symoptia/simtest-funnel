## Context

The deployed docs site is a static bundle assembled into `target/doc/` and
shipped to Cloudflare Pages by the `publish-docs` job in `release.yml` (gated on
a new semantic-release). Today `docs/index.html` is copied to
`target/doc/index.html` and only `<meta refresh>`-redirects into the Rust API
docs. The `@simtest-js/funnel` SDK exposes `compare()`, `defaultOptions()`,
`version()`, and `createFunnelPlot(plotly, el, …)` where Plotly is injected via a
minimal `PlotlyLike` interface. The SDK builds WASM with `wasm-pack --target
bundler`, which cannot be loaded directly from a plain `<script type=module>` —
it requires a bundler. The core `compare()` operates on a single
`(abscissa, value)` curve, so an x/y/z-over-time dataset maps to three
independent comparisons.

A numerical spike against the real library (1001 samples, `atolx = atoly = 0.1`)
confirmed the three demonstrated cases pass/fail as intended, and that the y case
passes *only* because of the non-zero horizontal tolerance (`atolx=0` → fail).

## Goals / Non-Goals

**Goals:**
- Turn the site root into a navigation hub (GitHub, `/demo`, API docs).
- Ship a self-contained, in-browser demo at `/demo` that dogfoods the published
  SDK surface (`compare` + `createFunnelPlot`) on real CSV data.
- Keep the demonstrated signals reproducible and CI-verified.
- Fit cleanly into the existing release deploy pipeline.

**Non-Goals:**
- No user CSV upload / drag-and-drop (data is pregenerated and committed).
- No changes to `simtest-funnel-core`, the Python bindings, or the SDK public API.
- No new runtime dependency in `@simtest-js/funnel` (Plotly stays external).
- No change to release gating (demo ships on the next prerelease/release).

## Decisions

**Demo as a bundled Vite app (Thread 1: option B).**
The demo lives in `examples/web/` (top-level) as a Vite app that imports
`@simtest-js/funnel` and builds to static assets copied into `target/doc/demo/`.
Chosen over a separate `--target web` WASM build (option A) or CDN-loading the
published package (option C) because it exercises the actual shipped package
surface and avoids maintaining a second WASM build flavor. Trade-off: adds a
build step to the docs pipeline.

The Vite config MUST use `vite-plugin-wasm` + `vite-plugin-top-level-await`
(same plugins the SDK already depends on) so the `--target bundler` WASM glue
resolves at build time.

**Workspace placement + SDK resolution (review blockers #2, #3).**
`pnpm-workspace.yaml` is extended from `["packages/*"]` to
`["packages/*", "examples/*"]` so `examples/web` is a workspace member that
resolves `@simtest-js/funnel` via `workspace:*` (the LOCAL SDK, not npm — keeps
the demo in lockstep with the source). Because `make docs-js` only builds the
WASM glue + typedoc (not the SDK `dist/`), the `publish-docs` job MUST build the
SDK `dist/` (`cd packages/sdk && pnpm install && pnpm build`) before building the
demo, otherwise the `@simtest-js/funnel` import is unresolved. Adding
`examples/*` to the workspace also brings the demo under `pnpm lint` (Biome) so
it satisfies the AGENTS.md linting requirement.

**CSV format + fixture verification (review major #5, #6).**
Both fixtures are comma-delimited with a header row `time,x,y,z` and 1001 rows
over `t ∈ [0, 1]` (`np.linspace(0, 1, 1001)`). The demo fetches them with
*relative* URLs (`./reference.csv`, `./test.csv`) so they resolve under `/demo/`.
The Python regeneration test lives at `tests/python/test_demo_fixtures.py`,
imports the signal formulas from a helper under `tests/python/tools/`, reloads
the committed CSVs with `np.loadtxt`, and asserts equality with `np.allclose`
(numeric, not byte-exact) to avoid float-formatting brittleness. It runs as part
of `make test-python` (and therefore CI).

**Plotly delivery + fallback (review major #7, minor #13, #14).**
Plotly is loaded from a pinned CDN URL (`https://cdn.plot.ly/plotly-3.6.0.min.js`,
the latest release at proposal time) and adapted to the SDK `PlotlyLike`
interface (`window.Plotly.newPlot` matches the `newPlot(el, data, layout, config)`
signature and still returns a `Promise` in 3.x). The three `createFunnelPlot`
calls run independently (one per signal) so one failure does not block the
others. If the Plotly script fails to load, the demo still renders each signal's
pass/fail status as text. A result is shown as PASS only when
`status === Status.Pass (0)`; any other status (Fail or an error code such as
LengthMismatch) is shown as a failure with its `status_message`.

**Explicit local dev recipes (decision 1).**
The `Makefile` gains explicit, dependency-ordered recipes so the demo is
buildable and runnable locally with the LOCAL workspace SDK:
- `build-sdk` — `cd packages/sdk && pnpm install && pnpm build` (wasm + dist).
- `demo` — depends on `build-sdk`; runs `cd examples/web && pnpm install &&
  pnpm build` and copies `dist/` into `target/doc/demo/`.
- `demo-serve` — depends on `build-sdk`; runs the Vite dev server for local
  preview.
- `lint-js` extended to also lint `examples/web`.
These recipes and the demo workflow are documented in the README so contributors
can reproduce the build. `publish-docs` reuses the same `build-sdk` + `demo`
ordering rather than ad-hoc inline steps.

**Plotly via CDN, injected through `PlotlyLike` (Thread 2 + decision 2).**
Plotly is loaded from a CDN `<script>` and passed into `createFunnelPlot`, keeping
it out of `@simtest-js/funnel` (which stays Plotly-agnostic) and off the bundle
size budget. Trade-off: relies on an external CDN at view time.

**Pregenerated, committed CSVs verified by a Python test (decision 1).**
Two CSV files (`reference.csv`, `test.csv`) with columns `time,x,y,z` are
committed as demo assets. Instead of a free-standing generator script, a test in
`tests/python/` regenerates the signals and asserts the committed files match, so
the fixtures are reproducible and protected against drift. The demo splits each
file into three `(time, value)` pairs at load time and runs three comparisons.

**Demo at `/demo`; root is a nav hub (decision 3).**
The demo is served from `/demo`, and `docs/index.html` becomes a lightweight nav
hub pointing to the GitHub repo, `/demo`, and the Rust/Python/JS API doc trees.
The existing API references are preserved and remain linked.

**Full-resolution signals (decision 4).**
Signals use 1001 samples over `t ∈ [0, 1]`; plots render at full resolution
(plot 2's ~24 oscillations are dense but faithful).

**Demonstrated signals and tolerances (Thread 3, spike-validated):**

| Signal | Reference | Test | `atolx=atoly=0.1` |
| --- | --- | --- | --- |
| x | `sin(2πt)` | `sin(2πt) + 0.05·sin(30πt)` | PASS (0 errors) |
| y | `cos(2πt)·sin(100t)` | `cos(2πt)·sin(150t)` | PASS (fails at `atolx=0`) |
| z | `sin(4πt)` | `sin(5πt)` | FAIL (338/1001 pts out, max err 1.13) |

## Risks / Trade-offs

- **Bundler-target WASM in a plain page** → Resolved by building the demo with
  Vite (option B) rather than hand-written HTML importing the SDK directly.
- **CDN Plotly unavailable at view time** → Pin a specific Plotly version URL
  (`plotly-3.6.0`); the demo degrades to showing computed pass/fail status even
  if the chart fails to load.
- **Docs pipeline gains a build step** → Keep the example build isolated to
  `examples/web/` and assemble its `dist/` into `target/doc/demo/`; failure is
  contained to the demo, not the API docs.
- **`.wasm` MIME type on Cloudflare Pages** → Cloudflare Pages serves `.wasm`
  as `application/wasm` by default and `vite-plugin-wasm` may inline small
  modules, but as cheap insurance the demo ships a `_headers` file declaring
  `Content-Type: application/wasm` for `/demo/*.wasm`.
- **SDK not built in `publish-docs`** → The job explicitly builds the SDK
  `dist/` before the demo (see Decisions); otherwise the workspace import is
  unresolved.
- **Fixture drift** → The Python regeneration test fails CI if `reference.csv`
  or `test.csv` no longer match the documented formulas.
- **Demo only visible after a release** → Accepted (Thread 4); the beta branch
  alias updates on the next prerelease via the unchanged `publish-docs` gate.

## Migration Plan

1. Add `examples/web/` Vite app and commit the two CSV fixtures + Python
   regeneration test.
2. Rewrite `docs/index.html` as the nav hub.
3. Extend the `Makefile` / `publish-docs` job to build the demo into
   `target/doc/demo/` before `wrangler pages deploy`.
4. Merge to `beta`; the next prerelease deploys the demo to
   `beta.simtest-funnel.pages.dev`. Rollback = revert the landing page and
   pipeline changes (no published-package impact).

## Open Questions

- Whether to also link the Rust WASM bindings doc tree (`simtest_funnel_wasm/`)
  from the landing hub, or only the core. Default: link core only to keep the
  hub focused; revisit if useful.
