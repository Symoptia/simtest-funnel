## MODIFIED Requirements

### Requirement: Output path safety

A relative output path SHALL be resolved against the first workspace root,
else the first configured output directory. The output path SHALL be refused
when its resolved location (directory and any symbolic link resolved) is
outside the allowed directories; when its directory does not exist (no
directory is created); or when it exists and is not a regular file. All
output path checks SHALL happen before any CSV file is read.

#### Scenario: Outside the roots
- **WHEN** the client declares the root `/work/project` and the output path is
  `/tmp/z.svg`
- **THEN** the call fails with an error naming the path and the roots, and
  nothing is written

#### Scenario: Missing directory
- **WHEN** the output path's directory does not exist
- **THEN** the call fails with an error naming the directory and no directory
  is created

#### Scenario: Directory replaced by a symbolic link during the call
- **WHEN** the output directory inside a root (or a directory above it) is
  replaced by a symbolic link to a directory outside the roots after the
  output path was checked and before the file is written
- **THEN** the call fails and nothing is written outside the roots

#### Scenario: Existing file replaced by a symbolic link during the call
- **WHEN** with `overwrite` true the existing output file is replaced by a
  symbolic link to a file outside the roots during the call
- **THEN** the link is replaced by the new plot inside the root and the file
  it pointed to is unchanged

### Requirement: Existing files are kept unless overwrite is requested

An existing output file SHALL be refused unless `overwrite` is true, in
which case it SHALL be replaced. A refused or failed call SHALL leave the
file system unchanged.

#### Scenario: Existing file without overwrite
- **WHEN** the output path names an existing file and `overwrite` is false
- **THEN** the call fails with an error suggesting `overwrite=true` and the
  file is unchanged

#### Scenario: Existing file with overwrite
- **WHEN** the same call is made with `overwrite` true
- **THEN** the file is replaced by the new plot

#### Scenario: File created during the call
- **WHEN** `overwrite` is false and another process creates the output file
  after the output path was checked
- **THEN** the call fails with an error suggesting `overwrite=true`, that
  file is unchanged and no temporary file is left behind

## ADDED Requirements

### Requirement: Plot write does not trust the checked path

Because the file is written only after reading, comparing and rendering, the
write SHALL NOT trust the checked output path. On platforms that support it,
the file SHALL be written relative to a handle of the target directory that is
opened without following a symbolic link and verified to lie inside the
allowed directories immediately before the file is put in place, and a
symbolic link at the file name SHALL be replaced, never followed.

#### Scenario: Directory handle verified before the write
- **WHEN** a plot file is written on a platform that supports directory handles
- **THEN** the target directory is opened without following a symbolic link
  and verified to lie inside the allowed directories immediately before the
  file is put in place

#### Scenario: Symbolic link at the file name
- **WHEN** the output name is a symbolic link when the file is put in place
  and `overwrite` is true
- **THEN** the link itself is replaced by the plot and its target is not
  written

### Requirement: Output directory re-checked on other platforms

On platforms without such directory handles, the output directory SHALL be
resolved and checked against the allowed directories again immediately before
the write.

#### Scenario: Directory moved outside the roots before the write
- **WHEN** on such a platform the output directory resolves outside the
  allowed directories at the time of the write
- **THEN** the call fails and nothing is written

### Requirement: Reported plot path

The path reported in the result SHALL be where the file was written.

#### Scenario: Relative output path
- **WHEN** an agent passes a relative output path that is written inside the
  first workspace root
- **THEN** the result reports the resolved path of the written file

### Requirement: Plot file put in place in one step

The plot SHALL be written to a temporary file in the target directory and put
in place under the output name in one step: with `overwrite` by an atomic
replacement, otherwise by an operation that fails if the name exists. No
partial file SHALL ever appear under the output name, and a file created by
someone else meanwhile SHALL never be replaced without `overwrite`.

#### Scenario: No partial file under the output name
- **WHEN** a plot file is being written
- **THEN** the output name holds either nothing or the previous file until the
  complete plot replaces it in one step

#### Scenario: Temporary file removed on failure
- **WHEN** putting the plot in place fails
- **THEN** no temporary file is left in the target directory

### Requirement: Plot result reports a missing x tolerance

When the comparison behind a plot fails and no x coefficient (`atolx`, `ltolx`,
`rtolx`) was given in its tolerance set, the plot result SHALL carry the same
hint note that `compare_signals` gives for such a row.

#### Scenario: Failing plot without an x coefficient
- **WHEN** an agent plots a column whose test step is slightly delayed with a
  tolerance set that gives only `atoly`, and the comparison fails
- **THEN** the result's notes contain the hint suggesting an x tolerance

#### Scenario: Failing plot with an x coefficient
- **WHEN** the same column is plotted with `atolx` given and still fails
- **THEN** the result contains no such hint
