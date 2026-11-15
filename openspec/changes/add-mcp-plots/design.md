# Design

## Context

See proposal.md for motivation and specs/mcp-plots/spec.md for the required
behaviour. Relevant current state:

- The server (`python/simtest-funnel-mcp/`, change `add-mcp-server-local`)
  has two read-only tools. `compare.run_compare` does column selection,
  server-side column problems (missing, bad cells, time column), the
  coverage problem texts and the summary row; `server.py` does roots, path
  resolution, rounding (`_trim`) and returns text plus structured content.
- `simtest.funnel` already provides everything numeric the plot needs:
  `compare` (tube `lower`/`upper` and `errors` on the full test grid),
  `summarize` (all violation intervals with `worst_x`) and
  `downsample_min_max(x, y, buckets, pinned_x)` (add-signal-downsampling).
- Observation while prototyping: tube bounds are **not** always compact.
  For a noisy 200k-sample signal the library returns ~20k points per bound,
  for a smooth one ~200k (about one per reference sample). The bound
  *lines* are simplified by the renderer (sub-pixel, visually lossless) to
  a few kB, but a *filled* band between them is not.
- Claude Code declares workspace roots (verified: a read of `/etc/hostname`
  is refused with the repository as root).

## Goals / Non-Goals

**Goals:**

- One new tool that reuses `run_compare` unchanged in meaning, so a plot
  is exactly the `compare_signals` row for the same arguments.
- Rendering cost and output size bounded independently of the sample
  count (except tube bounds, see Risks).
- No start-up cost for the plotting dependency.

**Non-Goals:**

- No theming/style arguments, no figure-size or bucket arguments (fixed,
  documented values; can be added later without changing the contract).
- No separate "view window": see the x-range decision.
- No change to `describe_signals` / `compare_signals` behaviour or schema.

## Decisions

### Tool name and arguments

`plot_signals(reference_path, test_path, column, tolerance=None,
x_range=None, output_path=None, overwrite=False, max_intervals=5)`.

- Name: same `*_signals` family as the other two tools, so it sorts and
  reads together with them. (`plot_comparison` was the alternative.)
- `reference_path`, `test_path`, `x_range`, `max_intervals`: identical
  names, shapes and meaning to `compare_signals`.
- `column`: one exact column name (singular because it is one value; a
  string that is not a column name and contains glob characters is
  refused instead of expanded, since a pattern could match several).
- `tolerance`: singular, because a plot shows one tolerance set; its shape
  is exactly one entry of `compare_signals.tolerances` (`ToleranceSet`,
  optional `label`), so an agent can copy a set across unchanged. Reusing
  the name `tolerances` with a non-list shape would be a trap.
  `column_tolerances` is not offered: with one column it is the same as
  `tolerance`.

### Output path optional; preview only when omitted

Omitting `output_path` returns only the inline preview and writes nothing.
An agent often wants to look before deciding to save; making the path
required would force junk files. Alternative (required path) rejected for
that reason.

### Write-path checks (stricter than reads)

In order, before loading any CSV, so a bad path fails fast:

1. extension `.svg` or `.png` (case-insensitive), else error;
2. the parent directory must exist and be a directory; the server never
   creates directories (a typo must not create trees);
3. the location, with the parent and any existing symlink resolved, must
   be inside a workspace root, or, **when the client declares no roots,
   inside the server's working directory** (reads accept any path without
   roots; writes do not);
4. the resolved target must still have the requested extension (a symlink
   `plot.svg -> notes.txt` is refused);
5. an existing target must be a regular file, and is refused unless
   `overwrite=true`.

The file is written only after both renderings succeeded, from memory,
with `open(..., "xb")` (exclusive create) when not overwriting, so a race
cannot clobber a file that appeared meanwhile and a failed call leaves
nothing behind. No temporary file is used (it would be a second file).

### Overwrite: refuse by default

Default `overwrite=false`. An agent re-plotting after a model change passes
`overwrite=true` deliberately; documents are never silently replaced.

### Tool annotations

`read_only_hint=False`, `destructive_hint=True` (it can replace an existing
file, though only on request), `idempotent_hint=True` (same arguments give
a byte-identical file or the same refusal, no additional effect),
`open_world_hint=False`. The other two tools keep their read-only
annotations.

