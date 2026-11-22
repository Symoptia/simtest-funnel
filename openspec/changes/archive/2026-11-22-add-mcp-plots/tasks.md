# Tasks

## 1. Dependency

- [x] 1.1 Add `matplotlib>=3.8` to `python/simtest-funnel-mcp/pyproject.toml`, run `uv lock` / `uv sync`, and verify `uv.lock` gains only the new packages (no workspace version bumps) and `import simtest_funnel_mcp.server` does not import matplotlib

## 2. Comparison data for plots

- [x] 2.1 Keep the library `CompareResult` and full `ViolationSummary` on each library-decided `RowRecord` (summary computed once, passed to `_library_row`) and verify the existing compare and snippet tests still pass unchanged

## 3. Plot preparation and rendering

- [x] 3.1 Implement `plot.prepare_plot` (one exact column, one tolerance set, `run_compare` on full data, error verdicts refused, view window, min/max reduction with every interval's `worst_x` pinned, violating-point mask as `summarize` judges, widened/merged regions) and verify with unit tests that every violation interval contains a marked drawn point for a single-sample spike in a 200k signal and for a delayed steep edge, and that a passing case has no markers or regions
- [x] 3.2 Implement `plot.render` (lazy matplotlib, white background, line styles, tube band and bounds, regions and markers with SVG ids, legend, title with verdict and resolved tolerances, deterministic metadata, fully vector SVG) and verify with tests that the SVG parses as XML and contains the violation ids only for failures, the PNG has the right signature and size, and two renderings are byte-identical

## 4. plot_signals tool

- [x] 4.1 Implement output-path checks (extension, existing directory, allowed location, symlink target extension, existing file vs `overwrite`) and exclusive writes after rendering, and verify with unit tests for inside/outside roots, existing file with and without overwrite, missing directory, directory as target and wrong extension, each asserting nothing was written on refusal
- [x] 4.2 Implement `plot_signals_impl` and the tool registration (arguments as designed, annotations not read-only / destructive / idempotent / closed-world, text + PNG image content, `PlotResult` structured content, quantized 800x450 preview) and verify with unit tests: result row equals the `compare_signals` row, error statuses raise without writing, x-range zooms, structured result for 200k samples stays below 4 kB and contains no sample arrays
- [x] 4.3 Update the server instructions, the stdio end-to-end test (three tools, annotations, `plot_signals` call returning an `image/png` 800x450 block and writing an SVG under the root) and verify `make test-python` passes

## 5. Documentation

- [x] 5.1 Document `plot_signals` in `python/simtest-funnel-mcp/README.md` (arguments, output files, path rules, preview, determinism, matplotlib font-cache note, no longer strictly read-only) and the root README MCP section, and verify the described arguments match the tool schema

## 6. Integration checks

- [x] 6.1 Save failing and passing sample plots of the demo files (SVG + inline preview PNG) to the scratchpad, inspect the PNGs for legibility, and fix any issue found
- [x] 6.2 Run `make build`, `make lint`, `make test` and `openspec validate add-mcp-plots --strict` and verify all pass

## 7. Tube bounds reduced for drawing (review follow-up)

- [x] 7.1 Implement `plot.bound_at` (the library's bound interpolation, bit-identical) and verify with a test that deviations recomputed from it equal the library's `errors` exactly for a smooth 200k and a noisy 50k signal
- [x] 7.2 Reduce both tube bounds with `downsample_min_max` (vertices bracketing the view, 1000 buckets) plus exact bound points inserted only where a judged drawn test point would otherwise be drawn on the wrong side or less far outside, and remove the raster-band fallback; verify with tests that every violation marker lies outside the drawn tube and no non-violating judged drawn test point does (spike in 200k samples, steep edge, noisy 50k with and without x tolerance, demo files incl. 5 buckets, passing variants), that these tests fail without the exact points, that bounds of the 200k / 50k cases are reduced below 3000 points, that short bounds are drawn unchanged, that a zoom between bound vertices still draws the tube, and that the smooth 200k SVG has no `<image>` and stays below 250 kB
- [x] 7.3 Report reduced bound counts in `drawn.tube_lower` / `drawn.tube_upper` and the text, and record before/after SVG sizes for the demo and 200k cases in design.md

## 8. Plot files only in roots or a configured output directory (review follow-up)

- [x] 8.1 Add `--output-dir DIR` (repeatable) and `SIMTEST_FUNNEL_MCP_OUTPUT_DIR` (`os.pathsep`-separated), validated at start-up (exit status 2 with a message for a missing or non-directory entry), and verify with unit tests for parsing, the env variable and `main` rejecting a missing directory
- [x] 8.2 Allow writes only inside a workspace root or a configured output directory (inside either when both exist; relative paths against the first root, else the first output directory), refuse every `output_path` with neither (explaining both ways to enable writing) while the preview still works, keep all other write checks, and verify with unit, in-process and stdio tests (no roots + `--output-dir` / env variable, no roots and no directory, roots + directory, symlink escape, missing directory at start-up)
- [x] 8.3 Update the tool description, server instructions and both READMEs (Claude Code and Claude Desktop configuration), keep the checked-in `.mcp.json` unchanged, and run `make lint`, `make test` and `openspec validate add-mcp-plots --strict`
