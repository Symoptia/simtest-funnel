# Proposal

## Why

A field test of the MCP server on a real Windows 11 machine found that it
works there, but also found usability problems that make an agent guess
or retry: misspelt arguments are silently ignored, a non-UTF-8 file fails
with a raw codec message, `deviation` and `tube_half_width_y` are not
explained and the plain test-minus-reference gap is missing, failures at
the first or last sample under a time tolerance come without explanation,
version strings are spelled two ways and the tool descriptions cost
several screens of context. A skill-writing agent added that a comparison
of files with different time spans whose overlap fails is a plain `fail`
with no hint that the spans differ.

## What Changes

- **Unknown arguments refused** by all three tools, also inside tolerance
  sets, pairs, `x_range` and `column_tolerances` entries, with the closest
  valid name suggested (`unknown argument 'header_lin'; did you mean
  'header_line'?`). The published input schemas say
  `additionalProperties: false` everywhere. Argument errors are stated
  compactly (one line per argument at fault). **BREAKING** for callers that
  relied on unknown names being ignored (beta line, no shim).
- **Non-UTF-8 files** (local, URL, and in the generated pytest snippet's
  reader) are refused with an actionable message: not valid UTF-8, the line
  and offending bytes in context, the likely cause (a legacy code page such
  as Windows-1252, Excel's plain "CSV"; UTF-16/UTF-32 when a byte-order mark
  says so) and the fix (save as "CSV UTF-8" or convert). UTF-8 stays the
  only encoding read.
- **Result clarity**: new `worst.difference` and per-interval
  `worst_difference` (test minus the reference at the same x); output-schema
  field descriptions and the `compare_signals` description define
  `deviation` (distance outside the tube, signed) and `tube_half_width_y`
  (effective vertical half-width); the text rendering shows the difference.
- **Notes**: a note when failures under an x tolerance lie within one x
  half-width of the first or last reference sample (with an `x_range` that
  excludes the edge), and a note when the files cover different time spans
  and the overlap fails.
- **Versions**: both Python packages carry PEP 440 versions (`1.0.0b21`),
  so distribution metadata, MCP `serverInfo.version` and `--version` agree;
  the release writes the PEP 440 form into the Python projects.
- **Shorter descriptions**: server instructions and tool descriptions cut
  from about 17 000 to about 8 000 characters (network off) by removing
  repetition and moving rarely needed detail into argument descriptions,
  keeping the examples the field test found decisive; generated `title`
  keywords are dropped from the schemas.
- **Docs**: the server README states the output-directory list separator
  as the platform's (`;` on Windows); the agent skill reads the new field
  and notes and gains verified Windows platform notes.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `mcp-server`: unknown arguments refused; UTF-8 error message; difference
  field and field definitions; record-edge and differing-span notes;
  concise descriptions; the x-range window explained in the argument
  description.
- `mcp-plots`: the plot result carries the difference and all comparison
  notes.
- `python-distribution`: Python package versions in PEP 440 form.

## Impact

- `python/simtest-funnel-mcp/src/simtest_funnel_mcp/`: new `arguments.py`;
  `server.py` (tool construction, descriptions), `models.py`, `compare.py`,
  `reader.py` (embedded in snippets), `csvio.py`, `render.py`,
  `snippet.py`, `fetch.py`, `__init__.py`; tests; README.
- `crates/simtest-funnel-python/pyproject.toml`,
  `python/simtest-funnel-mcp/pyproject.toml` (PEP 440 versions),
  `.releaserc.json`, new `scripts/release-python-versions.sh`; the docstring
  of `simtest.funnel.version()`.
- `plugins/simtest-funnel/skills/funnel-signal-comparison/` (SKILL.md,
  `references/results.md`, `references/setup.md`).
- No change to the Rust core, the WASM bindings or the TypeScript SDK.
