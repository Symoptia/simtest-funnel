# Reading results and drawing conclusions

How to turn a `compare_signals` result into an answer a person can act on.
Field meanings are in the tool's output schema and description; this file
is about what they tell you.

## Contents

- [Error, fail or pass](#error-fail-or-pass)
- [Errors that are not verdicts](#errors-that-are-not-verdicts)
- [Explaining a failure](#explaining-a-failure)
- [Patterns in the intervals](#patterns-in-the-intervals)
- [Time limit and incomplete results](#time-limit-and-incomplete-results)
- [What a result cannot tell you](#what-a-result-cannot-tell-you)
- [Answer template](#answer-template)

## Error, fail or pass

Each row is one column (or pair) under one tolerance set. Read the verdict
first:

- `pass`: every judged test point lies inside the tube. Report it with the
  tolerance it passed under.
- `fail`: at least one test point lies outside. Explain it (below).
- `error`: the comparison could not be judged. Report the problem, not a
  verdict.

A failed **call** (an error message instead of rows) is always a problem
with the inputs or the server: file not found, outside the client's
workspace, unreadable file, URL refused, invalid argument. Fix the call or
tell the user what is needed; do not guess an answer.

`totals` counts all rows. When `rows_omitted` is non-zero, the returned rows
are a subset (errors first, then failures, then passes); say so, or narrow
the call with `columns`.

## Errors that are not verdicts

| Status or message | What it means for the answer | What to offer |
| --- | --- | --- |
| `MISSING_TEST`, `MISSING_REFERENCE` | The files cover different time spans; the overlap passed | Compare the overlap with the `x_range` from the problem text, and say that the rest was not compared |
| `NON_MONOTONIC` | A time column goes backwards (merged runs, duplicated blocks, event iterations) | Ask for a clean file or the part to use |
| `EMPTY_RANGE`, `INSUFFICIENT_DATA` | The `x_range` misses the data, or leaves fewer than two points | Check the window against the spans from describe |
| Column not found | The name differs (units, case) | Use the close names the problem suggests, after describe |
| Non-numeric or empty cells | Bad data in the column | Report the column; do not drop data silently |
| File cannot be read | Wrong header line, not UTF-8, not comma-separated | `header_line` from the hint; ask for a UTF-8 CSV export |

A coverage error is reported only when the overlap passes. If the overlap
fails, the row is a plain `fail` and nothing in it says that the spans
differ; that is one reason to describe both files first and compare their
time spans yourself.

## Explaining a failure

For each failing row, say:

1. **How much.** `points_outside` of `points_compared` and the share of the
   time span outside. With uneven sampling (dense output around events) the
   two shares differ; the span share says "how much of the time".
2. **How far and which way.** The worst deviation is the distance beyond
   the tube's edge at the worst point: positive = test above the tube,
   negative = below. Add `tube_half_width_y` to get roughly how far the test
   is from the reference there. Translate it into the user's terms: "up to
   1.2 °C beyond the 2 °C band, so about 3.2 °C warmer than the reference".
3. **Where.** The intervals give start, end, direction, point count and
   worst deviation. Name the largest one or two with their times;
   `interval_count` says how many there are in total.
4. **How far from passing.** If the call had a looser set or a sweep, name
   the tightest set that passes.

## Patterns in the intervals

| Pattern | Likely meaning | Check |
| --- | --- | --- |
| Short misses at every steep edge, no time tolerance given | Timing: the test is shifted or delayed | Repeat with a small `atolx` |
| All intervals in one direction, spread over the record | Offset or bias | Worst deviation is similar everywhere |
| One long interval | An event or regime the test handles differently | Zoom with `x_range`, plot that row |
| Many short intervals in both directions | Noise or a slightly different oscillation | Compare the value tolerance with the noise level |
| Misses only at the start or end | Initial conditions, start-up, end effects | Ask whether that window should count |

These are hypotheses. Phrase them as "likely" or "consistent with", and say
what would confirm them.

## Time limit and incomplete results

When the call hits its time limit it still returns: finished rows are
valid, rows listed in `not_completed` have no verdict, and
`time_limit_reached` is true. Never report the missing ones as passed.
Offer a rerun with a larger `time_limit`, fewer columns or a narrower
`x_range`. A large time tolerance on a long, nearly noise-free signal is the
usual cause of slow comparisons.

## What a result cannot tell you

- A pass means "inside this tube", nothing more. If the tolerance was
  picked without a requirement behind it, say so; a pass is not proof that
  a model is correct.
- The reference may itself be wrong or not a measurement (a model run, an
  analysis, an earlier version). Name what it is.
- Only the compared columns, window and tolerance sets were checked.
- A failure locates differences; it does not explain their cause.

## Answer template

> **Verdict:** `<column>` fails/passes against `<reference>` with
> `<tolerances in the user's units>`.
> **How much:** `<n>` of `<N>` points (`<share>` of the time) lie outside.
> **Where and which way:** mostly `<interval(s) with times>`, test
> `<above/below>` the reference by up to `<size in units>`.
> **How far from passing:** passes at `<looser set>`, not at `<agreed set>`.
> **Likely meaning:** `<hypothesis>`.
> **Not checked:** `<columns, window, caveats about the reference>`.

Example, from the worked forecast comparison on the bundled weather file
(`examples/open-meteo/stockholm-2026-11-05-to-19.csv`;
[Weather data by Open-Meteo.com](https://open-meteo.com/),
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)):

> The day-3 forecast fails against the latest model run with ±2 °C and
> ±3 h: 14 of 360 hourly points (3.9 % of the time) lie outside. The misses
> are on 16 November (forecast too warm, up to 0.7 °C beyond the band) and
> in the early hours of 19 November (too cold, up to 0.9 °C beyond the
> band). It passes with ±3 °C and ±3 h. The reference is a model run, not a
> measurement, so this says how much the forecast changed, not how good it
> was.