### Plotting library: matplotlib (Agg + SVG backends)

- Renders SVG and PNG headless with no display and no system libraries;
  ships manylinux/macOS/Windows wheels, so `uvx simtest-funnel-mcp` stays
  a clean install. Used through `matplotlib.figure.Figure` directly (no
  `pyplot`, no global backend selection or figure registry).
- Added install (Linux x86-64, CPython 3.12): matplotlib 3.11 plus
  contourpy, cycler, fonttools, kiwisolver, pillow, pyparsing (numpy,
  packaging, python-dateutil were already present): **~24 MB of wheels
  downloaded, ~77 MB installed** (matplotlib 25 MB, fontTools 23 MB,
  pillow 20 MB incl. bundled libs, kiwisolver 6 MB).
- Imported lazily inside the render function (and Pillow inside the
  preview function), so server start-up is unchanged: stdio spawn →
  `list_tools` median 0.764 s before, 0.777 s after (noise level);
  `matplotlib` is not in `sys.modules` after importing the server.
- Alternatives: pygal / hand-written SVG (PNG would need cairosvg → system
  libcairo, breaks `uvx`); Plotly + kaleido (bundles Chromium, ~100 MB+,
  explicitly out of scope); Bokeh (needs a browser for PNG). Dependency
  constraint `matplotlib>=3.8`.

### Determinism

`svg.hashsalt` fixed, SVG metadata `Date` removed and `Creator` fixed,
PNG `Software` metadata removed, the bundled DejaVu Sans used explicitly
and glyphs embedded as paths (`svg.fonttype = "path"`), so output does not
depend on system fonts. Same input and matplotlib version → byte-identical
SVG and PNG (tested). A matplotlib upgrade may change bytes; that is
acceptable for a diff-friendly, not a frozen, format.

### Sizes and resolution

- Figure 8 × 4.5 in (SVG document 576 × 324 pt), 9–10 pt text.
- Inline preview: 100 dpi → **800 × 450 px**, then reduced to a 128-colour
  palette (median cut, no dither): visually identical, ~25 kB instead of
  ~73 kB for the demo plot. Image token cost depends on pixels, not bytes,
  and 800 px keeps titles and tick labels legible.
- PNG file: 200 dpi → 1600 × 900 px, full colour.
- Drawing buckets: 1000 for reference and test (≤ ~2000 points per series
  plus pins), more than the horizontal pixels of any rendering, so the
  min/max envelope is visually exact; SVG stays ~100 kB for the demo.

### Drawing data and the "never contradict" rule

- The comparison is `run_compare(columns=[column], tolerances=[set],
  max_rows=1)` on the full data. `RowRecord` gains an optional `library`
  field holding the library `CompareResult` and the full `ViolationSummary`
  (computed once in the existing loop; `_library_row` now receives the
  summary instead of recomputing it), so the plot neither repeats the
  comparison nor re-implements any rule. Snippets and `compare_signals`
  output are unchanged.
- View window: `x_range` clipped to the union of both files' time extents.
  Reference, test and bounds are sliced to the view plus one neighbour on
  each side (lines reach the axes edge); bounds use the contiguous index
  range of their in-view points because their x need not be monotonic.
- Reference: `downsample_min_max(..., 1000)`. Test: same, pinning the
  `worst_x` of **every** violation interval (not only the listed ones).
- Violating test points are computed on the full data exactly as
  `summarize` judges them: deviation ≠ 0 and x within `x_range` ∩
  reference span. Markers are the drawn test points in that mask. Since
  `worst_x` is a test sample of the interval and pins keep the sample at
  that x (and all samples sharing it), every interval has a marker.
- Regions: every interval `[start_x, end_x]`, widened centrally to at
  least 0.4 % of the view (~3 px in the preview, so a single-sample spike
  is visible) and merged where they then overlap; at most ~250 regions.
- Error verdicts raise a tool error with the row's problem text (and the
  comparison notes) and write nothing: a plot of a comparison that did not
  run would show a verdict that does not exist.

### Visual design

- White figure background (opaque), dark ink text. This keeps SVG and PNG
  readable on light and dark documents alike, at the cost of appearing as a
  light card on a dark page (no `prefers-color-scheme` styling; see Risks).
