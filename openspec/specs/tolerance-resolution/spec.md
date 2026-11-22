# tolerance-resolution Specification

## Purpose
Defines how default and partially specified tolerances are resolved into
the six effective coefficients (`atolx`, `atoly`, `ltolx`, `ltoly`,
`rtolx`, `rtoly`), so that identical inputs give identical verdicts in
the Rust, Python, TypeScript and command-line interfaces.

## Requirements

### Requirement: Default tolerances
When no tolerance coefficient is given at all, the comparison SHALL use
`rtoly = 2e-3` with `atolx`, `atoly`, `ltolx`, `ltoly` and `rtolx` equal
to zero, so there is no tolerance in x. Omitting the options entirely,
or giving options without tolerances, SHALL be equivalent to giving no
coefficient. Zero x tolerance SHALL mean the x half-width is the
minimum half-width floor, so a test point is judged only against the y
band around the reference at the same x.

#### Scenario: Options omitted
- **WHEN** a comparison is run without options in any interface
- **THEN** the effective tolerances are `rtoly = 2e-3` and every other coefficient is `0`

#### Scenario: Options given without tolerances
- **WHEN** a comparison is run with options that set only an x-range
- **THEN** the effective tolerances are `rtoly = 2e-3` and every other coefficient is `0`

#### Scenario: Reported defaults agree with behaviour
- **WHEN** a caller reads the default options reported by an interface and passes them back explicitly
- **THEN** the comparison verdict and bounds are identical to running with options omitted

#### Scenario: Time-shifted steep edge with default tolerances
- **WHEN** the test is the reference's steep step delayed by a small fraction of the x range (a step from 0 to 1 over x 0.49 to 0.50 on x 0 to 1, delayed by 0.001) and options are omitted
- **THEN** the status is fail

#### Scenario: Time-shifted steep edge with an explicit x tolerance
- **WHEN** the same trajectories are compared with `atolx = 0.002` (or `rtolx = 2e-3`) given
- **THEN** the status is pass

### Requirement: Per-axis resolution
Tolerances SHALL be resolved independently for the x axis (`atolx`,
`ltolx`, `rtolx`) and the y axis (`atoly`, `ltoly`, `rtoly`). An axis
for which no coefficient is given SHALL receive the default for that
axis. An axis for which at least one coefficient is given SHALL use the
given coefficients and zero for the coefficients of that axis that are
not given.

#### Scenario: Only a y coefficient given
- **WHEN** a caller gives only `atoly = 0.05`
- **THEN** the effective tolerances are `atoly = 0.05` and every other coefficient is `0`

#### Scenario: Only an x coefficient given
- **WHEN** a caller gives only `ltolx = 0.01`
- **THEN** the effective tolerances are `atolx = 0`, `ltolx = 0.01`, `rtolx = 0`, `atoly = 0`, `ltoly = 0`, `rtoly = 2e-3`

#### Scenario: One coefficient on each axis
- **WHEN** a caller gives `atolx = 0.1` and `atoly = 0.1`
- **THEN** the effective tolerances are `atolx = 0.1`, `atoly = 0.1` and every other coefficient is `0`

### Requirement: Explicit zero counts as given
A coefficient given with the value zero SHALL count as given for the
purpose of per-axis resolution, so that zero tolerance on an axis
remains expressible. A coefficient that is omitted, or given as the
language's null value (`None` in Python, `null`/`undefined` in
JavaScript), SHALL count as not given.

#### Scenario: Explicit zero on the x axis
- **WHEN** a caller gives `atolx = 0` and `atoly = 0.05` and nothing else
- **THEN** the effective tolerances are `atoly = 0.05` and every other coefficient is `0`

#### Scenario: Null coefficient is absent
- **WHEN** a caller gives `atoly = 0.05` and gives `atolx` as `None` (Python) or `null` (JavaScript)
- **THEN** the effective tolerances equal those of giving only `atoly = 0.05`

### Requirement: Fully specified tolerances are unchanged
When all six coefficients are given, the comparison SHALL use exactly
the given values, with the same results as before this change.

#### Scenario: Six explicit coefficients
- **WHEN** a caller gives all six coefficients explicitly
- **THEN** the comparison bounds, errors and status are identical to those produced before this change for the same values

### Requirement: Identical resolution in every interface
The Rust library, the Python package, the TypeScript SDK and the
command-line tool SHALL resolve tolerances with the same rule and SHALL
produce the same effective tolerances and the same comparison status for
the same trajectories and the same set of given coefficients.

#### Scenario: Same partial specification everywhere
- **WHEN** the same trajectories are compared with only `atoly` given, once through each of the four interfaces
- **THEN** all four use the same six effective coefficients and report the same status

### Requirement: Command-line coefficient sources
The command-line tool SHALL take each coefficient from its flag when the
flag is present (including an explicit `0`), otherwise from the
parameter file when the file contains that key, and SHALL then resolve
the combined set of given coefficients with the per-axis rule. A key
absent from the parameter file SHALL count as not given. The tool's help
for the parameter file SHALL state that it uses the LBNL keys but that a
missing tolerance key is resolved per axis rather than meaning zero.

#### Scenario: Flag only on the y axis
- **WHEN** the tool is run with `--atoly 0.05` and no other tolerance flag or parameter file
- **THEN** it compares with `atoly = 0.05` and every other coefficient `0` (no x tolerance)

#### Scenario: Parameter file without tolerance keys
- **WHEN** the tool is run with a parameter file that names the trajectories but contains no tolerance keys, and no tolerance flags
- **THEN** it compares with the default tolerances

#### Scenario: Help explains parameter-file semantics
- **WHEN** a user reads the help for `--params`
- **THEN** it says the file has the LBNL keys and that a missing tolerance key is not zero but resolved per axis

#### Scenario: Flag and parameter file combined
- **WHEN** the parameter file gives `atolx = 0.1` and `atoly = 0.1` and the tool is run with `--rtoly 0.01`
- **THEN** it compares with `atolx = 0.1`, `atoly = 0.1`, `rtoly = 0.01` and every other coefficient `0`

### Requirement: Echoed tolerances are resolved
Any result that echoes the tolerances of a comparison, including the
violation summary, SHALL report the six effective coefficients after
resolution, never the partial input.

#### Scenario: Summary of a partially specified comparison
- **WHEN** a violation summary is produced for options that give only `atoly = 0.2`
- **THEN** the summary reports `atoly = 0.2` and every other coefficient `0`

#### Scenario: Summary with options omitted
- **WHEN** a violation summary is produced with options omitted
- **THEN** the summary reports `rtoly = 2e-3` and every other coefficient `0`
