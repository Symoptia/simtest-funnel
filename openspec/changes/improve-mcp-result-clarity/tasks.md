# Tasks

## 1. Unknown arguments refused

- [x] 1.1 Add `arguments.py` (`StrictInput`, `strict_model`, unknown-name message with `difflib` suggestion, compact `describe_validation_error`, `strip_titles`); derive `ToleranceSpec`, `XRange`, `ColumnPair` from `StrictInput` (design D1). Verify with `test_mcp_arguments.py` (`test_unknown_message_without_a_close_match_lists_the_names`, `test_strip_titles_keeps_properties_named_title`).
- [x] 1.2 Build the three tools as `StrictTool` (strict argument model, republished input schema, titles stripped, compact errors) and pass them to `MCPServer(tools=...)`. Verify the field-test call (`header_lin: 4`) fails with `unknown argument 'header_lin'; did you mean 'header_line'?`, unknown top-level and nested names fail in all three tools, JSON-encoded nested objects are checked, and every input-schema object has `additionalProperties: false` (`test_mcp_arguments.py`); the skill's examples validate against the real schemas (`test_mcp_skill.py`, helper `strict_schema` removed).
- [x] 1.3 Document strict argument names in the server README. Verify by review.

## 2. Non-UTF-8 files

- [x] 2.1 `reader.check_utf8` (byte-order marks, line, bytes in context, Windows-1252 reading, fix) called by `read_signal_columns`; `CsvEncodingError` reported without preamble hint; the snippet's `_columns` adds the path; the URL charset refusal says what to do (design D2). Verify `test_windows_1252_file_is_refused_with_line_bytes_and_fix`, `test_line_of_a_bad_byte_counts_physical_lines`, `test_utf16_and_utf32_files_are_named_by_their_bom`, `test_utf8_with_bom_and_crlf_and_non_ascii_names_still_read` (`test_mcp_csv.py`), `test_non_utf8_url_content_gets_the_encoding_message` (`test_mcp_url_server.py`) and `test_snippet_reader_refuses_a_non_utf8_file_with_the_same_message` for Windows-1252 and UTF-16 (`test_mcp_snippet.py`).
- [x] 2.2 State the encoding rule in `CSV_HELP` and the README's CSV dialect. Verify `test_descriptions_explain_pairs_header_line_and_date_axis` checks "UTF-8".

## 3. Difference at the worst points and field definitions

- [x] 3.1 Add `Worst.difference` and `Interval.worst_difference` with descriptions, and descriptions for `deviation`, `worst_deviation`, `tube_half_width_y`; compute the difference with `difference_at` / `interpolate_like_library` (design D3); round it like the other value fields; show it in the text rendering. Verify `test_difference_on_the_open_meteo_sample` (worst point 2026-11-19T04:00, deviation -0.9, half-width 2.15, difference -3.0 equal to the cells' difference, also per interval), `test_difference_interpolates_the_reference_like_the_library` (`test_mcp_compare.py`), `test_output_schema_explains_deviation_difference_and_half_width` (`test_mcp_arguments.py`) and `test_plot_reports_the_difference_and_the_record_edge_note` (`test_mcp_plot.py`).

## 4. Notes

- [x] 4.1 Record-edge note (`record_edge_hint`, design D4). Verify `test_record_edge_note_for_a_delayed_test` (generated sin data, delay 0.1, `atoly 0.06, atolx 0.15` fails only at t = 0, note text, suggested `x_range` passes), `test_record_edge_note_at_the_end_for_an_advanced_test` and `test_no_record_edge_note_for_failures_elsewhere`.
- [x] 4.2 Differing-spans note when the overlap fails (`differing_spans_hint`), after confirming that the library reports `FAIL` rather than `MISSING_TEST` then. Verify `test_differing_spans_note_when_the_overlap_fails` (note text; passing overlap keeps `MISSING_TEST` and gets no failure note; the overlap's x_range gets no note).

## 5. Versions

- [x] 5.1 PEP 440 versions in both Python projects and the pin; `scripts/release-python-versions.sh` called from `.releaserc.json`; `library_version()` for the snippet header; docstring of `simtest.funnel.version()` (design D5). Verify `test_python_packages_report_pep_440_versions` (metadata, `__version__`, `serverInfo.version`, `--version`), `test_release_writes_pep_440_versions` (four version forms and a refused one), `uv lock --check` and `uv run simtest-funnel-mcp --version`.

## 6. Shorter descriptions

- [x] 6.1 Measure the instructions and descriptions before the change (design, sizes table), rewrite them (design D6), move details into the `x_range`, `include_snippet`, `time_limit`, `column_tolerances` and `output_path` argument descriptions. Verify `test_descriptions_stay_short` and `test_descriptions_keep_the_decisive_examples` (`test_mcp_arguments.py`), and the updated description tests in `test_mcp_server.py` (whitespace-insensitive; CSV rules only in `describe_signals`; the x-range window checked in the argument description).

## 7. Documentation and skill

- [x] 7.1 Server README: output-directory separator is the platform's path-list separator (`;` on Windows); result fields and notes. Verify by review and `grep -rn "OUTPUT_DIR" --include=*.md`.
- [x] 7.2 Skill: "Reading the result" and `references/results.md` use `difference` and the new notes; `references/setup.md` platform notes from the Windows field test (verified facts only). Verify `test_mcp_skill.py`, including the new check of the quoted difference ("3 °C below the latest run at 04:00").

## 8. Integration checks

- [x] 8.1 Run `make build`, `make lint`, `make test` and `openspec validate improve-mcp-result-clarity --strict`; verify all pass.

## Workflow follow-up

- Archive after review and merge (`openspec archive improve-mcp-result-clarity`).
- `split-mcp-versioning`: its library configuration keeps calling `scripts/release-python-versions.sh` for the library project; the server's own configuration can use it or write its 0.x version directly (identical forms).