- Reference: dark grey `#3d3d3a`, dashed. Test: blue `#2a78d6`, solid.
  Distinguishable by line style without colour.
- Tube: grey band (22 % alpha) between thin solid grey bound lines.
- Violations: red shaded regions (16 % alpha) plus red `x` markers on the
  violating test points (shape, not only colour).
- Legend below the axes (never covers data): reference, test, tolerance
  tube, and "outside the tube" only when violations exist.
- Title (left): `z: FAIL, 338 of 1001 points outside the tube, 3 violation
  interval(s)`; second line `tolerances [loose]: x atolx=0.1 | y atoly=0.1`
  (non-zero resolved coefficients per axis, `0` for an axis without
  tolerance). Axis labels: time column name, signal column name.
- SVG element ids: `reference`, `test`, `tube`, `violation-regions`,
  `violation-markers` (tests look for the last two).

### Tube band for large tubes

Tube bounds are drawn with all their points as decided. The bound lines
are vector (renderer simplification keeps them to a few kB for smooth
signals). The filled band is a single polygon, which the renderer never
simplifies: for the smooth 200k case it made a 9.9 MB SVG. Above 20 000
tube points the band is therefore **rasterized inside the SVG at 200 dpi**
(the bound lines, curves, markers and text stay vector): 97 kB instead of
9.9 MB. Alternatives: no band (worse readability), simplifying the bounds
ourselves (contradicts the "bounds not downsampled" decision).

The band is drawn as a `PolyCollection`, not `Axes.fill`: `fill` computes
patch limits by iterating Bezier segments in Python (16 s for 400k
vertices).

### Result shape

Structured content (`PlotResult`): `reference`, `test`, `x_range`
(as in `compare_signals`), `tolerance_set` (`label`, `given`,
`resolved`), `row` (exactly a `compare_signals` row), `view` (`lo`, `hi`),
`file` (`path`, `format`, `bytes`, PNG `width_px`/`height_px`; absent when
no output path), `preview` (`format`, `width_px`, `height_px`, `bytes`),
`drawn` (point counts per series, markers, regions, buckets), `notes`. The
same `_trim` rounding applies. The text lists the files, the resolved set,
the row line in `compare_signals` format, the file written, the preview
size and the drawn counts. Content: text block, then the PNG image block.
~1.6 kB structured for a 200k-sample input.

### x-range: restrict and zoom, no separate view window

`x_range` keeps its `compare_signals` meaning and is also the window
shown. Then the plot is always exactly a `compare_signals` row and never
has violations outside the view. A separate view window would show the
full-range tube zoomed (relevant when `rtol*` bases change with the
window), but adds a second range concept and a "violations outside the
view" case; it can be added later if needed.

### Instructions and descriptions

Server instructions now mention `plot_signals` and say that only it
writes, only the given path. The tool description states what is drawn,
the semantics equality, file formats, path rules, overwrite and the
x-range meaning.

## Risks / Trade-offs

- [Conflict with the `mcp-server` spec of `add-mcp-server-local`, which
  says the server exposes exactly two read-only tools and writes no
  file] → `mcp-plots` states the exception; `mcp-server` has no main spec
  yet (change not archived), so a MODIFIED delta is impossible here. Its
  wording must be reconciled before or when both are archived.
- [matplotlib writes its font cache (`~/.cache/matplotlib/fontlist-*.json`,
  or `$MPLCONFIGDIR`) the first time it is imported in an environment] →
  documented library side effect; the server itself writes only the plot
  file. Avoiding it would need patching matplotlib internals.
- [Large install, ~77 MB] → only matplotlib does SVG + PNG headless without
  system libraries; lazy import keeps start-up unaffected.
- [Noisy long signals give large bounds: ~590 kB SVG for a noisy 200k
  input, since sub-pixel simplification cannot remove noise zig-zags] →
  accepted under the "bounds not downsampled" decision; PNG output is an
  alternative for such signals.
- [White card on dark documents] → stated limitation; readable everywhere.
- [First plot call is slower (matplotlib import, font cache on first use
  in a fresh environment)] → one-off per server process.
- [Comparison time dominates for long noisy signals (~15 s library time
  for 200k noisy samples)] → identical to `compare_signals`; not a plot
  issue.
