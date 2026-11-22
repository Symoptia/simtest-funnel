# Design

## Context

See proposal.md (Why). Facts established before deciding (2026-11-22):

- **SDK argument handling** (`mcp` 2.3.0, `MCPServer`): `Tool.from_function`
  builds an argument model with `create_model(..., __base__=ArgModelBase)`;
  `ArgModelBase` sets only `arbitrary_types_allowed`, so pydantic's default
  `extra="ignore"` applies: unknown top-level names are dropped silently.
  The published `inputSchema` is `arg_model.model_json_schema()` and has no
  `additionalProperties` at the top level. The nested input models
  (`ToleranceSpec`, `XRange`, `ColumnPair`) already had `extra="forbid"`,
  so their schemas said `additionalProperties: false` and an unknown key
  failed with pydantic's generic "Extra inputs are not permitted" (no
  suggestion). `Tool.run` turns a `ValidationError` into
  `ToolError(f"Error executing tool {name}: {exc}")`; a `ToolError` raised
  inside a validator would become an unexpected error with its text
  withheld. `MCPServer(tools=[...])` accepts prebuilt `Tool` objects;
  `Tool.parameters` and `FuncMetadata.arg_model` / `output_schema` are
  public fields read on every call.
- **Field test reproduction**: `describe_signals` with `header_lin: 4` on
  the Open-Meteo file returned 362 rows (header on line 1) instead of 360.
- **Core definitions** (`crates/simtest-funnel-core/src/errors.rs`,
  `summary.rs`): a test point's deviation is `y - upper(x)` when above,
  `y - lower(x)` when below, 0 inside, with the bounds interpolated by
  `interpolate_clamped` (linear on the segment ending at the first vertex
  with `x_i >= x`, left value on segments shorter than 1e-10, clamped
  outside). `WorstDeviation.tube_half_width_y` is
  `0.5 * (upper(x) - lower(x))`. The summary carries neither the test
  value nor the reference value at a point; `CompareResult.errors` holds
  one `(x, deviation)` per test point.
- **Coverage precedence** (`classify_status` in `compare.rs`): any judged
  non-zero deviation gives `FAIL` before the clipped extents are compared,
  so `MISSING_REFERENCE` / `MISSING_TEST` appear only when the overlap
  passes. Reproduced: reference 0..10, test 0..8 with a bump fails as a
  plain `FAIL` and the result carried no hint; the same files without the
  bump give `MISSING_TEST` and the "time ranges differ" note.
- **Record edge**: reference `sin(t)` at 0.05 from 0 to 10, test delayed by
  0.1, `atoly 0.06, atolx 0.15` fails at t = 0 only (deviation -0.0398):
  the upper/lower bound at t is built from reference samples within
  `[t - half_x, t + half_x]`, and there are none before the first sample.
- **Versions**: hatchling writes the server's metadata version as spelled
  in `pyproject.toml` (`1.0.0-beta.21`); maturin normalises the library's to
  `1.0.0b21`. `serverInfo.version` and `--version` come from the server's
  metadata; `simtest.funnel.version()` returns the Rust crate's SemVer
  string. `uv.lock` already records both as `1.0.0b21`.

### Description sizes (measured with an in-process client)

Characters, approximate tokens (characters / 4), network access off:

| Text | Before | After |
| --- | --- | --- |
| Server instructions | 1694 (~424) | 1006 (~252) |
| `describe_signals` description | 2278 (~570) | 1705 (~426) |
| `compare_signals` description | 8257 (~2064) | 3557 (~889) |
| `plot_signals` description | 4818 (~1204) | 1682 (~420) |
| Sum of the four | 17047 (~4261) | 7950 (~1987) |
| Whole `tools/list` result (descriptions and schemas) | 57775 (~14443) | 46030 (~11507) |

With network access on the sum goes from 18660 to 9065 characters.

## Goals / Non-Goals

**Goals:**

- An agent learns of a misspelt argument from the first call.
- Every refusal and every result field an agent must interpret states its
  meaning where the agent sees it (message, output schema, description).
- Fewer tokens per session without losing anything needed to call the
  tools correctly on the first try.

**Non-Goals:**

- No encoding detection or encoding argument (owner decision: UTF-8 only).
- No change to the Rust core, its summary or the TypeScript / WASM APIs.
- No change to the version numbering itself (`split-mcp-versioning` gives
  the server its own 0.x line); only the spelling of what is reported.

## Decisions

### D1. Strict arguments through a `Tool` subclass

