## MODIFIED Requirements

### Requirement: Explicit tolerance sets resolved by the library

`compare_signals` SHALL accept zero or more tolerance sets, each with an optional
unique label and any of the six coefficients `atolx`, `atoly`, `ltolx`, `ltoly`,
`rtolx`, `rtoly`. The server SHALL pass the given coefficients unchanged to the
library, which resolves omitted ones; each set's six resolved values SHALL be
echoed. No sets means one set with nothing given.

#### Scenario: Only a y tolerance
- **WHEN** an agent passes one set `{"label": "y1pct", "rtoly": 0.01}`
- **THEN** the echoed resolved values are `rtoly = 0.01`, `atoly = ltoly = 0`
  and `atolx = ltolx = rtolx = 0` (no time tolerance), as the library resolves
  them

#### Scenario: No tolerance set
- **WHEN** an agent passes no tolerance set
- **THEN** the single set's echoed resolved values are `rtoly = 0.002` and every
  other coefficient `0`

#### Scenario: Several sets in one call
- **WHEN** an agent passes the sets `strict` and `loose` and three columns are
  compared
- **THEN** the result contains six rows, one per (column, set)

#### Scenario: Unknown coefficient name
- **WHEN** a tolerance set contains the key `rtol_y`
- **THEN** the call fails with an argument validation error

#### Scenario: Duplicate labels
- **WHEN** two tolerance sets carry the same label
- **THEN** the call fails with an error naming the duplicate label

## ADDED Requirements

### Requirement: Descriptions state that there is no default time tolerance

The `compare_signals` description and the server instructions SHALL state that
there is no time tolerance unless an x coefficient is given. The description
SHALL also say that a slightly shifted steep edge then fails, and that the x
half-width is then the `1e-10` floor.

#### Scenario: Agent learns the x default
- **WHEN** an agent reads the `compare_signals` description or the server
  instructions
- **THEN** it finds that there is no time tolerance unless an x coefficient is
  given, and that a slightly shifted steep edge then fails

### Requirement: Hint when a failure had no x tolerance

When at least one row of a `compare_signals` result has verdict fail and no x
coefficient (`atolx`, `ltolx`, `rtolx`) was given for it, neither in its
tolerance set nor in a per-column override, the result SHALL contain exactly
one note giving the number of such rows and suggesting an x tolerance (such as
`atolx`) if the test may be shifted or delayed in time. Otherwise no such note
SHALL appear.

#### Scenario: Shifted edge with no x coefficient
- **WHEN** a column whose test step is slightly delayed fails with a set that
  gives only `atoly`
- **THEN** the notes contain one hint saying 1 failing row had no x (time)
  tolerance and suggesting `atolx`

#### Scenario: Explicit zero x tolerance
- **WHEN** the same column fails with a set that gives `atolx = 0` and `atoly`
- **THEN** no such hint appears

#### Scenario: Only passing rows
- **WHEN** every compared row passes
- **THEN** no such hint appears
