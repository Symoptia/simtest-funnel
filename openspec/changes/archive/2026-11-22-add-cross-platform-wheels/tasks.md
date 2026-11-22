# Tasks

## 1. Python versions and metadata

- [x] 1.1 Set `requires-python = ">=3.11"` in `crates/simtest-funnel-python/pyproject.toml`, `python/simtest-funnel-mcp/pyproject.toml` and the workspace `pyproject.toml`, remove the duplicate `[tool.maturin] requires-python`, drop mypy's pinned `python_version` (design §1) and annotate the one numpy reduction typed `Any` by numpy 2.4 stubs (`reader.py`), add classifiers (3.11–3.14, Linux/macOS/Windows) and the project URL; verify `mypy --strict` passes in environments synced for 3.11, 3.12 and 3.14
- [x] 1.2 Declare `dependencies = ["numpy>=1.26"]` for `simtest-funnel` (imported at module load); verify a clean venv with only the wheel imports `simtest.funnel` and compares (`scripts/wheel_smoke.py`)
- [x] 1.3 Refresh `uv.lock` with uv 0.11.25 (`uv --version` checked first); verify the diff only adds the Python 3.11 fork (numpy 2.4.6, contourpy 1.3.3) and the `numpy` dependency of `simtest-funnel`, and `uv lock --check` passes
- [x] 1.4 CI `python-test` job as a matrix over 3.11 and 3.14 (`ci.yml`, `UV_PYTHON`), also running `make lint-python`; verify `actionlint` passes and the job's steps pass locally in environments synced with `uv sync --python 3.11` (tests + mypy) and `--python 3.14` (mypy)

## 2. Stable ABI

- [x] 2.1 Enable PyO3 `abi3-py311` in `crates/simtest-funnel-python/Cargo.toml` (comment linking it to `requires-python`); verify `cargo clippy --workspace --all-targets -- -D warnings` and `cargo test --workspace` pass with no Rust code change
- [x] 2.2 Build the release wheel with `maturin build --release`; verify its tag is `cp311-abi3` and the extension is `_simtest_funnel.abi3.so`
- [x] 2.3 Install the abi3 wheel with the freshly built MCP wheel into clean venvs for CPython 3.11 and 3.14 and run `tests/python` and the MCP tests against the installed packages (not the source tree), plus `tests/python` on 3.11 with numpy 1.26 and pandas 2.x; verify all pass
- [x] 2.4 Compare wheel size and speed against the previous `cp312` build (release builds, same Python 3.12, best of N: wide-x 100k compare, default 2M compare, 2M downsample, 5,000 small compares); verify and record the numbers in design.md ("Local verification")

## 3. Source distribution

- [x] 3.1 `maturin sdist` from `crates/simtest-funnel-python`; verify it contains `crates/simtest-funnel-core` and `Cargo.lock`
- [x] 3.2 Install the sdist with `uv pip install --no-cache` into clean venvs for 3.11 and 3.14 (compiling it), run the Python test suite and `scripts/wheel_smoke.py --mcp`; verify all pass

## 4. Smoke test

- [x] 4.1 `scripts/wheel_smoke.py` (standard library only): import from `site-packages`, extension name, a passing and a failing `compare`; `--mcp`: start `python -m simtest_funnel_mcp`, `initialize`, `tools/list` with the three tools, one `compare_signals` with verdict `fail`, clean exit; verify it passes against the installed wheel and the installed sdist on 3.11 and 3.14 and fails (exit code ≠ 0) when run against the source tree

## 5. Workflows

- [x] 5.1 `.github/workflows/python-wheels.yml`: reusable (`ref` input), `workflow_dispatch`, path-filtered `pull_request`; jobs `sdist`, `build` (8 targets, design §3), `smoke` (8 native runners, 3.11 and 3.14, MCP where `mcp: true`, Alpine containers for musl); artifacts `dist-*` and `mcp-dist`; verify `actionlint` with shellcheck reports nothing
- [x] 5.2 `release.yml`: replace the single-wheel `publish-pypi` with `python-wheels` (called with `ref: v<version>`) and `publish-pypi` (needs it; checks the file set, `twine check --strict`, uploads `simtest-funnel` then `simtest-funnel-mcp` with `--skip-existing`, token unchanged); verify `actionlint` reports nothing and that no other job changed
- [ ] 5.3 First real run on GitHub: open a pull request with this change into `beta`; verify the "Python wheels" run passes all 17 jobs and its artifacts hold 8 `cp311-abi3` wheels, the sdist and the MCP wheel and sdist (owner; not possible locally)

## 6. Documentation

- [x] 6.1 READMEs (workspace, `crates/simtest-funnel-python`, package README, MCP README): Python ≥ 3.11, platforms, sdist needs Rust; remove the Linux-only note and "once published to PyPI"; absolute link on the PyPI page; verify `grep -rn "CPython 3.12\|once published" README.md crates python` finds nothing
- [x] 6.2 `MAINTAINER.md`: Python wheels section (trial run, failure state, recovery), PyPI token valid for both projects; verify it matches design §6–§8

## 7. Integration checks

- [x] 7.1 Run `make build`, `make lint`, `make test` and `openspec validate add-cross-platform-wheels --strict`; verify all pass

## Workflow follow-up

- Owner review of the design choices marked "not yet confirmed" (design §1, §3, §4, §6, §7).
- Optional: switch to PyPI trusted publishing (design §8, owner steps on PyPI first).
- Archive after the first release from `beta` has published the full set to PyPI.
