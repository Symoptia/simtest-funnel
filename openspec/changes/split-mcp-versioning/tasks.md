# Tasks

## 1. Owner decisions and prerequisites

- [ ] 1.1 Owner confirms or changes the choices marked "not yet confirmed" (design §1 version ordering, §2 path assignment, §4 automatic pin patches, §11 plugin reading); verify the answers are recorded in design.md and, if §1 changes to option C or E, tasks 2.2, 2.3 and 7.x are adjusted before starting
- [ ] 1.2 Archive `add-cross-platform-wheels` (its first full release has published) so the `python-distribution` delta has a target; verify `openspec validate split-mcp-versioning --strict` no longer reports "target spec does not exist"

## 2. Release configurations

- [ ] 2.1 `scripts/release/path-filter.mjs`: semantic-release plugin wrapping `commit-analyzer` and `release-notes-generator` with include/exclude path prefixes and the server's pin-change patch with a "Pins simtest-funnel X" note (design §2, §4), plus `node:test` tests on a temporary git repository (server-only, library-only, both, `uv.lock`-only, pin change without commits, `feat(mcp)!` → minor); verify the tests pass with `node --test`
- [ ] 2.2 Reduce `.releaserc.json` to the library line (`tagFormat`, path filter excluding the server set, `prepareCmd` and git assets without the server files) and add the server configuration (`branches: ["beta"]`, `mcp-v` tags, `conventionalcommits` preset, breaking → minor, server changelog, release name template, commit message) (design §3); verify with the dry-run harness of 2.4
- [ ] 2.3 `scripts/release/pin-library.sh`: read the library version, write `simtest-funnel==<V>` into the server's `pyproject.toml`, accept V when it equals `LIB_RELEASED_VERSION`, otherwise require the PyPI JSON for the PEP 440 version to list files, fail with a message naming the version (design §5); verify with shellcheck and by running it against a released version (passes), a non-existent one (fails, file unchanged after `git checkout`) and the same-run case
- [ ] 2.4 `scripts/release/dry-run.sh`: clone the repository into a temporary directory with a local bare remote (tags and `refs/notes/semantic-release-*` included), add the bootstrap tag of §10 and scripted test commits, run both configurations with `--dry-run --no-ci`; verify it reports library `1.0.0-beta.22` / server `0.1.0` for a library fix plus server feat, server `0.1.1` pinning the new library for a library-only fix, and "not configured" for the server on `main`
- [ ] 2.5 Keep `scripts/release-refresh-lockfiles.sh` working for both lines (design §7); verify by running each line's `prepareCmd` in a scratch clone with uv 0.11.25: the library run changes only the library `version =` lines, the server run only the `simtest-funnel-mcp` line of `uv.lock`, and the guard passes

## 3. Server package

- [ ] 3.1 `--version` prints server and installed library version (design §8); verify with a unit test and `uv run simtest-funnel-mcp --version`, and that `serverInfo.version` in the stdio end-to-end test equals the package version
- [ ] 3.2 Set the server's `pyproject.toml` version to `0.0.0`, add `python/simtest-funnel-mcp/CHANGELOG.md` with the header of design §9; verify `uv lock --check` passes after `uv lock` and `make test-python` passes

## 4. Workflows

- [ ] 4.1 `python-wheels.yml`: `lib_ref` / `mcp_ref` inputs, library jobs and server build conditional, new `smoke-mcp` job (3 rows) installing the pinned library from the run's artifacts or as a first-party requirement from PyPI, library `smoke` without `--mcp` (design §6); verify `actionlint` with shellcheck reports nothing and a manual run with only `mcp_ref` (current `beta`) passes with `simtest-funnel 1.0.0b21` from PyPI
- [ ] 4.2 `release.yml`: jobs `release-lib` and `release-mcp`, outputs per line, `concurrency`, `publish-pypi-lib` and `publish-pypi-mcp` with per-package file checks, crate/docs depending on `release-lib`, exact semantic-release package versions, and a `workflow_dispatch` dry-run input that runs both configurations with `--dry-run` and skips every publish job (design §3, §6); verify `actionlint` reports nothing and a dry-run dispatch on `beta` reports the versions expected by 2.4 without creating tags (`git ls-remote --tags origin` unchanged)
- [ ] 4.3 Run `scripts/release/dry-run.sh` and the `path-filter` tests in CI when release files change (`ci.yml`, path filter on `.releaserc*`, `scripts/release/**`, `release.yml`); verify the job passes on the pull request

## 5. Bootstrap and first release (on `beta`)

- [ ] 5.1 Tag `mcp-v0.0.0` on the current `origin/beta` head with note `{"channels":[null]}` in `refs/notes/semantic-release-mcp-v0.0.0` and push both (design §10 step 3; maintainer, after approval); verify `git ls-remote origin 'refs/*mcp-v0.0.0*'` lists the tag and the note
- [ ] 5.2 Merge the change with commit A (`ci(release): ...`) and commit B (`feat(mcp): own 0.x version line`) in one push to `beta`; verify the run releases `mcp-v0.1.0` pinning `simtest-funnel==1.0.0-beta.21`, no unexpected library release, a GitHub Release titled `simtest-funnel-mcp 0.1.0`, and `uvx --refresh simtest-funnel-mcp@0.1.0 --version` from PyPI prints `0.1.0` and `1.0.0b21`
- [ ] 5.3 Owner yanks `simtest-funnel-mcp` `1.0.0b12`–`1.0.0b21` on PyPI with the reason of design §1; verify `uv pip compile` of `simtest-funnel-mcp` with and without `--prerelease allow` selects `0.1.0` and the PyPI JSON lists the ten releases as yanked
- [ ] 5.4 Next library change on `beta`: verify the run releases the library pre-release and, in the same run, a server patch pinning it, uploaded after the library (job order in the run log)

## 6. Documentation

- [ ] 6.1 Server README: version line, `--version`, `uvx simtest-funnel-mcp@latest`, uv ≥ 0.12.0, changelog link, yanked `1.0.0bN` note (design §12); verify the text names each item of the spec "Versioning documented"
- [ ] 6.2 Root `README.md`: one paragraph on the two version lines; verify by review
- [ ] 6.3 `MAINTAINER.md`: both lines, tags and notes, path rule, dry run, per-line failure states and recovery, `main` → `beta` merge after stable library releases, the yank record; `AGENTS.md` "Releasing" and "Conventional Commits" (path rule, `mcp`/`skill` scopes); verify by review against design §3–§7 and §10
- [ ] 6.4 Check `.github/copilot-instructions.md` and `docs/` for release or version statements and update them; verify `grep -rn "1.0.0-beta\|same version" .github docs README.md python/simtest-funnel-mcp/README.md` finds nothing outdated

## 7. Integration checks

- [ ] 7.1 Run `make lint`, `make test` and `openspec validate split-mcp-versioning --strict`; verify all pass

## Workflow follow-up

- Tell the `add-claude-skill` change that the plugin pins the 0.x server version from `release-mcp`'s output (design §11).
- Archive after task 5.4 has been observed.
