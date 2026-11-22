# Worked example: was the forecast close enough?

A complete comparison on the weather sample bundled with simtest-funnel,
`examples/open-meteo/stockholm-2026-11-05-to-19.csv` (relative to a
checkout; use its absolute path). The sample is not part of this skill.

[Weather data by Open-Meteo.com](https://open-meteo.com/), licensed
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), not modified;
see the sample's
[ATTRIBUTION.md](https://github.com/Symoptia/simtest-funnel/blob/main/examples/open-meteo/ATTRIBUTION.md).

## Contents

- [The question](#the-question)
- [1. Describe](#1-describe)
- [2. Choose tolerances](#2-choose-tolerances)
- [3. Compare](#3-compare)
- [4. How far from passing, and where](#4-how-far-from-passing-and-where)
- [5. A picture, because the user asked](#5-a-picture-because-the-user-asked)
- [6. The answer](#6-the-answer)
- [What this example cannot tell you](#what-this-example-cannot-tell-you)

## The question

> Was the forecast made three days ahead within 2 °C and 3 hours of the
> latest run? And the day-1 and day-5 ones?

The file is an Open-Meteo Previous Runs response: Stockholm, 15 days
hourly, the latest model run (`temperature_2m (°C)`) next to the forecasts
made 1, 3 and 5 days before for the same hours.

## 1. Describe

```jsonc
// describe_signals
{"path": "examples/open-meteo/stockholm-2026-11-05-to-19.csv", "header_line": 4}
```

The file starts with three lines of metadata, so the header is on line 4
(a first describe without `header_line` would say so). Result: 360 rows; a
date-time time column without time zone (read as UTC; the response is in
GMT), 2026-11-05T00:00 to 2026-11-19T23:00, uniform hourly steps; four
columns, the latest run ranging from -0.8 to 8.8 °C.

What this decides: all four columns are in one file, so the comparison
needs `pairs` and no `test_path`; the time axis is date-time, so 3 hours is
`atolx` 10800.

## 2. Choose tolerances

The user gave both numbers: `atoly` 2 (°C, absolute, because the user
stated an accuracy in the signal's unit) and `atolx` 10800. Adding the
same set without the time tolerance shows how much of the miss is timing.

## 3. Compare

```jsonc
// compare_signals
{
  "reference_path": "examples/open-meteo/stockholm-2026-11-05-to-19.csv",
  "header_line": 4,
  "pairs": [
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day1 (°C)", "label": "day1"},
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day3 (°C)", "label": "day3"},
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day5 (°C)", "label": "day5"}
  ],
  "tolerances": [
    {"label": "2C", "atoly": 2},
    {"label": "2C_3h", "atoly": 2, "atolx": 10800}
  ]
}
```

Points outside the tube (of 360):

| Forecast | ±2 °C | ±2 °C and ±3 h |
| --- | --- | --- |
| `day1` | pass, 0 of 360 | pass, 0 of 360 |
| `day3` | fail, 38 of 360 | fail, 14 of 360 |
| `day5` | fail, 84 of 360 | fail, 47 of 360 |

Reading it: the time tolerance removes about two thirds of the day-3
misses (38 to 14) and almost half of the day-5 misses (84 to 47), so part
of the error is timing (warming or cooling a few hours early or late), the
rest is level. For `day3` with ±2 °C and ±3 h the intervals are 19 November
00:00 to 05:00 (below the tube, worst -0.9 °C beyond it) and 16 November
15:00 to 20:00 and 04:00 to 05:00 (above, worst +0.7 °C).

## 4. How far from passing, and where

A sweep of the value tolerance with the time tolerance kept:

```jsonc
// compare_signals
{
  "reference_path": "examples/open-meteo/stockholm-2026-11-05-to-19.csv",
  "header_line": 4,
  "pairs": [
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day3 (°C)", "label": "day3"}
  ],
  "tolerances": [
    {"label": "2C_3h", "atoly": 2, "atolx": 10800},
    {"label": "3C_3h", "atoly": 3, "atolx": 10800},
    {"label": "4C_3h", "atoly": 4, "atolx": 10800}
  ]
}
```

`day3` fails at 2 °C and passes at 3 °C and 4 °C (always with ±3 h): it
needs between 2 and 3 °C. And the first ten days alone:

```jsonc
// compare_signals
{
  "reference_path": "examples/open-meteo/stockholm-2026-11-05-to-19.csv",
  "header_line": 4,
  "pairs": [
    {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day3 (°C)", "label": "day3"}
  ],
  "tolerances": [{"label": "2C_3h", "atoly": 2, "atolx": 10800}],
  "x_range": {"lo": "2026-11-05T00:00", "hi": "2026-11-15T00:00"}
}
```

It passes there: every miss is from 16 November on. Report that as where
the forecast went wrong, not as a pass.

## 5. A picture, because the user asked

"Show me where day 3 goes wrong" is a reason to plot one row:

```jsonc
// plot_signals
{
  "reference_path": "examples/open-meteo/stockholm-2026-11-05-to-19.csv",
  "header_line": 4,
  "column": "temperature_2m (°C)",
  "test_column": "temperature_2m_previous_day3 (°C)",
  "tolerance": {"label": "2C_3h", "atoly": 2, "atolx": 10800}
}
```

The inline preview shows the three shaded regions. Add `output_path` (an
`.svg` inside the project) only if the user wants a file. Day 1 passes, so
it needs no picture.

## 6. The answer

> Day 1 is within 2 °C of the latest run at every hour. Day 3 is not: with
> ±2 °C and ±3 h, 14 of 360 hours (3.9 %) are outside, on 16 November (the
> forecast was too warm, up to 0.7 °C beyond the band) and early on 19
> November (too cold, up to 0.9 °C beyond the band); it would pass with
> ±3 °C. Day 5 misses 47 hours (13.1 %) even with the time tolerance, mostly
> too warm, up to 2.4 °C beyond the band on the evening of 16 November.

## What this example cannot tell you

- The "latest run" is the newest model run or analysis, not a measured
  temperature. The comparison says how much the forecast changed between
  runs, not how good it was.
- Two weeks of one city say nothing general about forecast quality.
- ±2 °C and ±3 h are the user's choice. A pass under them is a statement
  about that tube, not a quality grade.
