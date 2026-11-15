# Proposal

## Why

`simtest-funnel` is published to PyPI as a single wheel —
CPython 3.12, Linux x86-64, glibc 2.34 or newer — with no source
distribution. It cannot be installed on macOS, Windows, ARM Linux, older
Linux distributions or any other Python version. That already limits
pytest users, and it prevents the local MCP server
(`uvx simtest-funnel-mcp`) from starting on most developer machines.

**Sequencing:** this change is deliberately the last step of the MCP
series. The full chain (server, plots, URL ingestion, skill) is first
completed and proven on one platform; multi-platform builds, which can
only be verified by running the release pipeline and cost CI minutes on
macOS and Windows runners, follow once there is a complete product to
ship.

## What Changes

- Build and publish wheels for Linux x86-64 and ARM64, macOS Apple
  Silicon and Intel, and Windows x86-64.
- Build against Python's stable ABI so one wheel per platform serves
  CPython 3.12 and every later version (subject to the `numpy` Rust
  crate supporting it; otherwise one wheel per supported Python
  version).
- Target an older glibc baseline so older Linux distributions work.
- Publish a source distribution as a fallback for other platforms.
- Verify in CI that the published artifacts install and pass a smoke
  test on each platform before release.

## Capabilities

### New Capabilities

- `python-distribution`: which platforms and Python versions the
  Python package installs on from PyPI, and how that is verified.

### Modified Capabilities

<!-- none -->

## Impact

- `.github/workflows/release.yml` (`publish-pypi` job) and possibly
  `ci.yml`; `crates/simtest-funnel-python` build configuration.
- Longer release runs and macOS/Windows runner minutes.
- No API or behaviour change.
