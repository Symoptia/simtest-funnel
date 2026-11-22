# Keeping a comparison as a CI test

`compare_signals` can return a self-contained pytest file that repeats the
comparison without the MCP server. This file is the workflow around it; the
`include_snippet` description of the tool says what the snippet contains.

## Contents

- [When to offer it](#when-to-offer-it)
- [Steps](#steps)
- [Where the data files must be](#where-the-data-files-must-be)
- [What the test asserts](#what-the-test-asserts)
- [Inputs that were URLs](#inputs-that-were-urls)
- [Updating the test](#updating-the-test)

## When to offer it

Offer it when the user will run the same check again: a regression check
of a model or solver change, a nightly simulation against a baseline, a
forecast quality check. Do not create test files unasked.

Agree on the comparison first (files, columns, tolerances). The snippet
freezes exactly the call that produced it.

## Steps

1. Repeat the agreed `compare_signals` call with `include_snippet` set to
   true and everything else unchanged. Example, with a checkout of
   simtest-funnel as the project
   (`examples/open-meteo/stockholm-2026-11-05-to-19.csv`;
   [Weather data by Open-Meteo.com](https://open-meteo.com/),
   [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)):

   ```jsonc
   // compare_signals
   {
     "reference_path": "examples/open-meteo/stockholm-2026-11-05-to-19.csv",
     "header_line": 4,
     "pairs": [
       {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day1 (°C)", "label": "day1"}
     ],
     "tolerances": [{"label": "2C", "atoly": 2}],
     "include_snippet": true
   }
   ```

   The row passes, and the structured field `snippet` holds the test file.
   Its data path is relative to the project:
   `DATA_ROOT / 'examples/open-meteo/stockholm-2026-11-05-to-19.csv'`.

2. Write the snippet unchanged to the user's test directory, with a name
   that says what it guards, e.g. `tests/test_forecast_day1_funnel.py`.
   Follow the project's layout if it has one.
3. Tell the user which CSV files must be committed and at which paths (the
   `REFERENCE` and `TEST` lines of the snippet).
4. Tell the user what the test needs: the requirement line at the top of the
   snippet (the `simtest-funnel` library, pandas, pytest) belongs in the
   project's test dependencies.
5. If the project's tools allow it, run the test once and report the
   result.

## Where the data files must be

The snippet resolves data paths against `SIMTEST_FUNNEL_DATA_ROOT`, else
the directory pytest is started from. Paths are written relative to the
client's first workspace root (normally the project), so:

- Run pytest from the project root in CI, or set
  `SIMTEST_FUNNEL_DATA_ROOT` to the directory the paths are relative to.
- Files outside the project keep an absolute path with a comment saying it
  will not resolve elsewhere. Before generating the snippet, ask the user
  to copy such files into the repository, then compare the copies.
- Large result files: suggest Git LFS or a smaller export (only the
  compared columns) rather than leaving the test unable to find its data.

## What the test asserts

Each case asserts the status the server observed. A snippet made from a
passing comparison is a regression gate. One made from a failing comparison
asserts the failure, which is useful only to track a known difference: say
so clearly, and tell the user that for a gate every expected status must be
`PASS` (the snippet's header comment says the same).

Row errors (missing columns, coverage) are frozen too. Fix them before
generating the test instead of committing a test that expects an error.

## Inputs that were URLs

A snippet never fetches during a normal run. For a URL input it reads a
local copy (named after the URL's last path segment, under the data root)
and checks its SHA-256 against what the server saw. Tell the user to run
the test once with `SIMTEST_FUNNEL_DOWNLOAD=1` to download the copy, then
commit it, so CI runs offline. If the remote file changes, the test fails
with the hashes instead of silently comparing new data.

## Updating the test

When the reference legitimately changes (a new baseline) or the tolerance
is renegotiated, rerun the comparison with `include_snippet` and replace
the whole file. Do not edit expected statuses or tolerances by hand: the
file should always be what the server produced for a stated comparison.
Mention the change of baseline or tolerance in the commit message.
