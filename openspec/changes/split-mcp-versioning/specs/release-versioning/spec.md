# Spec Delta

## Purpose

Defines the repository's two release version lines (the shared library line
and the MCP server's own 0.x line): which commits release which line, how
the server's exact library pin is chosen and moved, release order and PyPI
gating, tags, changelogs, the version the server reports, and the dry run.

## ADDED Requirements

### Requirement: Two version lines

The Rust crate `simtest-funnel-core`, the Python library `simtest-funnel`
and the npm package `@simtest-js/funnel` SHALL share one version (the
library line), tagged `v<version>`. The MCP server `simtest-funnel-mcp`
SHALL have its own semantic version (the server line), tagged
`mcp-v<version>`, which SHALL NOT be written into any library package.

#### Scenario: Server-only release
- **WHEN** a push releases only the server line as `0.4.0`
- **THEN** the repository gains the tag `mcp-v0.4.0`, PyPI gains
  `simtest-funnel-mcp` `0.4.0`, and no library package gets a new version

#### Scenario: Library-only release
- **WHEN** a push releases only the library line as `1.0.0-beta.23`
- **THEN** the tag `v1.0.0-beta.23` exists, the crate, the Python library
  and the npm package carry that version, and the server package's own
  version is unchanged

### Requirement: Commits assigned to a line by path

A releasing commit (by Conventional Commit type, as today) SHALL count for
the server line when it changes a file in `python/simtest-funnel-mcp/` or
`plugins/simtest-funnel/`, and for the library line when it changes any
other file except `uv.lock`. A commit changing files of both sets SHALL
count for both lines. The commit scope SHALL NOT affect the assignment.

#### Scenario: Server fix
- **WHEN** the only new commit is `fix(mcp): ...` changing files under
  `python/simtest-funnel-mcp/`
- **THEN** the next run releases a server patch and no library version

#### Scenario: Commit touching both
- **WHEN** a `feat` commit changes `crates/simtest-funnel-python/` and
  `python/simtest-funnel-mcp/`
- **THEN** the same run releases a library minor (or pre-release) version
  and a server minor version

#### Scenario: Lockfile-only change
- **WHEN** the only new commit is `fix(deps): ...` changing only `uv.lock`
- **THEN** neither line releases

### Requirement: Server line stays in 0.x

While the server line's major version is 0, a breaking change (`!` or a
`BREAKING CHANGE` footer) SHALL bump the server's minor version, a `feat`
the minor version and a `fix` or `perf` the patch version. Leaving 0.x
SHALL require an explicit configuration change, not a commit message.

#### Scenario: Breaking server change
- **WHEN** the last server release is `0.4.2` and a commit
  `feat(mcp)!: rename the pairs argument` changes the server
- **THEN** the next server version is `0.5.0`

### Requirement: Server released as stable versions from beta

The server line SHALL be released only from pushes to `beta`, and every
server release SHALL be a final (non-pre-release) version. A push to
`main` SHALL NOT release the server line; server tags reach `main` by
merging `beta`.

#### Scenario: Push to beta
- **WHEN** a server `feat` commit is pushed to `beta`
- **THEN** a final version such as `0.3.0` is released, not `0.3.0-beta.1`

#### Scenario: Merge to main
- **WHEN** `beta` is merged into `main`
- **THEN** the library line may release a stable version and the server
  line releases nothing

### Requirement: Exact library pin

Each server release SHALL declare exactly one dependency on the library,
`simtest-funnel==<V>`, where V is the library version recorded on the
release branch when the server is released, and SHALL NOT use a range.
V MAY be a pre-release.

#### Scenario: Library in beta
- **WHEN** the library version on `beta` is `1.0.0-beta.22` and the server
  releases `0.2.0`
- **THEN** the metadata of `simtest-funnel-mcp` `0.2.0` requires
  `simtest-funnel==1.0.0b22` (equivalent PEP 440 spelling) and nothing
  looser

### Requirement: Pin follows library releases

When the library version on the release branch differs from the server's
current pin, the server line SHALL release at least a patch version that
moves the pin, even if no commit counts for the server line, and its
release notes SHALL name the newly pinned library version.

#### Scenario: Library fix only
- **WHEN** a push to `beta` releases only library `1.0.0-beta.23` and the
  server, at `0.2.0`, pins `1.0.0-beta.22`
- **THEN** the same run releases server `0.2.1` pinning `1.0.0-beta.23`,
  with a release note naming that library version

### Requirement: Release order within one run

Within one release run, the library line SHALL be released before the
server line, so that a server release made by the same push pins the
library version released by that push.

#### Scenario: One push changes both
- **WHEN** one push contains a library `feat` and a server `fix`
- **THEN** library `1.0.0-beta.24` is tagged first and server `0.2.2`,
  tagged afterwards, pins `1.0.0-beta.24`

