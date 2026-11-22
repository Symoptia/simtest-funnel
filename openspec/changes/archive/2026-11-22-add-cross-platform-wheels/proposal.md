# Proposal

## Why

`simtest-funnel` is published to PyPI as a single wheel —
CPython 3.12, Linux x86-64, glibc 2.34 or newer — with no source
distribution. It cannot be installed on macOS, Windows, ARM Linux, older
Linux distributions or any other Python version. `uvx simtest-funnel-mcp`
is the MCP server's only distribution channel, and its users are desktop
coding agents, mostly on macOS and Windows: today the server starts for
almost none of them. The wheel also does not declare its `numpy`
dependency, so even on the one supported platform a plain
`pip install simtest-funnel` gives a package that fails on import.

**Sequencing:** this change is deliberately the last step of the MCP
series. The full chain (server, plots, URL ingestion, skill) was first
completed and proven on one platform; multi-platform builds, which can
only be verified by running the release pipeline and cost CI minutes on
macOS and Windows runners, follow now that there is a complete product to
ship.

## What Changes

- **Stable ABI:** the extension is built against Python's stable ABI
  (PyO3 `abi3`), so one wheel per platform serves the minimum supported
  CPython version and every later one.
- **Minimum Python 3.11** for both `simtest-funnel` and
  `simtest-funnel-mcp` (today 3.12); the abi3 floor is the same version.
  CI's Python job runs the test suite on the lowest and the newest
  supported Python.
- **Wheels for** Linux x86-64 and ARM64 (manylinux 2.17, i.e. glibc 2.17
  or newer, and musllinux 1.2), macOS x86-64 and ARM64, Windows x64 and
  ARM64, plus a **source distribution** that builds on any platform with a
  Rust toolchain.
- `simtest-funnel` declares its `numpy` dependency.
- **Release pipeline:** semantic-release decides the version and tags as
  today; then the wheel matrix and the sdist build from the tag; every
  wheel is smoke-tested on its own platform in a clean environment (import,
  one comparison; on each OS also the freshly built MCP server, started
  over stdio and answering `tools/list` and one `compare_signals`); only
  when everything has passed does one job upload all files to PyPI.
  Nothing is uploaded if any build or smoke test fails.
- **Builds only in the release workflow** (every release from `beta` and
  from `main`) and in a separate workflow that can be run by hand, or on a
  pull request that changes the packaging files, and keeps the files as
  workflow artifacts without publishing. Ordinary CI does not build wheels.
- Install documentation lists the supported platforms and Python versions;
  the "Linux x86-64 / CPython 3.12 only" caveat is removed.

**BREAKING** (beta line, accepted): none for users of a working install;
the published wheel's tag changes from `cp312-cp312` to `cp311-abi3`, and
the manylinux tag from `manylinux_2_34` to `manylinux_2_17`.

Out of scope:

- Shipping the `simtest-funnel` CLI binary inside the wheel.
- A plotting extra for the MCP server (it keeps matplotlib as a hard
  dependency).
- Separate versioning of the MCP server.
- conda packages.
- Free-threaded CPython wheels (the stable ABI does not cover them; such
  interpreters fall back to the sdist).
- 32-bit platforms, other Linux architectures (s390x, ppc64le, armv7) and
  PyPy / GraalPy wheels.
- Running wheel builds in ordinary CI.

## Capabilities

### New Capabilities

- `python-distribution`: which platforms and Python versions the two
  Python packages install on from PyPI, the source distribution, the
  stable-ABI build, and how a release verifies every file before
  uploading any (smoke tests, all-or-nothing upload, recovery), plus the
  unpublished trial run.

### Modified Capabilities

<!-- none: no library or server behaviour changes -->

## Impact

- `crates/simtest-funnel-python`: `Cargo.toml` (pyo3 `abi3-py311`),
  `pyproject.toml` (`requires-python`, `numpy` dependency, classifiers,
  duplicate maturin `requires-python` removed). No Rust code change is
  needed: the binding uses no API outside the stable ABI.
- `python/simtest-funnel-mcp/pyproject.toml` and the workspace
  `pyproject.toml`: `requires-python >= 3.11`, classifiers, mypy checks
  the running interpreter (one annotation in `reader.py` for numpy 2.4's
  stubs); `uv.lock` gains the Python 3.11 fork (numpy 2.4, contourpy 1.3)
  and the `numpy` dependency of `simtest-funnel`.
- `.github/workflows/`: new `python-wheels.yml` (reusable, also manual and
  path-filtered pull requests), `release.yml` (`python-wheels` +
  `publish-pypi` replace the single-wheel job), `ci.yml` (Python job on
  3.11 and 3.14).
- `scripts/wheel_smoke.py`: the per-platform smoke test.
- READMEs: install instructions and supported platforms.
- Longer release runs (about 17 extra jobs, macOS and Windows among them;
  free on GitHub-hosted runners for public repositories).
- Details, alternatives and the points not yet confirmed by the owner are
  in design.md.

## Decisions

Decided by the owner (binding for design and specs):

1. **Wheels are built only in the release workflow**, so ordinary CI cost
   does not change; the full set is built on every release from `beta` as
   well as `main`, so the builds are exercised before a stable release.
2. **Stable ABI** (PyO3 `abi3`): one wheel per platform covers a minimum
   Python version and all later ones.
3. **Clean design, no compatibility with earlier betas.**