`StrictTool` (in `server.py`) builds each tool with `Tool.from_function`,
then replaces the argument model with a subclass that sets
`extra="forbid"` and a `mode="before"` validator refusing unknown keys
(`arguments.strict_model`), and republishes `parameters` from that model
(top level `additionalProperties: false`). Nested input models derive from
`arguments.StrictInput` with the same validator, so pydantic reports each
unknown key at its location (`tolerances[0]`, `column_tolerances.x`). The
server is created with `MCPServer(tools=[...])` instead of decorators.
`StrictTool.run` validates first and, on a `ValidationError`, raises
`ToolError` with a compact text (`arguments.describe_validation_error`):
one line per argument path at fault, union member tags dropped, the input
value quoted (cut to 60 characters), the unknown-name message verbatim.
Suggestions use `difflib.get_close_matches` (cutoff 0.6); without a close
match the accepted names are listed.

Alternatives: (a) only `extra="forbid"` on a subclass: schema and
behaviour agree, but the error is pydantic's "Extra inputs are not
permitted" with the whole input repeated and no suggestion; (b) raising
`ToolError` from a validator: the SDK turns it into an unexpected error and
withholds the text; (c) patching `ArgModelBase` globally: affects every
server in the process. The subclass touches only public fields of the SDK.
The compact rendering changes the wording of all argument errors (they
were pydantic's multi-line report); the pydantic messages themselves are
kept, so the change is in layout only.

Generated `title` keywords (`"title": "Header Line"`) repeat the names; they
are removed from the input and output schemas (`arguments.strip_titles`,
which leaves a property named `title` alone).

### D2. UTF-8 check in the shared reader

`reader.check_utf8` runs on the whole file after a UTF-8 byte-order mark
is skipped: a UTF-16 / UTF-32 byte-order mark is named as such; otherwise
`bytes.decode("utf-8")` either succeeds or gives the first bad byte, from
which the physical line (counted like the reader counts lines: CRLF, CR,
LF), up to 40 characters of context on either side (bad bytes shown as
`\xNN`), the bytes in hex and their Windows-1252 reading are derived. The
reader is embedded verbatim in snippets, so the snippet gives the same
text; its `_columns` helper adds the path. The server reports it without
the preamble hint (`CsvEncodingError`), and a URL input shows the URL, not
the cache path. Cost: one extra decode of the file (the parse decodes it
again); negligible next to parsing. The URL charset refusal also says what
to do.

Message (local file):
`<path>: not valid UTF-8, the only encoding read: line 1 has the byte(s)
0xB0 ('°' in Windows-1252) in "time,value (\xb0C)". The file was probably
saved in a legacy code page such as Windows-1252 (e.g. Excel's plain "CSV
(Comma delimited)" format); re-save it as "CSV UTF-8" (in Excel: Save As,
"CSV UTF-8 (Comma delimited)") or convert it to UTF-8`.

### D3. `difference` computed in the server

Field `worst.difference` and `intervals[].worst_difference`: test value
minus the reference value at the same x. The test value is the test
sample itself: the first test point whose x and deviation equal the
worst point's (test times may repeat at a step, so x alone could be
ambiguous; found by binary search on the non-decreasing test times). The
reference value is the reference column interpolated at x with exactly the
core's `interpolate_clamped` arithmetic (`compare.interpolate_like_library`):
at a repeated reference time, its first value. Rounded to 10 significant
digits like the other value fields.

Alternatives: extend the core's `summarize` with `y_ref` / `y_test`
arguments: a signature change in Rust, Python and TypeScript for one
server-side field, with nothing gained in accuracy, so not clearly cleaner;
derive the test value as `bound + deviation`: exact only up to rounding,
and the bound must be re-interpolated anyway. Intervals get the field too:
each interval already names its worst point, and "how far off at 17:00"
is the natural follow-up; the name `worst_difference` follows `worst_x`
(an attribute of the interval's worst point, not the largest difference
in the interval), which its description states.

The text rendering: `worst -0.9 outside the tube at t=... (test -
reference -3, tube half-width 2.15)` and per interval `(6 pts, worst -0.9
at t=..., test - reference -3)`.

### D4. Notes

