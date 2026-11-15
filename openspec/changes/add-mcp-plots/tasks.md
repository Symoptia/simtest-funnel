# Tasks

## 1. Dependency

- [x] 1.1 Add `matplotlib>=3.8` to `python/simtest-funnel-mcp/pyproject.toml`, run `uv lock` / `uv sync`, and verify `uv.lock` gains only the new packages (no workspace version bumps) and `import simtest_funnel_mcp.server` does not import matplotlib

## 2. Comparison data for plots

- [x] 2.1 Keep the library `CompareResult` and full `ViolationSummary` on each library-decided `RowRecord` (summary computed once, passed to `_library_row`) and verify the existing compare and snippet tests still pass unchanged

## 3. Plot preparation and rendering

- [x] 3.1 Implement `plot.prepare_plot` (one exact column, one tolerance set, `run_compare` on full data, error verdicts refused, view window, min/max reduction with every interval's `worst_x` pinned, violating-point mask as `summarize` judges, widened/merged regions) and verify with unit tests that every violation interval contains a marked drawn point for a single-sample spike in a 200k signal and for a delayed steep edge, and that a passing case has no markers or regions
- [x] 3.2 Implement `plot.render` (lazy matplotlib, white background, line styles, tube band and bounds, regions and markers with SVG ids, legend, title with verdict and resolved tolerances, deterministic metadata, band rasterized above 20 000 tube points) and verify with tests that the SVG parses as XML and contains the violation ids only for failures, the PNG has the right signature and size, two renderings are byte-identical, and the smooth 200k SVG stays below 300 kB

## 4. plot_signals tool

- [x] 4.1 Implement output-path checks (extension, existing directory, roots or working directory, symlink target extension, existing file vs `overwrite`) and exclusive writes after rendering, and verify with unit tests for inside/outside roots, no roots, existing file with and without overwrite, missing directory, directory as target and wrong extension, each asserting nothing was written on refusal
- [x] 4.2 Implement `plot_signals_impl` and the tool registration (arguments as designed, annotations not read-only / destructive / idempotent / closed-world, text + PNG image content, `PlotResult` structured content, quantized 800x450 preview) and verify with unit tests: result row equals the `compare_signals` row, error statuses raise without writing, x-range zooms, structured result for 200k samples stays below 4 kB and contains no sample arrays
- [x] 4.3 Update the server instructions, the stdio end-to-end test (three tools, annotations, `plot_signals` call returning an `image/png` 800x450 block and writing an SVG under the root) and verify `make test-python` passes

## 5. Documentation

- [x] 5.1 Document `plot_signals` in `python/simtest-funnel-mcp/README.md` (arguments, output files, path rules, preview, determinism, matplotlib font-cache note, no longer strictly read-only) and the root README MCP section, and verify the described arguments match the tool schema

## 6. Integration checks

- [x] 6.1 Save failing and passing sample plots of the demo files (SVG + inline preview PNG) to the scratchpad, inspect the PNGs for legibility, and fix any issue found
- [x] 6.2 Run `make build`, `make lint`, `make test` and `openspec validate add-mcp-plots --strict` and verify all pass
