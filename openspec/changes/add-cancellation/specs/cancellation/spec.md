# Spec Delta

## Purpose

Lets a caller stop a running comparison, on request or after a time limit,
in the Rust core and the Python binding, and defines what a stopped
comparison reports.

## ADDED Requirements

### Requirement: Cancellable comparison in the Rust core

The Rust core SHALL offer a comparison that takes a cancellation signal: a
flag that any thread can set, an optional deadline, or a caller-supplied
check, consulted at checkpoints throughout the comparison.

#### Scenario: Flag set from another thread
- **WHEN** a comparison of an input that takes seconds is running and another
  thread sets its cancellation flag
- **THEN** the comparison returns well under a second later, reporting that
  it was cancelled on request

### Requirement: Bounded work after the signal fires

The signal SHALL be consulted before the work starts, between the phases
of the comparison and, inside every phase whose cost grows with the input,
after a bounded amount of work, so that the work done after the signal
fires does not grow with the input length. Only input validation, whose
status takes precedence over cancellation, MAY run before the first check.

#### Scenario: Checks inside the linear phases
- **WHEN** a comparison of a smooth input without loops to remove runs with
  a caller-supplied check
- **THEN** the check is called repeatedly within each linear pass (about
  once per fixed number of elements, not only at phase boundaries), and a
  check that returns an error at any of these calls stops the comparison
  with that error

#### Scenario: Deadline
- **WHEN** a comparison is given a deadline 50 ms in the future and the input
  would take seconds
- **THEN** it returns shortly after the deadline, reporting that the deadline
  was exceeded

#### Scenario: Deadline already passed
- **WHEN** a comparison is given a deadline in the past
- **THEN** it reports that the deadline was exceeded without doing the
  comparison

### Requirement: Cancellation is reported distinctly from verdicts

A cancelled comparison SHALL NOT return a status or partial bounds; it SHALL
report cancellation as a separate outcome that says whether it was requested
or the deadline was exceeded. The existing status codes SHALL stay unchanged.
Input validation SHALL take precedence: invalid input reports its status even
when the signal has fired.

#### Scenario: Cancelled outcome
- **WHEN** a cancellable comparison is cancelled
- **THEN** the caller receives a cancelled outcome naming the reason, and no
  status code

#### Scenario: Invalid input with a fired signal
- **WHEN** a comparison with mismatched array lengths is given a flag that is
  already set
- **THEN** it reports the length-mismatch status

### Requirement: Comparisons without a signal are unchanged

The existing comparison functions SHALL behave exactly as before: identical
results bit for bit, and no measurable slowdown. A cancellable comparison
whose signal never fires SHALL return exactly the same result as the plain
comparison.

#### Scenario: Same result with an unfired signal
- **WHEN** the same input is compared with the plain function and with a
  cancellable comparison whose signal never fires
- **THEN** the status, bounds and deviations are bit-identical

### Requirement: Python comparison releases the interpreter lock

The Python `compare` SHALL release the interpreter lock while the comparison
runs, so other Python threads make progress, and its results SHALL equal
those of the Rust core.

#### Scenario: Another thread runs during a comparison
- **WHEN** one Python thread runs a comparison that takes about a second and
  another thread increments a counter in a loop meanwhile
- **THEN** the counter advances many times before the comparison returns

### Requirement: Python time limit and cross-thread cancellation

The Python `compare` and `compare_dataframes` SHALL accept an optional time
limit in seconds and an optional cancellation token whose `cancel()` may be
called from any thread. A time limit SHALL raise `ComparisonTimeout`; a
cancelled token SHALL raise `ComparisonCancelled`, of which
`ComparisonTimeout` is a subclass. A negative or non-finite time limit SHALL
raise `ValueError`.

#### Scenario: Time limit exceeded
- **WHEN** `compare` is called with `timeout=0.05` on an input that takes
  seconds
- **THEN** it raises `ComparisonTimeout` shortly after 0.05 s

#### Scenario: Cancelled from another thread
- **WHEN** a thread calls `token.cancel()` while another thread runs
  `compare(..., cancel=token)` on a slow input
- **THEN** that `compare` raises `ComparisonCancelled` promptly

#### Scenario: Token already cancelled
- **WHEN** `compare` is called with a token on which `cancel()` was already
  called
- **THEN** it raises `ComparisonCancelled` without comparing

#### Scenario: Generous limit
- **WHEN** `compare` is called with a time limit far longer than the
  comparison takes
- **THEN** the result equals the result without a time limit

### Requirement: Timeout messages name the caller's limit

A time limit counts from the start of the call, so the copy of the input
arrays the binding makes before the comparison starts (which the limit
cannot interrupt) counts against it. The message of a `ComparisonTimeout` SHALL name the time limit the caller
passed; for `compare_dataframes` that is the limit of the whole call, not
the time that was left for the column that exceeded it.

#### Scenario: compare_dataframes names the caller's limit
- **WHEN** `compare_dataframes` is called with `timeout=0.2` and its second
  column cannot finish in time
- **THEN** the `ComparisonTimeout` message names the column and the time
  limit of 0.2 s

### Requirement: Ctrl-C interrupts a Python comparison

While a comparison runs in the Python main thread, a SIGINT (Ctrl-C) SHALL
stop it promptly and raise `KeyboardInterrupt`, or whatever the installed
SIGINT handler raises.

#### Scenario: Ctrl-C during a long comparison
- **WHEN** a Python process running a comparison that takes seconds in its
  main thread receives SIGINT
- **THEN** `compare` raises `KeyboardInterrupt` within a fraction of a second
