# Spec Delta

## MODIFIED Requirements

### Requirement: One row per column and tolerance set

The result SHALL contain one row per (column, tolerance set) whose comparison
completed, with the column, the set label, a verdict (`pass`, `fail` or
`error`), the library status code and name and the number of judged points;
failing rows add the points outside the tube, the fractions of points and of
span outside, the worst deviation and the number of intervals. Comparisons
stopped by the time limit SHALL have no row and SHALL be listed as not
completed instead.

#### Scenario: Failing column
- **WHEN** a column fails
- **THEN** its row has verdict `fail`, status `-1` named `FAIL`, a non-zero
  count of points outside and the worst deviation with its time and tube
  half-width

#### Scenario: Passing column
- **WHEN** a column passes
- **THEN** its row carries the verdict, status and judged-point count only

#### Scenario: All comparisons complete
- **WHEN** every comparison finishes within the time limit
- **THEN** there is one row per (column, tolerance set) and the result
  contains no not-completed list

## ADDED Requirements

### Requirement: compare_signals time limit

`compare_signals` SHALL accept a time limit in seconds, 60 by default,
which MUST be positive and finite: a deadline for the whole call, counted
from its start, so the time spent reading the files counts against it.
Comparisons SHALL be started only while time remains, and a running
comparison SHALL be stopped when the limit is reached. Reading the files is
not interrupted, so a call can exceed the limit by the time spent reading.

#### Scenario: Default limit
- **WHEN** an agent calls `compare_signals` without a time limit
- **THEN** the comparisons are limited to 60 seconds in total

#### Scenario: Invalid limit
- **WHEN** an agent passes a time limit of 0 or a negative number
- **THEN** the call fails with an argument validation error

### Requirement: Time limit described as a deadline for the call

The descriptions of the `time_limit` argument and of the `compare_signals`
and `plot_signals` tools SHALL state that the limit counts from the start
of the call and includes reading the files (and, for `plot_signals`,
rendering).

#### Scenario: Agent reads the argument description
- **WHEN** an MCP client lists the tools
- **THEN** the `time_limit` description of both tools says the deadline
  counts from the start of the call and includes reading the files

### Requirement: Partial results on timeout

When the time limit stops `compare_signals`, the call SHALL still succeed and
return the rows of the comparisons that completed, the number of comparisons
not completed, the (column, tolerance set) pairs not completed (capped like
the rows), a flag that the limit was reached and a note suggesting a larger
time limit, fewer columns or a narrower x-range. The text SHALL say so too.

#### Scenario: Tiny time limit
- **WHEN** a fast column `a` and a column `b` whose comparison takes seconds
  are compared with a time limit of 0.3 s
- **THEN** the call succeeds, `a` has its normal row, `b` is listed as not
  completed with its tolerance set, the totals count one comparison not
  completed and the result says the time limit was reached

#### Scenario: Snippet with partial results
- **WHEN** the same call requests a snippet
- **THEN** the snippet reproduces only the completed rows

### Requirement: Server stays responsive during comparisons

The server SHALL run comparisons outside its message loop and without holding
the Python interpreter lock, so it keeps reading and answering messages while
a comparison runs.

#### Scenario: Request during a long comparison
- **WHEN** a `compare_signals` call with a comparison that takes seconds is
  running and the client sends a `tools/list` request on the same session
- **THEN** the server answers `tools/list` before the comparison finishes

### Requirement: Protocol cancellation stops the comparison

When the client sends the protocol's cancellation notification for a running
`compare_signals` or `plot_signals` call, the server SHALL stop the running
comparison promptly and SHALL NOT start further comparisons for that call.

#### Scenario: Client cancels a slow call
- **WHEN** a client cancels a `compare_signals` call whose comparison would
  take seconds
- **THEN** the comparison stops within a fraction of a second and the server
  goes on serving further calls
