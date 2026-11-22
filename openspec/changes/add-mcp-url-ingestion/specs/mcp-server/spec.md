# Spec Delta

## MODIFIED Requirements

### Requirement: Local stdio server distribution

The server SHALL be distributed as its own Python package, `simtest-funnel-mcp`,
whose console script of the same name starts an MCP server on the stdio
transport. The server SHALL expose the tools `describe_signals` and
`compare_signals`, both annotated as read-only and idempotent, and as
closed-world unless network access was enabled at start-up (`mcp-url-sources`),
in which case they are open-world. Other capabilities MAY add further tools
(for example the plot tool of `mcp-plots`).

#### Scenario: Client lists the tools
- **WHEN** an MCP client starts `simtest-funnel-mcp` as a subprocess, initializes
  a session over stdio and lists the tools
- **THEN** the list contains `describe_signals` and `compare_signals`, each
  marked read-only and closed-world

#### Scenario: Server started with network access
- **WHEN** the server was started with `--allow-network` and a client lists
  the tools
- **THEN** `describe_signals` and `compare_signals` are marked read-only and
  open-world

### Requirement: Stateless file access

Each tool call SHALL name the files it reads by path or URL; the server MUST
keep no state between calls except the URL cache of `mcp-url-sources` and MUST
NOT open network connections unless network access was enabled at start-up.
Apart from that cache, the only file the server writes is a requested plot file
(`mcp-plots`). A relative path SHALL be resolved against the first workspace
root when the client declares roots, otherwise against the server's working
directory.

#### Scenario: Same call twice
- **WHEN** an agent calls `describe_signals` twice with the same path and the file
  is unchanged
- **THEN** both calls return identical results and no file is created or modified

#### Scenario: Local files without network access
- **WHEN** the server was started without network access and an agent
  compares two local files
- **THEN** no network connection is opened and no file or directory is
  created

### Requirement: Workspace roots are honoured

When the client declares one or more `file://` workspace roots, the server SHALL
refuse to read any local path whose resolved location (symbolic links followed) is not
inside one of those roots. Only local `file://` roots (empty host or
`localhost`) SHALL be used, converted to local paths with the platform's URL
path rules; other roots SHALL be ignored with a note in the result. When the
client declares no usable roots, any readable path SHALL be accepted.

#### Scenario: Path outside the roots
- **WHEN** the client declares the root `/work/project` and an agent calls
  `describe_signals` with `/etc/hosts`
- **THEN** the call fails with an error that names the path and the declared roots

#### Scenario: Non-local root
- **WHEN** the client declares the root `file://fileserver/share`
- **THEN** that root is ignored and the result carries a note saying so

#### Scenario: No roots declared
- **WHEN** the client does not support roots and an agent passes an absolute path
  to a readable CSV file
- **THEN** the file is read

#### Scenario: URL with roots declared
- **WHEN** the client declares the root `/work/project`, network access is
  enabled and an agent passes an `https://` URL
- **THEN** the URL is fetched, not resolved against the root, and the result
  names the URL

### Requirement: compare_signals time limit

`compare_signals` SHALL accept a time limit in seconds, 60 by default,
which MUST be positive and finite: a deadline for the whole call, counted
from its start, so the time spent fetching and reading the files counts
against it. Comparisons SHALL be started only while time remains, and a running
comparison SHALL be stopped when the limit is reached, as SHALL a URL fetch.
Reading a file is not interrupted, so a call can exceed the limit by the
time spent reading.

#### Scenario: Default limit
- **WHEN** an agent calls `compare_signals` without a time limit
- **THEN** the comparisons are limited to 60 seconds in total

#### Scenario: Invalid limit
- **WHEN** an agent passes a time limit of 0 or a negative number
- **THEN** the call fails with an argument validation error

#### Scenario: Limit reached while fetching
- **WHEN** a URL input is still downloading when the time limit passes
- **THEN** the fetch is stopped and the call fails with an error naming the
  URL and the time limit

## ADDED Requirements

### Requirement: Snippet for URL inputs

For an input given as a URL, the snippet SHALL read a local copy at
`SIMTEST_FUNNEL_DATA_ROOT` / a file name derived from the URL, state the URL,
fetch time, size and SHA-256, and before comparing verify the copy's
SHA-256, failing when the copy is missing (naming the URL, the expected
file, the hash and `SIMTEST_FUNNEL_DOWNLOAD`) or differs (giving both
hashes). Without `SIMTEST_FUNNEL_DOWNLOAD=1` it SHALL NOT access the network.

#### Scenario: Vendored copy
- **WHEN** an agent requests a snippet for a comparison of a URL input, the
  fetched file is saved under the stated name in the data root and the
  snippet is run with pytest
- **THEN** every test case passes, reproducing the status codes in the result,
  and no connection is opened

#### Scenario: Copy missing in CI
- **WHEN** the same snippet runs where the copy is missing and
  `SIMTEST_FUNNEL_DOWNLOAD` is not set
- **THEN** the tests fail with a message naming the URL, the file expected
  under the data root, the SHA-256 and `SIMTEST_FUNNEL_DOWNLOAD=1`, and no
  connection is opened

#### Scenario: Copy differs
- **WHEN** the copy under the data root differs from the data compared
- **THEN** the tests fail with a message giving the expected and the actual
  SHA-256

#### Scenario: Two URLs with the same last path segment
- **WHEN** the reference and test URLs differ but end in the same file name
- **THEN** the snippet uses two different local file names

### Requirement: Opt-in download in the snippet

When `SIMTEST_FUNNEL_DOWNLOAD=1` is set and a URL input's local copy is
missing (and only then), the snippet SHALL download the URL over `https`
only, read at most the recorded size, and save it as the copy only when its
SHA-256 equals the recorded one; an existing copy SHALL never be replaced.

#### Scenario: Opt-in download of a missing copy
- **WHEN** the snippet runs with `SIMTEST_FUNNEL_DOWNLOAD=1`, the copy is
  missing and the URL still serves the data that was compared
- **THEN** the URL is downloaded once, saved under the stated name, and
  every test case passes

#### Scenario: Opt-in download of changed data
- **WHEN** the snippet runs with `SIMTEST_FUNNEL_DOWNLOAD=1`, the copy is
  missing and the URL now serves different data
- **THEN** the tests fail with a message saying the data behind the URL
  differs from what was compared, giving both SHA-256 values, and no file is
  left under the data root

#### Scenario: Opt-in with an existing copy
- **WHEN** the snippet runs with `SIMTEST_FUNNEL_DOWNLOAD=1` and a copy
  already exists
- **THEN** no request is made and the copy is checked as without the
  variable
