# Design

## Context

See proposal.md (Why, Decisions) for motivation and the owner's binding
decisions, and the spec delta for the required behaviour. State before this
change:

- `crates/simtest-funnel-python` builds the extension `_simtest_funnel`
  with PyO3 0.30 and the `numpy` crate 0.30 (`PyReadonlyArray1`,
  `IntoPyArray`, `PyArray1`), version-specific (`cp312-cp312`).
- `release.yml`: `semantic-release` (version, changelog, tag, GitHub
  Release, npm publish inside semantic-release) → `publish-pypi`,
  `publish-crate`, `publish-docs` in parallel. `publish-pypi` ran
  `maturin build --release` on `ubuntu-latest` (one
  `manylinux_2_34_x86_64` wheel for the runner's Python 3.12), built the
  MCP server's wheel and sdist with `uv build` and uploaded all with one
  `twine upload` using `PYPI_API_TOKEN`.
- `ci.yml`: one Python job on 3.12 (`maturin develop` + pytest).
- `requires-python >= 3.12` in all three `pyproject.toml` files; mypy
  targets 3.12.
- `simtest.funnel` imports `numpy` at module load but the package declared
  no dependencies (it worked only because every environment had numpy
  already). Found while designing the smoke test.

Facts checked on 2026-11-22:

- GitHub-hosted runner labels (docs.github.com, "GitHub-hosted runners"
  reference): Linux x64 `ubuntu-24.04`, Linux arm64 `ubuntu-24.04-arm`,
  Windows x64 `windows-2025`, Windows arm64 `windows-11-arm`, macOS arm64
  `macos-15` / `macos-latest`, macOS Intel `macos-15-intel` (and
  `macos-26-intel`). Standard runners are free and unlimited for public
  repositories, the arm64 ones included. The repository is public.
- PyPI `requires_python` of the newest releases: `mcp` 2.3 ≥ 3.10,
  `truststore` ≥ 3.10, `anyio` ≥ 3.10, `pydantic` ≥ 3.10, `pandas` 3.1 ≥ 3.11,
  `matplotlib` 3.11 ≥ 3.11, `pillow` 13 ≥ 3.11, `numpy` 2.5 ≥ 3.12 (2.4 ≥ 3.11).
- win_arm64 wheels exist for cp311–cp314 of numpy 2.4, pandas, matplotlib,
  pillow, contourpy, kiwisolver, pydantic-core and rpds-py (the MCP
  server's compiled dependencies); musllinux aarch64 wheels exist for
  numpy and pandas but not matplotlib.
- PyO3 0.30 links `python3.dll` on Windows with `raw-dylib`
  (`pyo3-ffi/build.rs`), so no import library or target Python is needed
  to build for Windows; the old `generate-import-lib` feature is a no-op.
- Action versions current at the time: `PyO3/maturin-action` v1.51,
  `actions/upload-artifact` v7, `actions/download-artifact` v8. Existing
  workflows use `actions/checkout@v6`, `setup-python@v6`, `setup-uv@v6`;
  the new workflow uses the same majors (Dependabot updates all of them).

## Goals / Non-Goals

**Goals:**

- `uvx simtest-funnel-mcp` works out of the box on the desktop platforms
  of coding agents (macOS, Windows), with prebuilt wheels only.
- A release never leaves a partial or untested set of Python files on PyPI.
- The builds can be exercised without publishing, and ordinary CI cost
  does not change (one extra Python job version, see §1).

**Non-Goals:**

- No change to the library or server behaviour or API.
- No conda packages, CLI binary in the wheel, plotting extra or separate
  MCP versioning (proposal, Out of scope).
- No free-threaded (`cp314t`) wheels: the stable ABI does not cover
  free-threaded builds; such interpreters get the sdist.

## Decisions

Items marked **(design choice, not yet confirmed by the owner)** are this
design's answer to something the owner's decisions leave open; each gives
the recommendation and the main alternative.

### 1. Minimum Python 3.11 (design choice, not yet confirmed by the owner)

`requires-python = ">=3.11"` for both packages and the workspace; PyO3
feature `abi3-py311`. mypy loses its pinned `python_version` and checks
against the interpreter it runs under: pinning 3.11 while the environment
has numpy 2.5 (≥ 3.12 only, stubs in PEP 695 syntax) produced false
`call-overload` errors, and numpy 2.4's stubs (the 3.11 resolution) type
some reductions as `Any`, which needed one annotated variable in
`reader.py`. `mypy --strict` passes with 3.11 / numpy 2.4.6, 3.12 / 2.5.4
and 3.14 / 2.5.4.

What actually sets the floor:

- The MCP server uses `datetime.UTC` (3.11+; `urlcache.py`, tests) — the
  only 3.11-only feature found; no `type` statements, PEP 695 generics,
  `typing.override` or `itertools.batched` (3.12 features) are used.
  The full test suite passes on 3.11.
- Dependencies allow 3.10 (`mcp` 2.x needs ≥ 3.10; numpy ≥ 1.26, pandas ≥ 2,
  matplotlib ≥ 3.8 all have 3.10 releases).
- CPython 3.10 reached end of life in October 2026; numpy, pandas,
  matplotlib and pillow have already dropped it, so 3.10 users would get
  a frozen, older dependency stack that CI would have to test separately.

Recommendation: 3.11, the lowest version that needs no code change, is
still supported upstream (until October 2027) and gets current dependency
releases (numpy 2.4). Alternative: 3.10 (change `datetime.UTC` to
`timezone.utc`; test against an EOL stack), or keep 3.12 (no gain: the
abi3 wheel works on 3.11 unchanged, tested locally, see "Local
verification").

CI: the `python-test` job of `ci.yml` becomes a two-entry matrix, 3.11 and
3.14 (newest released; 3.15 is in beta), and also runs `make lint-python`
(mypy) there. That is one extra Linux job per CI run, the only CI cost
change. `lint` stays on 3.12 (the devcontainer's version).

`uv.lock` changes genuinely: uv forks the resolution at 3.12 (numpy 2.4.6
and contourpy 1.3.3 for 3.11, unchanged versions for ≥ 3.12) and records
the new `numpy` dependency of `simtest-funnel`. Written with uv 0.11.25,
the version that wrote the file.

### 2. Stable ABI: no code change needed

`pyo3 = { features = ["extension-module", "abi3-py311"] }` in the crate's
`Cargo.toml`, so every build (also `maturin develop`, `cargo test`)
compiles against the limited API and a non-abi3 API cannot creep back in.

- The binding uses only APIs available under abi3 (dicts, lists, tuples,
  exceptions via `create_exception!`, a frozen `#[pyclass]`,
  `py.detach` / `Python::attach`, `check_signals`). It compiled unchanged.
- `numpy` crate 0.30: it reaches numpy's C API through numpy's own
  capsule at run time (not through CPython APIs excluded from the limited
  API) and supports numpy 1.x and 2.x at run time, so it works under abi3.
  Verified: full test suite against the abi3 wheel with numpy 2.4.6 (3.11),
  2.5.5 (3.14) and 1.26.4 (3.11).
- The duplicate `[tool.maturin] requires-python` is removed;
  `[project] requires-python` is the single source.

### 3. Platform matrix (design choice, not yet confirmed by the owner)

| Wheel | Built on | Target | Smoke-tested on |
| --- | --- | --- | --- |
| manylinux x86-64 (glibc ≥ 2.17) | `ubuntu-24.04`, manylinux2014 container | `x86_64` | `ubuntu-24.04` |
| manylinux aarch64 (glibc ≥ 2.17) | `ubuntu-24.04-arm`, native manylinux2014 container | `aarch64` | `ubuntu-24.04-arm` |
| musllinux x86-64 (musl ≥ 1.2) | `ubuntu-24.04`, musllinux_1_2 cross container | `x86_64-unknown-linux-musl` | `ubuntu-24.04`, `python:3.x-alpine` |
| musllinux aarch64 (musl ≥ 1.2) | `ubuntu-24.04`, musllinux_1_2 cross container | `aarch64-unknown-linux-musl` | `ubuntu-24.04-arm`, `python:3.x-alpine` |
| macOS x86-64 (≥ 10.12) | `macos-15` (cross) | `x86_64-apple-darwin` | `macos-15-intel` |
| macOS arm64 (≥ 11.0) | `macos-15` | `aarch64-apple-darwin` | `macos-15` |
| Windows x64 | `windows-2025` | `x86_64-pc-windows-msvc` | `windows-2025` |
| Windows arm64 | `windows-11-arm` | `aarch64-pc-windows-msvc` | `windows-11-arm` |
| sdist | `ubuntu-24.04` | — | `ubuntu-24.04` (built from the sdist) |

- **manylinux 2.17** (manylinux2014), the oldest baseline Rust's standard
  library supports: covers every maintained glibc distribution (RHEL/Alma
  8+, Debian 10+, Ubuntu 18.04+). Alternative `2_28`: no benefit for this
  crate (no C dependencies).
- **musllinux**: cheap (two cross builds, two container smoke tests) and
  makes `pip install simtest-funnel` work in Alpine-based CI images.
  Smoke-tested without the MCP server, since matplotlib has no musllinux
  wheels on every architecture. Alternative: drop musl (Alpine users get
  the sdist and need Rust).
- **Separate macOS wheels instead of universal2**: each download is half
  the size and each wheel is smoke-tested on its own architecture.
  x86-64 is cross-compiled on Apple silicon (Apple's toolchain does this
  natively; Intel macOS runners are being retired, so builds do not depend
  on them); only its smoke test needs the Intel runner. When GitHub
  retires `macos-15-intel`, the smoke test can move to `macos-26-intel`
  or be dropped. Deployment targets are maturin's defaults (10.12 / 11.0).
- **Windows arm64** is built natively on `windows-11-arm` (free for public
  repositories) and gets the full smoke test including the MCP server
  (all its compiled dependencies have win_arm64 wheels for cp311–cp314).
- Not built: 32-bit (i686, win32, armv7), s390x, ppc64le, PyPy. The sdist
  covers them for users with Rust.

### 4. Build tooling: `PyO3/maturin-action` (design choice, not yet confirmed by the owner)

maturin is already the build backend; `maturin-action` runs it in the
PyPA manylinux / rust-cross musllinux containers on Linux (which bring
Rust and do the auditwheel-style tagging) and on the host elsewhere.
`maturin-version` is pinned to the `uv.lock` version (v1.16.0), so CI and
local builds agree. For an abi3 crate no interpreter list is needed.

Alternative: cibuildwheel. It is built around one build per Python
version and a repair step; with abi3 it needs extra configuration, and
for Rust it must install rustup inside each manylinux container. No
benefit here.

### 5. Workflow structure

New reusable workflow `.github/workflows/python-wheels.yml`
(`workflow_call` with input `ref`, plus `workflow_dispatch` and
path-filtered `pull_request`), jobs:

1. `sdist` (ubuntu): `maturin sdist` for `simtest-funnel`, `uv build` for
   `simtest-funnel-mcp` (wheel + sdist); installs the `simtest-funnel`
   sdist with `uv pip install --no-cache` into clean environments for 3.11
   and 3.14 (compiling it) and runs the smoke test. Artifacts
   `dist-sdist`, `mcp-dist`.
2. `build` (matrix of 8, `fail-fast: true`): one wheel each, checked to be
   exactly one `cp311-abi3` wheel, artifact `dist-<name>`.
3. `smoke` (matrix of 8, `needs: [sdist, build]`): on a fresh runner of the
   wheel's platform, without Rust or the source tree (sparse checkout of
   the smoke script only), for 3.11 and 3.14: new venv (`uv venv`),
   install the wheel (and the MCP wheel where `mcp: true`), run
   `scripts/wheel_smoke.py`. musllinux: `docker run python:<v>-alpine`
   with pip.

Separate build and smoke jobs (instead of testing in the build job): the
smoke test then runs on a machine that never had the build environment,
which is what users have, and cross-built wheels (musl aarch64, macOS
x86-64) are tested on real hardware.

`scripts/wheel_smoke.py` (standard library only): checks that
`simtest.funnel` is imported from `site-packages`, prints the extension
file name (e.g. `_simtest_funnel.abi3.so` / `.pyd`), runs one passing and
one failing `compare`; with `--mcp` it starts
`python -m simtest_funnel_mcp` with pipes, sends `initialize`
(protocol `2025-11-25`), `notifications/initialized`, `tools/list`
(expects the three tools) and one `compare_signals` on two generated CSV
files (expects verdict `fail`), then closes stdin and expects exit code 0.
A raw JSON-RPC client is used deliberately: it is what an agent's client
does and does not depend on the SDK's client.

Dependencies in the smoke environments are resolved from PyPI (newest
compatible), not from `uv.lock`: that is what users get.

### 6. Release job order and the all-or-nothing upload

```
semantic-release ──┬─> python-wheels (sdist, build ×8, smoke ×8) ──> publish-pypi
                   ├─> publish-crate
                   └─> publish-docs
```

- `semantic-release` decides the version first, as today
  (`.releaserc.json`, `scripts/release-refresh-lockfiles.sh`); the wheel
  workflow builds from tag `v<version>`, so it builds exactly the release
  commit with the bumped versions.
- `publish-pypi` needs `python-wheels`; with the implicit `success()` its
  `if` is false when any build or smoke job failed or was cancelled, so
  nothing is uploaded. It downloads all `dist-*` artifacts and `mcp-dist`,
  checks the set (exactly 8 `cp311-abi3` wheels + 1 sdist with the release
  version; MCP wheel + sdist), runs `twine check --strict`, then uploads
  `simtest-funnel` first and `simtest-funnel-mcp` second in one step, both
  with `--skip-existing`.
- `publish-crate` stays independent of the wheels
  (design choice, not yet confirmed by the owner): the Rust crate does not
  depend on them, gating it would not make the release atomic (npm is
  already published inside `semantic-release`), and `cargo publish` of an
  existing version fails, so a job that has succeeded must not be in the
  re-run path. Alternative: `publish-crate` needs `python-wheels`, so a
  failed wheel build leaves crates.io untouched as well (then the crate
  is published by the same re-run).

**State after a failure in `python-wheels` or `publish-pypi`:** tag
`v<version>`, the release commit on the branch, the GitHub Release, the
npm package, normally the crates.io crate and the docs exist; PyPI has
nothing for that version (or, if the upload itself broke mid-way, a prefix
of the `simtest-funnel` files, never an MCP file without its library). Users
of `uvx simtest-funnel-mcp` keep getting the previous version.

**Recovery:**

- Transient (runner, network, PyPI): "Re-run failed jobs" on the same run
  (`gh run rerun <id> --failed`). Failed jobs and their dependents rerun
  from the same tag; artifacts of the successful jobs remain available to
  the run; `--skip-existing` completes a partial upload. Re-running the
  whole workflow is also safe for PyPI but would re-run `semantic-release`
  (which finds no new commits and does nothing) and the crates.io job
  (which fails on an existing version), so prefer failed-jobs-only.
- Real defect: fix on `beta` (`fix:` commit). The next release carries a
  new version and publishes everything; the broken version stays absent
  from PyPI. Nothing on PyPI references it, since `simtest-funnel-mcp`
  pins `simtest-funnel` exactly and the MCP files are uploaded last.

Documented for maintainers in `MAINTAINER.md` ("Python wheels").

### 7. Trial run without publishing (design choice, not yet confirmed by the owner, for the triggers)

- `workflow_dispatch` on `python-wheels.yml` (input `ref`, default the
  selected branch). GitHub offers manual runs only for workflows present
  on the default branch (`main`), so this works once the change has
  reached `main`.
- `pull_request` into `main`, `beta` or `develop` when the packaging files
  change (`crates/simtest-funnel-python/{Cargo.toml,pyproject.toml}`,
  `python/simtest-funnel-mcp/pyproject.toml`, `scripts/wheel_smoke.py`,
  the two workflow files). This is how the change itself gets its first
  real test: open a pull request with it into `beta` and let the matrix
  run before merging; the merge then triggers the first real release.
  Ordinary pull requests (core or server code) do not run the matrix.

Artifacts are kept for the repository's default retention. Alternative:
manual trigger only (cheaper still, but the first run would be the
release itself until the workflow reaches `main`).

### 8. PyPI trusted publishing: prepared as a follow-up, token kept

Trusted publishing (OIDC) needs a "trusted publisher" registered on PyPI
for each project before the first upload that uses it; there is no way to
prepare the workflow so that it works both before and after that without
keeping the token path. The workflow therefore keeps `PYPI_API_TOKEN`
(which must be allowed to upload to both projects). Owner steps to switch:

1. On pypi.org, for `simtest-funnel` and for `simtest-funnel-mcp`:
   *Manage project → Publishing → Add a new publisher → GitHub*, owner
   `Symoptia`, repository `simtest-funnel`, workflow `release.yml`,
   environment `pypi`.
2. In GitHub: create the environment `pypi` (Settings → Environments),
   optionally restricted to the `main` and `beta` branches.
3. Then change `publish-pypi`: `environment: pypi`,
   `permissions: id-token: write`, and replace the twine upload by two
   `pypa/gh-action-pypi-publish@release/v1` steps (`packages-dir: dist/`
   then `mcp-dist/`, `skip-existing: true`), or `uv publish
   --trusted-publishing always`; remove `TWINE_*`.
4. Delete the `PYPI_API_TOKEN` secret and revoke the token on PyPI.

### 9. Documentation

READMEs (workspace, `crates/simtest-funnel-python` = PyPI page of
`simtest-funnel`, package README, MCP README) state Python ≥ 3.11 and the
platforms; the MCP README's "Linux x86-64 / CPython 3.12 only" note is
replaced by a platform list; "once published to PyPI" goes (the server is
on PyPI). There were no `--prerelease allow` notes to remove: uv accepts
the pre-release because the package has only pre-releases and the MCP
server pins `simtest-funnel` exactly. The PyPI page's relative link to the
workspace README becomes absolute.

## Local verification (2026-11-22, Linux x86-64, devcontainer)

- `maturin build --release` before (cp312) and after (abi3):
  `simtest_funnel-1.0.0b17-cp312-cp312-manylinux_2_34_x86_64.whl`
  362 950 bytes → `…-cp311-abi3-manylinux_2_34_x86_64.whl` 381 109 bytes
  (+5 %; the extension 860 840 → 882 408 bytes, +2.5 %).
- Speed, both wheels on CPython 3.12.13, best of 5–10, second (warm)
  round, before → after: wide-x compare of 100k samples 868.7 → 862.9 ms,
  default compare of 2M samples 194.5 → 194.0 ms, 2M min/max downsample
  18.9 → 18.8 ms, 5,000 compares of 50 samples (call overhead) 57.6 →
  56.3 ms. No measurable change (within run-to-run noise of a few %).
- sdist 200 969 bytes; it vendors `simtest-funnel-core` (sources, tests and
  corpus as in the crates.io package) and the workspace `Cargo.lock`.
- Clean venvs (uv-managed CPython 3.11.15 and 3.14.6), each with the wheel
  or the sdist (compiled by `uv pip install --no-cache`), the freshly built
  MCP wheel, pytest and cryptography, dependencies from PyPI: full Python
  suite (`tests/python` + MCP tests) and `scripts/wheel_smoke.py --mcp`
  pass in all four; 3.11 with numpy 1.26.4 and pandas 2.x: `tests/python`
  passes.

## Risks / Trade-offs

- [The workflows are untested until they run on GitHub] → `actionlint`
  (with shellcheck) passes; first real run through the path-filtered pull
  request into `beta` before merging (§7).
- [Container or runner specifics: musllinux aarch64 cross image, native
  manylinux on `ubuntu-24.04-arm`, Rust on `windows-11-arm`, Docker on
  arm64 runners] → a failure stops the release before upload; fix or drop
  the entry (the matrix is data).
- [abi3 may cost some speed in call overhead] → measured: no measurable
  change ("Local verification").
- [Release runs get longer (≈ 18 jobs)] → parallel; only release and
  packaging pull requests pay it.
- [macOS Intel runners retire] → only the x86-64 smoke test uses one (§3).
- [`crates/simtest-funnel-python/uv.lock` is a stale, unused lockfile that
  ends up in the sdist] → harmless; removing it is left to a separate
  clean-up.

## Open Questions

None blocking. The owner is asked to confirm §1 (3.11), §3 (musllinux and
Windows arm64 included), §4 (maturin-action), §6 (crates.io not gated) and
§7 (pull request trigger).
