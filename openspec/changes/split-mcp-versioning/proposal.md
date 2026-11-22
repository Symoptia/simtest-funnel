# Proposal

## Why

The MCP server's tool surface changes much faster than the library API, yet
every server change today releases the Rust crate, the Python library and
the TypeScript SDK under a new shared version, and every library change
releases a new server. The owner has decided that the libraries keep one
shared version heading for 1.0.0, while `simtest-funnel-mcp` gets its own
0.x line and changelog and pins the library exactly. The server exists on
PyPI only as `1.0.0b12` … `1.0.0b21`, which sort above any 0.x version, so
the split also has to decide what happens to those releases.

## What Changes

- Two version lines in one repository, both released by semantic-release
  on pushes to `beta` and `main`:
  - **Library line** (unchanged numbering, `v<version>` tags): Rust core,
    Python library, TypeScript SDK, docs site. It no longer writes the
    server's version or pin.
  - **Server line** (new, `mcp-v<version>` tags, 0.x): `simtest-funnel-mcp`,
    with its own `python/simtest-funnel-mcp/CHANGELOG.md` and GitHub
    Releases named `simtest-funnel-mcp <version>`. A breaking change bumps
    the minor version while the line is in 0.x.
- Commits are assigned to a line by the paths they touch (server package
  and plugin directory vs. everything else), with a small local
  semantic-release plugin. A commit touching both releases both.
- The server pins `simtest-funnel==<V>` exactly, where V is the library
  version on the release branch at release time (a pre-release while the
  library is in beta). A library release is followed automatically by a
  server patch release that moves the pin.
- Release order and gating: in one run the library is released first, then
  the server. A server release is never tagged with a pin that is neither
  released in the same run nor already on PyPI, its files are uploaded only
  after the pinned library is on PyPI, and a failed server step does not
  stop the library's publication.
- The wheel workflow builds and smoke-tests only the lines that released,
  and tests the server against exactly the library version it pins.
- Version ordering on PyPI (headline design choice, not yet confirmed by
  the owner): the server line releases **stable** 0.x versions from `beta`
  (no server pre-releases), starting at `0.1.0`, and the ten `1.0.0bN`
  server releases are **yanked** (not deleted) once `0.1.0` is on PyPI.
- The server's `--version` also prints the installed library version;
  `serverInfo.version` is the server's own version.
- The release workflow gains a dry-run mode that reports both next
  versions without publishing.
- Documentation: READMEs, `MAINTAINER.md`, `AGENTS.md` ("Releasing",
  commit scopes).
- **BREAKING** (for the server's PyPI history only): `simtest-funnel-mcp`
  restarts at `0.1.0`; the `1.0.0bN` releases are yanked. Earlier beta
  users are deliberately not protected (owner decision).

Out of scope: separate versions for the Rust core, the Python library and
the SDK; changes to npm or crates.io publishing; other distribution
channels for the server (`uvx simtest-funnel-mcp` from PyPI stays the only
one, plotting stays in the default install).

## Capabilities

### New Capabilities

- `release-versioning`: how the repository's two version lines are
  numbered, which commits release which line, how the server's exact
  library pin is chosen and moved, release order and PyPI gating, tags,
  changelogs and GitHub Releases, the version the server reports, the
  treatment of the superseded `1.0.0bN` server releases and the dry run.

### Modified Capabilities

- `python-distribution` (introduced by the in-flight change
  `add-cross-platform-wheels`): "every file verified before upload",
  "MCP server verified on each operating system" and "all-or-nothing
  upload" now apply per released line, and the server is verified against
  the library version it pins.

## Impact

- `.releaserc.json` (library config, reduced), a new server release
  config, a local semantic-release plugin and pin script under
  `scripts/release/`, `scripts/release-refresh-lockfiles.sh` (called by
  both lines, logic unchanged).
- `.github/workflows/release.yml` (two release jobs, conditional
  publishing, concurrency, dry run) and `python-wheels.yml` (per-line
  inputs, smoke against the pinned library).
- `python/simtest-funnel-mcp/pyproject.toml` (version `0.x`),
  new `python/simtest-funnel-mcp/CHANGELOG.md`, `--version` output.
- PyPI (owner, web UI): yank `simtest-funnel-mcp` `1.0.0b12`–`1.0.0b21`.
- Depends on `add-cross-platform-wheels` (archived first). The plugin of
  `add-claude-skill` pins the server's 0.x version and reads it from the
  server line's release.
