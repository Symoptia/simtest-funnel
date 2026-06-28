## 1. CSV fixtures + reproducibility test

- [ ] 1.1 Add a signal-formula helper under `tests/python/tools/` defining x/y/z reference and test signals over `t = np.linspace(0, 1, 1001)`
- [ ] 1.2 Generate and commit `examples/web/public/reference.csv` and `examples/web/public/test.csv` (comma-delimited, header `time,x,y,z`)
- [ ] 1.3 Add `tests/python/test_demo_fixtures.py` that imports the helper, reloads the committed CSVs with `np.loadtxt`, and asserts `np.allclose` (numeric, not byte-exact)
- [ ] 1.4 Run `make test-python` and confirm the new test passes

## 2. Demo app scaffold (examples/web/)

- [ ] 2.1 Scaffold a Vite app in `examples/web/` depending on `@simtest-js/funnel` via `workspace:*`
- [ ] 2.2 Update `pnpm-workspace.yaml` to `["packages/*", "examples/*"]` so the demo is a workspace member
- [ ] 2.3 Add `examples/web/vite.config.ts` using `vite-plugin-wasm` + `vite-plugin-top-level-await`
- [ ] 2.4 Add a pinned Plotly CDN `<script>` (`plotly-3.6.0.min.js`) and adapt `window.Plotly` to the SDK `PlotlyLike` interface
- [ ] 2.5 Add a `_headers` file in the demo output declaring `Content-Type: application/wasm` for `*.wasm` (insurance)
- [ ] 2.6 Verify the app builds to static assets (`pnpm build` in `examples/web`)

## 3. Demo logic

- [ ] 3.1 Fetch and parse both CSV files with relative URLs (`./reference.csv`, `./test.csv`)
- [ ] 3.2 Split each CSV into three `(time, value)` pairs (x, y, z) at full 1001-sample resolution
- [ ] 3.3 Run `compare()` per signal with `atolx = atoly = 0.1` and capture status + errors
- [ ] 3.4 Render three Plotly funnel plots via `createFunnelPlot` (independent calls; reference, test, tube bounds, errors)
- [ ] 3.5 Display each signal's status — PASS only when `status === Status.Pass`, otherwise show `status_message`; render status text even if Plotly fails to load
- [ ] 3.6 Manually verify in a browser: x PASS, y PASS, z FAIL

## 4. Landing page nav hub

- [ ] 4.1 Rewrite `docs/index.html` as a navigation hub (no `<meta refresh>`)
- [ ] 4.2 Add a GitHub repo link (absolute) plus relative links to `demo/`, `simtest_funnel_core/`, `python/`, and `js/`
- [ ] 4.3 Confirm all links resolve against the assembled `target/doc/` layout

## 5. Build + deploy pipeline

- [ ] 5.1 Add an explicit `make build-sdk` recipe (`cd packages/sdk && pnpm install && pnpm build`)
- [ ] 5.2 Add a `make demo` recipe that depends on `build-sdk`, builds `examples/web`, and copies its `dist/` into `target/doc/demo/`
- [ ] 5.3 Add a `make demo-serve` recipe (depends on `build-sdk`) that runs the Vite dev server for local preview
- [ ] 5.4 Extend `make lint-js` so the demo (`examples/web`) is linted by `make lint`
- [ ] 5.5 In `release.yml` `publish-docs`, run `make build-sdk` then `make demo` before `wrangler pages deploy`
- [ ] 5.6 Document the new recipes and the demo build/run workflow in the README
- [ ] 5.7 Verify locally that building docs produces `target/doc/index.html` (hub) and `target/doc/demo/` (demo) with API docs intact

## 6. Validation

- [ ] 6.1 Run `make lint` and `make test` (Rust, Python, JS) and fix any failures
- [ ] 6.2 Run `openspec validate add-wasm-demo-landing --strict`

## 7. Delivery + end-to-end verification

- [ ] 7.1 Commit the change with a Conventional Commit (e.g. `feat(demo): add in-browser funnel demo landing page`) and push to `beta`
- [ ] 7.2 Watch CI to green with `gh run watch` (Release workflow on `beta`), fixing any failures
- [ ] 7.3 Confirm the `beta` prerelease cut and the `publish-docs` job deployed (`gh run view --log`)
- [ ] 7.4 `curl -fsI https://beta.simtest-funnel.pages.dev/demo/` returns HTTP 200 (demo page reachable)
- [ ] 7.5 `curl -fs https://beta.simtest-funnel.pages.dev/demo/` and assert the HTML references the pinned Plotly script and the demo bundle
- [ ] 7.6 `curl -fsI` the demo's `*.wasm` and `reference.csv`/`test.csv` assets and confirm 200 + `application/wasm` content-type on the wasm
- [ ] 7.7 Confirm the root hub (`curl -fs https://beta.simtest-funnel.pages.dev/`) links to GitHub, `demo/`, and the API doc trees, and that those trees still resolve
- [ ] 7.8 Open `/demo` in a browser and confirm e2e: three plots render with x PASS, y PASS, z FAIL
