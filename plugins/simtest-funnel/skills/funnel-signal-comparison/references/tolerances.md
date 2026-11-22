# Choosing tolerances

How to turn what a user says into tolerance coefficients. What each
coefficient does and how the server combines them is in the
`compare_signals` tool description; this file is about which to pick.

The example calls use files from a simtest-funnel checkout
(`examples/web/public/`: 1001 samples, time 0 to 1, columns `x`, `y`, `z`
with range about 2). Use absolute paths in real calls.

## Contents

- [From the user's words to coefficients](#from-the-users-words-to-coefficients)
- [Time tolerance](#time-tolerance)
- [Sweeps and strict-and-loose pairs](#sweeps-and-strict-and-loose-pairs)
- [Value or timing?](#value-or-timing)
- [Different tolerances per column](#different-tolerances-per-column)
- [Pitfalls](#pitfalls)

## From the user's words to coefficients

| The user says | Tolerance set | Note |
| --- | --- | --- |
| "within 0.5 bar" | `{"atoly": 0.5}` | Absolute, in the column's unit |
| "within 2 °C and 3 hours" (date-time axis) | `{"atoly": 2, "atolx": 10800}` | Hours become seconds |
| "within 1 % of the range" | `{"rtoly": 0.01}` | Band constant over time |
| "within 1 % of the value" | `{"ltoly": 0.01}` | Band follows the reference |
| "5 % of the value, but at least 0.1" | `{"ltoly": 0.05, "atoly": 0.1}` | The larger band applies |
| "allow one sample of delay" | `{"atoly": 0.01, "atolx": 0.001}` | `atolx` = the median step from describe (0.001 here) |
| "up to 15 minutes late" (date-time axis) | `{"atoly": 0.5, "atolx": 900}` | The value part still has to be chosen |
| "identical up to solver noise" | `{"rtoly": 0.0001}` | Say that you picked 0.01 % of the range |
| "1 %" with no further context | ask | Range or value? It can change the verdict |

When no number is given, state the domain reason for the one you choose:
an instrument's accuracy, a requirement, a typical modelling error, or "a
tolerance that only flags differences you would notice in a plot". Keep the
explanation to one sentence and offer to change it.

## Time tolerance

- Zero is the default, and zero means a signal that is right but shifted by
  even one sample fails at every steep edge. Slowly varying signals barely
  notice; steps and switching signals fail badly.
- Give one when the cause of a shift is acceptable: different solver steps
  or output intervals, sampled controllers, event detection, forecast
  timing. Size it from that cause: one or two sample steps, the controller
  period, "a few hours".
- Keep it well below the shortest feature you care about. A time tolerance
  near an oscillation's period lets a different frequency pass (see
  [Value or timing?](#value-or-timing)).
- Prefer `atolx`. A relative time tolerance grows with the length of the
  record, so the same coefficient means something else on a longer file.
- On a date-time time axis every time quantity is seconds:

  | Duration | Seconds |
  | --- | --- |
  | 1 minute | 60 |
  | 15 minutes | 900 |
  | 1 hour | 3600 |
  | 3 hours | 10800 |
  | 1 day | 86400 |

## Sweeps and strict-and-loose pairs

"Which of 1 %, 2 % and 5 % does it meet?" is one call with three labelled
sets:

```jsonc
// compare_signals
{
  "reference_path": "examples/web/public/reference.csv",
  "test_path": "examples/web/public/test.csv",
  "columns": ["x"],
  "tolerances": [
    {"label": "1pct", "rtoly": 0.01},
    {"label": "2pct", "rtoly": 0.02},
    {"label": "5pct", "rtoly": 0.05}
  ]
}
```

Result: `x` fails at 1 % (730 of 1001 points outside) and 2 % (410 of
1001), and passes at 5 %. Answer with the tightest passing set: "`x` meets
5 % of its range but not 2 %."

A sweep brackets the needed tolerance; it does not find it exactly. If the
user needs a sharper number, add values between the last failing and the
first passing set in one more call. Sweep one coefficient at a time, so the
answer stays readable.

## Value or timing?

The same value tolerance with and without a time tolerance separates level
errors from timing errors:

```jsonc
// compare_signals
{
  "reference_path": "examples/web/public/reference.csv",
  "test_path": "examples/web/public/test.csv",
  "tolerances": [
    {"label": "tight", "atoly": 0.1},
    {"label": "tight_t", "atoly": 0.1, "atolx": 0.1}
  ]
}
```

Result: `x` passes both. `z` fails both (884 of 1001 points outside without
the time tolerance, 338 with it), so it differs in level, not just timing.
`y` fails without the time tolerance (804 of 1001 outside) and passes with
it, but that pass is a warning sign rather than good news: `y` oscillates
with a period of about 0.06, shorter than the 0.1 time tolerance, so the
tube no longer sees that test and reference have different frequencies.
When a time tolerance turns a failure into a pass, check that it is small
compared to the features that matter before you report the pass.

## Different tolerances per column

Columns with different units or accuracies need different values. Keep one
labelled set for the common case and override single columns, axis by axis,
with `column_tolerances`:

```jsonc
// compare_signals
{
  "reference_path": "examples/web/public/reference.csv",
  "test_path": "examples/web/public/test.csv",
  "tolerances": [{"label": "spec", "atoly": 0.1, "atolx": 0.01}],
  "column_tolerances": {"z": {"atoly": 1.0}}
}
```

Here `z` keeps the time tolerance of the set and gets its own value band.
Mention every override in the answer; a pass under a column-specific
tolerance is easy to misread as a pass under the common one.

## Pitfalls

- **Range-relative bands shrink in a window.** With `x_range` the range of
  the reference inside the window is the base, so `rtoly` gets stricter when
  you zoom into a quiet stretch. Use `atoly` when comparing windows if the
  band should stay the same.
- **Constant references.** `rtoly` on a constant signal leaves almost no
  band. Give `atoly`.
- **Zero crossings.** `ltoly` alone gives no band where the reference is
  zero. Add an `atoly` floor.
- **Relative time tolerance on date-time axes.** The local-relative one is
  refused there; the range-relative one grows with the record. Use `atolx`.
- **Default tolerance.** Omitting `tolerances` gives a small range-relative
  value band and no time tolerance. If you use it, say so as you would any
  other choice.
- **Tightening after the fact.** Choosing the tolerance after seeing which
  one passes is fine for describing a difference ("it needs 3 °C"), not for
  declaring a pass. Keep the agreed tolerance as the verdict.
