# Spec Delta

## MODIFIED Requirements

### Requirement: Plot tool on the local server

The local MCP server SHALL offer a tool `plot_signals` in addition to its
existing tools, which stay unchanged. It SHALL take a reference path, a test
path, exactly one signal column name, at most one tolerance set, an optional
x-range, an optional output path, an `overwrite` flag, a cap on listed
intervals and a time limit, with the names and shapes `compare_signals` uses
for the same meaning.

#### Scenario: Client lists the tools
- **WHEN** an MCP client lists the server's tools
- **THEN** the list contains `describe_signals`, `compare_signals` and
  `plot_signals`, and the arguments of `describe_signals` are unchanged

#### Scenario: Glob pattern instead of a column name
- **WHEN** an agent calls `plot_signals` with column `"*"` and no column has
  that name
- **THEN** the call fails with an error saying one exact column name is needed

### Requirement: Output path safety

A relative output path SHALL be resolved against the first workspace root,
else the first configured output directory. The output path SHALL be refused
when its resolved location (directory and any symbolic link resolved) is
outside the allowed directories; when its directory does not exist (no
directory is created); or when it exists and is not a regular file. All
output path checks SHALL happen before any CSV file is read. Because the
file is written only after reading, comparing and rendering, the write
SHALL NOT trust the checked path: on platforms that support it, the file
SHALL be written relative to a handle of the target directory that is
opened without following a symbolic link and verified to lie inside the
allowed directories immediately before the file is put in place, and a
symbolic link at the file name SHALL be replaced, never followed. On other
platforms the directory SHALL be resolved and checked again immediately
before the write. The path reported in the result SHALL be where the file
was written.

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
file system unchanged. The plot SHALL be written to a temporary file in the
target directory and put in place under the output name in one step (with
`overwrite` by an atomic replacement, otherwise by an operation that fails
if the name exists), so no partial file ever appears under the output name
and a file created by someone else meanwhile is never replaced without
`overwrite`.

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

### Requirement: Plot time limit

`plot_signals` SHALL accept the same time limit as `compare_signals` (seconds,
60 by default, positive and finite), counted from the start of the call.
A plot is one comparison, so when the limit stops it the call SHALL fail
with an error saying the comparison did not finish within the limit and
suggesting a larger limit or a narrower x-range, and SHALL write no file.

#### Scenario: Comparison exceeds the limit
- **WHEN** an agent plots a column whose comparison takes seconds with a time
  limit of 0.2 s and an output path
- **THEN** the call fails with an error naming the time limit, and no file is
  written

#### Scenario: Comparison within the limit
- **WHEN** the comparison finishes within the time limit
- **THEN** the plot is produced exactly as without a time limit

### Requirement: Plot time limit covers rendering

The plot time limit SHALL cover reading the files, the comparison and
rendering. Reading and rendering are not interrupted, but the limit SHALL
be checked before rendering and again immediately before the file is put
in place; when it has passed, the call SHALL fail with an error naming the
limit and write no file.

#### Scenario: Limit passes while rendering
- **WHEN** the time limit passes while the plot file is being rendered
- **THEN** the call fails with an error naming the time limit, and neither
  the file nor a temporary file is left in the target directory

### Requirement: A cancelled plot writes nothing

When a `plot_signals` call is cancelled, no file SHALL be written for it,
also when the cancellation arrives after the comparison finished: the
cancellation SHALL be checked before rendering and immediately before the
file is put in place, ordered against putting it in place so that the file
either appears before the call is reported cancelled or never.

#### Scenario: Cancelled while rendering
- **WHEN** the client cancels a `plot_signals` call with an output path
  while its plot is being rendered
- **THEN** the call is reported cancelled at once, and after the abandoned
  work has finished no file (and no partial or temporary file) exists in the
  target directory