### Requirement: No server tag for an unavailable library

A server release SHALL NOT be tagged unless the library version it would
pin was released in the same run or is already installable from PyPI. If
neither holds, the server step SHALL fail with a message naming the
version, and no server tag, commit or GitHub Release SHALL be created.

#### Scenario: Previous library release never reached PyPI
- **WHEN** library `1.0.0-beta.25` was tagged but its wheel build failed,
  and a later push changes only the server
- **THEN** the server step fails naming `simtest-funnel 1.0.0b25` and no
  `mcp-v` tag is created

### Requirement: PyPI upload gated on the pinned library

Server distribution files SHALL be uploaded to PyPI only after the pinned
library version is installable from PyPI; when both lines release in one
run, every library file SHALL be uploaded before any server file. A
failure of the server's release or build steps SHALL NOT prevent the
library release of the same run from being published.

#### Scenario: Library wheels fail
- **WHEN** library and server release in one run and a library wheel build
  fails
- **THEN** no file of either version is uploaded, and re-running the
  failed jobs uploads the library first and then the server

#### Scenario: Server build fails
- **WHEN** library and server release in one run and only the server's
  smoke test fails
- **THEN** the library files are uploaded to PyPI, crates.io and npm
  publishing are unaffected, and no server file is uploaded

### Requirement: Separate changelogs and GitHub Releases

The library line SHALL keep `CHANGELOG.md` at the repository root and the
server line SHALL keep `python/simtest-funnel-mcp/CHANGELOG.md`; each SHALL
list only its own line's releases. Each release SHALL create one GitHub
Release named after its package and version, a server one titled
`simtest-funnel-mcp <version>`.

#### Scenario: Server release notes
- **WHEN** server `0.3.0` is released
- **THEN** its entry appears only in the server changelog, and the GitHub
  Release `simtest-funnel-mcp 0.3.0` for tag `mcp-v0.3.0` lists only
  commits counted for the server line

### Requirement: Versions reported by the server

The server SHALL report its own package version as `serverInfo.version`
during MCP initialization, and `simtest-funnel-mcp --version` SHALL print
both the server version and the installed `simtest-funnel` version.

#### Scenario: Version query
- **WHEN** a user runs `simtest-funnel-mcp --version` for server `0.3.0`
  installed with library `1.0.0b22`
- **THEN** the output names `simtest-funnel-mcp 0.3.0` and
  `simtest-funnel 1.0.0b22`

### Requirement: Release commits change only version lines in lockfiles

A release of either line SHALL change `Cargo.lock` and `uv.lock` only in
the version entries of that line's own packages; any other lockfile change
SHALL fail the release before anything is tagged.

#### Scenario: Server release
- **WHEN** the server line releases
- **THEN** `uv.lock` differs only in the `simtest-funnel-mcp` version line
  and `Cargo.lock` is unchanged

### Requirement: Superseded server pre-releases yanked

After the first server-line version is installable from PyPI, the
`simtest-funnel-mcp` releases `1.0.0b12` to `1.0.0b21` SHALL be yanked
(not deleted) with a reason naming the 0.x line. No later server release
SHALL use a version number of the form `1.0.0bN`.

#### Scenario: Unpinned install after the yank
- **WHEN** a user without any cached environment runs
  `uvx simtest-funnel-mcp`, or `uvx --prerelease allow simtest-funnel-mcp`
- **THEN** the newest 0.x server is installed, not `1.0.0b21`

#### Scenario: Exact pin to a yanked release
- **WHEN** a user requests `simtest-funnel-mcp==1.0.0b21`
- **THEN** the installer still installs it (with a yank warning)

### Requirement: Release dry run

The release workflow SHALL be runnable on demand in a dry-run mode that
reports, for the selected branch, the next version of each line (or that
none would be released) and the library version a server release would
pin, without creating commits, tags, GitHub Releases or uploads.

#### Scenario: Dry run on beta
- **WHEN** the maintainer starts the release workflow in dry-run mode on
  `beta` with one unreleased server `fix`
- **THEN** the run reports no library release and the next server patch
  version with its pin, and the repository and registries are unchanged

### Requirement: Versioning documented

The server README SHALL state that the server has its own 0.x version line,
how to see which library version a server pins, how to make `uvx` pick up
a newer server than a cached one, and the minimum `uv` version that
resolves its pin. The maintainer guide SHALL describe both lines, their
tags and failure recovery.

#### Scenario: Reader checks the README
- **WHEN** a user reads the server README's installation section
- **THEN** it names the 0.x line, `simtest-funnel-mcp --version`,
  `uvx simtest-funnel-mcp@latest` and the minimum uv version
