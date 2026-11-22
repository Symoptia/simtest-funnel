# Spec Delta

## Purpose

Defines where the Python packages `simtest-funnel` and `simtest-funnel-mcp`
install from PyPI (platforms, Python versions, source distribution) and how
a release verifies every distribution file before any of them is uploaded.

## ADDED Requirements

### Requirement: Supported Python versions

Both `simtest-funnel` and `simtest-funnel-mcp` SHALL declare the same
minimum CPython version (3.11) and SHALL install and work on it and on every
later released CPython version with the standard (not free-threaded) build.
The test suite SHALL run in CI on the lowest and on the newest supported
version.

#### Scenario: Lowest version
- **WHEN** a user runs `pip install simtest-funnel-mcp` with CPython 3.11
  on a platform with prebuilt wheels
- **THEN** both packages install from wheels and the server starts

#### Scenario: Older interpreter refused
- **WHEN** a user runs `pip install simtest-funnel` with CPython 3.10
- **THEN** pip finds no compatible release instead of installing a package
  that fails at import

#### Scenario: CI matrix
- **WHEN** CI runs the Python test job
- **THEN** it runs the full Python test suite once with the lowest and once
  with the newest supported Python version

### Requirement: One stable-ABI wheel per platform

`simtest-funnel` SHALL be published as one wheel per platform built against
CPython's stable ABI for the minimum supported version, so that the same
wheel installs on that version and every later one. A release SHALL NOT
contain version-specific wheels.

#### Scenario: Newer Python uses the same wheel
- **WHEN** a user installs a release on CPython 3.14 and on CPython 3.11 on
  the same platform
- **THEN** both installs use the same `cp311-abi3` wheel file

### Requirement: Platforms with prebuilt wheels

Each release SHALL contain `simtest-funnel` wheels for Linux x86-64 and
ARM64 (glibc 2.17 or newer, and musl 1.2 or newer), macOS x86-64 and ARM64,
and Windows x64 and ARM64. `simtest-funnel-mcp` SHALL stay a pure-Python
wheel that installs wherever its dependencies do.

#### Scenario: Desktop platforms
- **WHEN** a user on macOS (Intel or Apple silicon) or Windows x64, or on
  Windows ARM64 with an x64 Python, runs `uvx simtest-funnel-mcp`
- **THEN** uv installs prebuilt wheels only, without compiling anything, and
  the server starts

#### Scenario: Native Python on Windows ARM64
- **WHEN** a user installs `simtest-funnel` with a native ARM64 Python on
  Windows
- **THEN** the library installs from its prebuilt wheel; the MCP server is
  not covered there, because one of its dependencies has no such wheel

#### Scenario: Older Linux distribution
- **WHEN** a user on a Linux distribution with glibc 2.28 installs
  `simtest-funnel`
- **THEN** a prebuilt wheel is installed

#### Scenario: Alpine Linux
- **WHEN** a user on Alpine Linux (musl) installs `simtest-funnel`
- **THEN** a prebuilt musllinux wheel is installed

### Requirement: Declared runtime dependencies

`simtest-funnel` SHALL declare every package it imports when
`simtest.funnel` is imported (`numpy`), so that installing it into an empty
environment gives a package that imports and compares. Packages needed only
by optional functions (`pandas` for `compare_dataframes`) SHALL stay
optional.

#### Scenario: Clean environment
- **WHEN** `simtest-funnel` is installed into a new virtual environment
  with nothing else
- **THEN** `import simtest.funnel` succeeds and `compare` runs

### Requirement: Source distribution

Each release SHALL contain a source distribution of `simtest-funnel` that
contains every source it needs (including the Rust core crate) and builds
and installs with only a Python installation and a Rust toolchain, without
access to the repository.

#### Scenario: Platform without a wheel
- **WHEN** a user on a platform without a prebuilt wheel runs
  `pip install simtest-funnel` with a Rust toolchain installed
- **THEN** pip builds the package from the source distribution and the
  installed package imports and compares

### Requirement: Every file verified before upload

Before uploading, a release SHALL build every distribution file of both
packages from the release tag and SHALL install each `simtest-funnel` wheel
and the sdist into a clean environment on the platform it targets, with the
lowest and the newest supported Python, import it and run one comparison.

#### Scenario: Wheel smoke test
- **WHEN** the release builds the macOS ARM64 wheel
- **THEN** it is installed on a macOS ARM64 machine that did not build it,
  into new environments for the lowest and the newest supported Python,
  and a comparison returns the expected statuses

### Requirement: MCP server verified on each operating system

On at least one platform per operating system (Linux, macOS, Windows), the
release SHALL install the freshly built `simtest-funnel-mcp` wheel together
with the freshly built `simtest-funnel` wheel into a clean environment,
start `python -m simtest_funnel_mcp` over stdio, and check that it answers
`initialize`, lists its tools and completes one `compare_signals` call.

#### Scenario: Server smoke test on Windows
- **WHEN** the release builds the Windows x64 wheel
- **THEN** the server, installed from the new wheels on a Windows machine,
  lists `describe_signals`, `compare_signals` and `plot_signals` and
  compares two small CSV files

### Requirement: All-or-nothing upload

A release SHALL upload its Python distribution files to PyPI in a single
step that runs only after every build and every verification has passed;
if any of them fails, no file of that version SHALL be uploaded. Within the
step, `simtest-funnel` SHALL be uploaded before `simtest-funnel-mcp`.

#### Scenario: One platform fails
- **WHEN** the Windows ARM64 build or its smoke test fails during a release
- **THEN** no file of that version is uploaded to PyPI for either package

#### Scenario: Upload order
- **WHEN** the upload step runs
- **THEN** every `simtest-funnel` file is uploaded before any
  `simtest-funnel-mcp` file

### Requirement: Recovery from a failed release

Re-running the failed jobs of a release run SHALL rebuild from the same tag
and upload the complete set; files already on PyPI for that version (from an
interrupted upload) SHALL be skipped, not fail the step. The maintainer
documentation SHALL describe the state a failure leaves and how to recover.

#### Scenario: Transient failure
- **WHEN** a smoke test failed because of a runner problem and the
  maintainer re-runs the failed jobs
- **THEN** the release's Python files are uploaded without a new version

#### Scenario: Interrupted upload
- **WHEN** the upload stopped after some files and the job is re-run
- **THEN** the remaining files are uploaded and the existing ones skipped

### Requirement: Trial run without publishing

The same builds and verifications SHALL be runnable on demand, and on pull
requests that change the Python packaging files, without uploading to any
registry; the built files SHALL be kept as downloadable workflow artifacts.
Ordinary CI runs SHALL NOT build release wheels.

#### Scenario: Manual run
- **WHEN** the maintainer starts the wheel workflow by hand on a branch
- **THEN** all wheels, the sdist and the MCP distributions are built and
  verified, offered as workflow artifacts, and nothing is published

#### Scenario: Ordinary pull request
- **WHEN** a pull request changes only the Rust core or the MCP server code
- **THEN** no wheel matrix runs for it