*Record edge.* For each row the library judged `fail`, with the resolved
tolerances of its comparison and the reference time span inside x_range
(the `rtolx` base), `half_x` is evaluated at the first and the last
reference sample (`max(atolx, rtolx * span, ltolx * |t|)`). The row counts
when `half_x > 0` there and a violation interval starts before
`first + half_x` (or ends after `last - half_x`). One note names the
count, up to three rows, the reason and an `x_range` that excludes the
edge for the first such row (`lo = first + half_x`, `hi = last - half_x`).
The rule depends on the reference's ends, not on x_range: inside the
reference the tube is built from the reference beyond the window
(`x-range-window`), so a window edge is not a record edge. Cheap: uses the
full interval list of the summary already computed.

*Differing spans when the overlap fails.* Both extents are clipped to
x_range and compared with the core's `eps` (`1e-12 * max(|ends|)`); if they
differ and at least one row failed, a note gives both spans, which side
extends beyond the other (with the status it would have got), the failing
rows and the x_range of the overlap. The existing "time ranges differ"
note for `MISSING_*` rows and "do not overlap" note are unchanged.

### D5. Version spelling

| Surface | Form | Why |
| --- | --- | --- |
| Python distribution metadata (`simtest-funnel`, `simtest-funnel-mcp`) | PEP 440 (`1.0.0b21`) | What pip, uv and PyPI show and normalise to; what users type in `uvx simtest-funnel-mcp==...` |
| MCP `serverInfo.version`, `simtest-funnel-mcp --version` | PEP 440, the server's metadata version | The same string a user installs and reports; no second spelling |
| Exact pin `simtest-funnel==...` in the server's metadata | PEP 440 | Same as the metadata it pins |
| Snippet header `pip install "simtest-funnel>=..."` | PEP 440 (library metadata) | A pip requirement |
| `simtest.funnel.version()`, Rust `version()`, TypeScript `version()`, `Cargo.toml`, `package.json` | SemVer (`1.0.0-beta.21`) | The compiled core's version, shared by all bindings; its docstring now names both forms |

The release's `prepareCmd` calls `scripts/release-python-versions.sh
<semver>`, which converts `X.Y.Z[-alpha|beta|rc.N]` to `X.Y.Z[a|b|rcN]` and
writes both Python projects and the pin; it fails on anything else. This
does not conflict with `split-mcp-versioning`: that change moves the
server's lines into its own release configuration and uses final 0.x
versions, whose SemVer and PEP 440 forms are identical; the library line
keeps calling this script for the library project.

### D6. Description layout

- Instructions: purpose, flow, the cross-tool rules the field test found
  decisive (absolute paths, header_line, `pairs` / `test_column`, no time
  tolerance by default, seconds on date-time axes with "3 hours = atolx
  10800", where plot files may be written); network warnings unchanged.
- `describe_signals` carries the CSV dialect, header-line and date-time
  rules once; `compare_signals` and `plot_signals` refer to it instead of
  repeating them (they were in all three descriptions).
- `compare_signals` keeps the tube formula, resolution rule, fallback,
  pass condition, x-tolerance meaning, the worked examples ("1 % in y,
  0.5 s in x", "2 °C and 3 hours" = `atolx 10800`, ISO x_range bounds, a
  `pairs` example) and gains a short "READING A ROW" part (D3, D4). The
  x_range window paragraph lives in the `x_range` argument description; the
  snippet path rules in `include_snippet`; time-limit details in
  `time_limit`; the per-axis override rule in `column_tolerances`.
- `plot_signals` keeps the workspace-root rule for `output_path` and the
  preview; SVG details moved to `output_path`.
- A test bounds each description's size (about 15 % above the new sizes).

## Risks / Trade-offs

- [A client sends extra keys (for example its own metadata) in the tool
  arguments] → such calls now fail; the MCP specification puts client
  metadata in `_meta`, not in `arguments`, and the schema always declared
  the allowed names. The error names the key.
- [Shorter descriptions omit a detail an agent needed] → the detail is in
  the argument or field description in the same `tools/list`; the skill's
  examples run against the server in CI (`test_mcp_skill.py`).
- [The record-edge note fires for a row that also fails elsewhere] → the
  note says "if that edge is a row's only failure"; rows failing only
  elsewhere get no note (tested).
- [`difference` disagrees with a user's own interpolation at a step] → it
  follows the library's convention (first value at a repeated time), stated
  in the field description.
- [The release script uses GNU `sed -i`] → it runs on the Ubuntu release
  runner only, like the commands it replaces.

## Migration Plan

Beta line: no compatibility shim. Callers passing unknown argument names
must drop or correct them; results gain fields only. The next release
publishes PEP 440 metadata versions; nothing else changes for installers.
