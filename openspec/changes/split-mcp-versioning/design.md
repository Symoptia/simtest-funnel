# Design

## Context

See proposal.md (Why) for the motivation and the owner's binding decisions,
and the two spec deltas for the required behaviour. State before this
change:

- One semantic-release run (`.releaserc.json`, branches `main` and `beta`
  as pre-release) on every push to either branch. `prepareCmd` writes the
  version into `Cargo.toml`, both library `pyproject.toml` files and the
  server's, rewrites the server's pin `simtest-funnel==<version>`, and runs
  `scripts/release-refresh-lockfiles.sh` (`cargo update --workspace`,
  `uv lock`, then fails on any lockfile line change other than `version =`).
  Release commit `chore(release): X [skip ci]`, tag `vX`, one GitHub
  Release, npm publish inside semantic-release.
- After the tag, `python-wheels.yml` (reusable, `ref` input) builds 8 abi3
  wheels, the library sdist and the server's wheel and sdist, smoke-tests
  them (the server together with the fresh library wheel on 5 rows), and
  `publish-pypi` uploads everything with `twine` (library first,
  `--skip-existing`). `publish-crate` and `publish-docs` run in parallel.
- The uv workspace resolves `simtest-funnel` from the checkout, so the pin
  never appears in `uv.lock` (only the two `version = ` lines change on a
  release) and the repository's tests always run the server against the
  library at HEAD.
- The server's `__version__` comes from its distribution metadata and is
  passed to `MCPServer(..., version=__version__)`; `serverInfo.version`
  therefore already follows whatever version the package carries.
- `python-distribution` exists only in the in-flight change
  `add-cross-platform-wheels`; its delta here is MODIFIED, so that change
  must be archived first (validate reports this as an info).
- PyPI on 2026-11-22: `simtest-funnel-mcp` has `1.0.0b12` … `1.0.0b21`
  only, `simtest-funnel` has `1.0.0b3` … `1.0.0b21` only, nothing yanked.
  The local `beta` is one commit behind `origin/beta`
  (`chore(release): 1.0.0-beta.21`).
- semantic-release keeps the channel of each release in a git note
  `refs/notes/semantic-release-<tag>` (`{"channels":["beta"]}` on the
  remote for every `v1.0.0-beta.N`); a tag without a note is not found as a
  previous release on a pre-release branch (verified below).

### Verified by experiment on 2026-11-22

Scratch files: `/tmp/claude-1000/-workspaces-simtest-funnel/50c91c96-453d-4e72-b713-45ada178cdc1/scratchpad/version-split/`
(`fake/scenario.sh` builds a PEP 503 index with `data-yanked` entries from
throwaway wheels and resolves with uv and pip; `sr/` holds the
semantic-release dry runs). uv 0.11.25 (the repository's pinned uv) unless
stated, pip 25.0.1.

| # | Experiment | Observed |
| --- | --- | --- |
| E1 | Real PyPI: throwaway stable `tw-pin-sf 0.1.0` requiring `simtest-funnel==1.0.0b21`, `uv pip compile` (default) and `pip install --dry-run` with `--find-links` | Both install `simtest-funnel 1.0.0b21`. A stable package's exact pin of a pre-release resolves while the library has **only** pre-releases. |
| E2 | Real PyPI: `tw-pin-pandas 0.1.0` requiring `pandas==3.1.0rc0` (pandas has stable releases) | **uv 0.11.25 fails** ("pre-releases weren't enabled"); pip installs `pandas 3.1.0rc0`. Adding the library as a first-party requirement (`pandas==3.1.0rc0` next to it) makes uv 0.11.25 resolve. |
| E3 | Local index, library with `1.0.0` and `1.0.1b1`, server `0.2.0` (stable) or `0.2.0b1` pinning `==1.0.1b1`, uv 0.11.25 / 0.11.29 / 0.11.33 / 0.12.0 / 0.12.12 / 0.13.0 / 0.13.9 | Fails with every 0.11.x tried, resolves with every version from **0.12.0** (2026-07-28) on, for both the stable and the pre-release server. `uvx --from server==0.2.0b1 --with lib==1.0.1b1` and `--prerelease allow` work on 0.11.25; `--prerelease explicit` and `if-necessary` do not. |
| E4 | Local index: server `1.0.0b20`, `1.0.0b21`, `0.1.0` (stable), none yanked | uv default and pip default: `0.1.0`. `--prerelease allow` / `pip --pre`: `1.0.0b21`. |
| E5 | Server `1.0.0b21` and `0.1.0b1` (pre-release), none yanked | uv default and pip default: **`1.0.0b21`** (all versions are pre-releases, so both fall back to the highest one). A 0.x beta line without a yank never reaches plain `uvx`. |
| E6 | `1.0.0bN` yanked, `0.1.0b1` or `0.1.0` present | uv and pip, default and with pre-releases allowed: the 0.x version. |
| E7 | `1.0.0bN` yanked, request `==1.0.0b21` | uv and pip install it with a yank warning; `uvx server@1.0.0b21` works too (the `@` form accepts a PEP 440 pre-release string). A range `>=1.0.0b1` that only yanked versions satisfy fails in both. |
| E8 | `uvx fakemcp` with `1.0.0b21` cached, then the index changed to yanked `1.0.0bN` + `0.1.0` | Plain `uvx fakemcp` kept running `1.0.0b21`; `uvx fakemcp@latest` switched to `0.1.0`, and plain `uvx` used `0.1.0` afterwards. |
| E9 | semantic-release 25.0.9 dry runs (`--dry-run --no-ci`, local bare remote) with two configs and a local path-filter plugin (`sr/path-filter.mjs`) | Library config (`tagFormat v${version}`, server paths excluded) on `beta`: `1.0.0-beta.22` from a `fix` outside the server. Server config (`tagFormat mcp-v${version}`) with a bootstrap tag `mcp-v0.0.0`: `0.1.0-beta.1` on a pre-release `beta`, `0.1.0` on `main` once the tag's note lists channel `null`. A pin change with no server commit gave a patch (`0.1.0-beta.2`). `releaseRules [{breaking: true, release: "minor"}]` with the `conventionalcommits` preset turned `feat(mcp)!:` into a minor. The default (angular) preset, used by today's config, does **not** recognise `!` at all. The `conventionalcommits` preset's latest major refused to render notes with the writer bundled by the latest release-notes-generator (versions must be pinned together). Without a note, a tag is not found as a previous release on the pre-release branch. |

### Documentation read on 2026-11-22

| URL | What it established |
| --- | --- |
| https://docs.astral.sh/uv/concepts/resolution/ | Current docs: default strategy `if-necessary`, falling back to pre-releases "only if every stable candidate that satisfies the active constraints is rejected"; `explicit` mode only for first-party requirements; `--prerelease-package foo=allow` (not present in uv 0.11.25's help). Matches E3: the behaviour depends on the user's uv version. |
| https://docs.pypi.org/project-management/yanking/ | Yanking is "a non-destructive alternative to deletion"; installers skip a yanked release unless it is the only one matching an `==` / `===` specifier; done in the web UI (release Options → Yank) with an optional reason shown on the release page and in the index APIs. No API is mentioned. |
| https://docs.pypi.org/project-management/storage-limits/ , https://docs.pypi.org/project-management/troubleshooting/ | Deletion "is permanent and cannot be undone without administrative intervention"; deleted files cannot be re-uploaded (a version's file names stay used after deletion as after a yank). |
| PyPI JSON API, e.g. https://pypi.org/pypi/httpx/json | `info.version` (the version PyPI shows as current) is the highest **final** release when one exists: httpx shows `0.28.1` although `1.0.dev6` exists. A stable server `0.1.0` would therefore show as current even without a yank. |
| https://raw.githubusercontent.com/modelcontextprotocol/registry/main/docs/modelcontextprotocol-io/versioning.mdx | Registry versions must be unique and immutable; ranges (`^1.2.3`, `1.x`) prohibited; semver recommended; "latest" by semver sort; aligning the server version with the package version is advised. |
| https://raw.githubusercontent.com/semantic-release/github/master/README.md | `@semantic-release/github` has `releaseNameTemplate` and `releaseBodyTemplate`. |

## Goals / Non-Goals

**Goals:**

- Plain `uvx simtest-funnel-mcp` (no cached environment) installs the
  newest server on every uv version currently in use, and nothing a
  resolver shows as "latest" points at the abandoned `1.0.0bN` line.
- One push never leaves PyPI with a server whose pin cannot be installed.
- The release workflow can be rehearsed without publishing.

**Non-Goals:**

- No change to how the library line is numbered, published or announced,
  apart from no longer touching the server.
- No support for users of the `1.0.0bN` server (owner decision).
- No pre-release channel for the server (see §1).

## Decisions

Items marked **(not yet confirmed by the owner)** are design choices with a
recommendation. The tasks follow the recommendation; changing one changes
only the named tasks.

### 1. Version ordering: yank `1.0.0bN`, release stable 0.x from `beta` (not yet confirmed by the owner)

The headline choice. Options, with the consequences established above:

| Option | Plain `uvx` | Pre-releases allowed / "latest" tools | Other consequences |
| --- | --- | --- | --- |
| A. Stable 0.x, no yank | `0.1.0` (E4) | `pip --pre`, `uv --prerelease allow`, Renovate/Dependabot for a pre-release pin and any "highest version" listing see `1.0.0b21` (E4); PyPI's page shows `0.1.0` | Simplest, but the old line stays live for every pre-release-enabled tool. |
| B. Server pre-releases `0.1.0bN` on `beta` (mirroring the library), no yank | **`1.0.0b21`** (E5) | `1.0.0b21` | Broken: 0.x never reaches anyone until a stable server exists. |
| C. B plus yank | `0.N.0bK` (E6) | 0.x | Works; stable server only once `main` is released, i.e. together with library 1.0.0; after that the beta channel needs `--prerelease allow` or `--with simtest-funnel==V` on uv < 0.12 (E3), and every server pre-release has a semver string (`0.3.0-beta.2`) that differs from its PEP 440 string (`0.3.0b2`). |
| D. Stable 0.x from `beta` plus yank (**recommended**) | `0.N.M` (E4, E6) | 0.x (E6) | Owner's "0.x, may pin a beta library" literally; one server channel; semver and PEP 440 strings identical (`0.3.0`), which also suits the MCP registry and the plugin. After the library has a final release, a server pinning a library pre-release needs uv ≥ 0.12.0 or pip (E3). |
| E. Start above: `1.1.0`, `2.0.0` or CalVer `2026.11.0` | newest (sorts above `1.0.0b21`) | newest | No yank needed. Contradicts the owner's "0.x"; `1.x`/`2.x` promise stability the tool surface does not have; CalVer drops the breaking-change signal. Only with the owner's agreement. |
| F. Delete instead of yank (combined with A, C or D) | as with yank | the files are gone for everyone, including mirrors that sync deletions | Irreversible, breaks exact pins (`uvx --from simtest-funnel-mcp==1.0.0b21`, still working after a yank, E7), frees no version number (file names cannot be reused), PyPI recommends yanking. No benefit over yanking here. |

What a yank does and does not do (E6–E8, PyPI docs): resolvers skip the
yanked versions for unpinned and range requirements, also with
pre-releases allowed; exact pins still install them with a warning; PyPI
keeps the files and shows them as yanked with the reason; it is a web-UI
action of a project owner (no API), reversible; it does **not** update an
existing `uvx` cached environment (E8: users who ran `uvx
simtest-funnel-mcp` before keep `1.0.0b21` until `uvx
simtest-funnel-mcp@latest` or a cache clean), and it does not free the
version numbers (the server's own future 1.0 pre-releases must not be
`1.0.0bN`; use `1.0.0rc1` or none).

Recommendation D: the server line releases final 0.x versions on pushes to
`beta` only; after server `0.1.0` is on PyPI the owner yanks `1.0.0b12` …
`1.0.0b21` with the reason "Superseded by the 0.x line: simtest-funnel-mcp
0.1.0 and later". The yank comes after `0.1.0` because with every version
yanked a plain install finds nothing (E7). Not deleted (F).

The exact pin of a library pre-release by a final server (the owner's
question) is safe today on every uv and pip version (E1), because the
library has only pre-releases. Once the library has a final release
(1.0.0), a server pinning a later library pre-release resolves with pip and
uv ≥ 0.12.0 but not with uv 0.11.x (E3). The README therefore states uv ≥
0.12.0 as the minimum, the server smoke installs the pin as a first-party
requirement so the pinned uv 0.11.25 of the workflows is not a problem, and
whether final servers keep pinning library betas after 1.0.0 is left to
the owner then (Open Questions). Option C is the fallback if the owner
wants no final server before library 1.0.0; it changes §3 and tasks 2.2
and 2.3.

### 2. Commit assignment by path, with a local plugin (not yet confirmed by the owner)

semantic-release analyses every commit since the last tag of its
`tagFormat`; it has no path filter. A local plugin
(`scripts/release/path-filter.mjs`, about 50 lines, E9) wraps
`@semantic-release/commit-analyzer` and `release-notes-generator`, keeps
only the commits whose changed files (`git diff-tree`) match the line's
include/exclude prefixes, and for the server line forces at least a patch
when the pin would change (§4). Server set: `python/simtest-funnel-mcp/`
and `plugins/simtest-funnel/` (the plugin's version equals the server's,
`add-claude-skill` §6, so skill edits must cut a server release). Library
set: everything else except `uv.lock`, which no published artifact uses
(the abi3 wheels use `Cargo.lock`; the server wheel is pure Python).

Alternatives: scope-based rules (`feat(mcp)` → server) are possible with
`releaseRules`, but depend on every author choosing the scope right and
cannot express "touches both"; scopes stay a convention for readers
(`mcp`, `skill`, `core`, `python`, `sdk`). `semantic-release-monorepo`
filters by one package directory and cannot express "everything except the
server". multi-semantic-release and release-please would replace the
release tooling (release-please also changes the flow to release PRs),
which is out of proportion for one extra line.

### 3. Two release configurations and jobs

- `.releaserc.json` stays the library config: same branches and plugins,
  `tagFormat "v${version}"`, path filter (exclude the server set),
  `prepareCmd` without the server lines, git assets without the server's
  `pyproject.toml`. `successCmd` writes `.release-version` as today.
- `release-mcp.config.cjs` (or JSON): `branches: ["beta"]`, `tagFormat
  "mcp-v${version}"`, path filter (include the server set), preset
  `conventionalcommits` with `releaseRules [{breaking: true, release:
  "minor"}]`, changelog file `python/simtest-funnel-mcp/CHANGELOG.md`,
  `prepareCmd` = `scripts/release/pin-library.sh` (§5) + version into the
  server's `pyproject.toml` + `release-refresh-lockfiles.sh`, git assets
  (server `pyproject.toml`, server changelog, `uv.lock`), message
  `chore(release): simtest-funnel-mcp ${version} [skip ci]`,
  `@semantic-release/github` with `releaseNameTemplate
  "simtest-funnel-mcp <%= nextRelease.version %>"`, no npm.
  On `main` semantic-release reports that it is not configured for the
  branch and exits successfully.
- `release.yml`: job `release-lib` (today's job, unchanged steps) → job
  `release-mcp` (`needs: release-lib`, fresh checkout of the branch head,
  gets `LIB_RELEASED_VERSION` from `release-lib`'s outputs). Separate jobs
  so that a failure in the server step cannot stop the library's wheels
  (spec "PyPI upload gated on the pinned library"). A workflow-level
  `concurrency: release-${{ github.ref }}` (no cancel) serialises runs, so
  a push arriving between the two jobs is released by its own run.
- The npm, crate and docs jobs depend on `release-lib` only. The docs
  site has no server content beyond links.
- Pin all semantic-release packages to exact versions in the workflow
  (today `npm install -g semantic-release …` takes the newest; E9 showed
  the preset and writer must match).

Alternative: one job running both configurations back to back. Simpler,
but a failing server prepare (e.g. the guard of §5) would fail the job
after the library tag was pushed and skip the library's wheel builds.

### 4. Library patches reach server users automatically (not yet confirmed by the owner)

The pin is exact (owner decision), so a library release reaches `uvx
simtest-funnel-mcp` users only through a new server release. The server
config releases at least a patch whenever the library version on the
branch differs from the pin (E9), with a generated note "Pins
simtest-funnel X". Consequence: every library release on `beta` is
followed in the same run by a server patch; server patch numbers grow
with library pre-releases, which 0.x tolerates.

Alternative: manual (`fix(mcp): pin simtest-funnel X`). Fewer server
releases, but library fixes silently do not reach server users until
someone remembers.

On `main` (library stable releases) no server release happens (§1). The
stable library version reaches the server when `main` is merged back into
`beta` (the version files change there), and that push releases the
server patch. A `main` → `beta` merge after each stable release is
therefore part of the procedure in `MAINTAINER.md`.

### 5. Which library version is pinned, and the PyPI guard

The pin is the `version` of `crates/simtest-funnel-python/pyproject.toml`
at the server job's checkout: the library's own `prepareCmd` writes it, so
it is the latest library release on that branch, including one made by
`release-lib` in the same run. `scripts/release/pin-library.sh` writes
`simtest-funnel==<V>` into the server's `pyproject.toml` and then checks
availability: if V equals `LIB_RELEASED_VERSION` it passes (the upload
order guarantees the library goes first); otherwise it requires
`https://pypi.org/pypi/simtest-funnel/<PEP 440 V>/json` to answer 200 with
files. A failure stops semantic-release in `prepare`, before the commit,
tag and GitHub Release (spec "No server tag for an unavailable library").

Alternative: run the server release only after `publish-pypi` of the
library. It needs no guard for the same-run case, but delays every server
release by the wheel matrix, and a push landing meanwhile makes
semantic-release skip the release (local branch behind remote).

### 6. Wheel workflow and upload

`python-wheels.yml` takes `lib_ref` and `mcp_ref` (either may be empty;
manual runs and pull requests build both from the selected ref). Library
jobs (`sdist`, `build`, `smoke`) run when `lib_ref` is set; the server
wheel/sdist build and a new `smoke-mcp` job (Linux x86-64, macOS arm64,
Windows x64 rows) run when `mcp_ref` is set. `smoke-mcp` installs the
server wheel plus the library: the fresh wheel artifact when the library
released in the run, otherwise `simtest-funnel==<pin>` from PyPI, given as
a first-party requirement (E2/E3: works with the pinned uv 0.11.25 even
after library 1.0.0). The library `smoke` job no longer starts the server.

`release.yml`: `publish-pypi-lib` (needs the library jobs) and
`publish-pypi-mcp` (needs the server jobs and, when the library released,
`publish-pypi-lib`), each with today's file-set check for its package,
`twine check --strict` and `--skip-existing`. Recovery stays "re-run the
failed jobs" (everything builds from tags); a server version whose build
cannot be fixed is simply absent from PyPI and the next server release
supersedes it.

### 7. Lockfile guard

`release-refresh-lockfiles.sh` is called by both `prepareCmd`s unchanged:
in the library run `cargo update --workspace` and `uv lock` change the
library entries; in the server run only the `simtest-funnel-mcp`
`version =` line of `uv.lock` changes (the pin is not in `uv.lock`, see
Context), and `Cargo.lock` stays as it is. The guard's rule (only
`version = "…"` lines may change) holds for both. The server run's git
diff is taken against the library release commit when both released.

### 8. Versions shown to users

`serverInfo.version` already follows the package version, so it becomes
`0.x` without code. `--version` adds the installed library version
(`simtest-funnel-mcp 0.3.0 (simtest-funnel 1.0.0b22)`), so a bug report
names both. The User-Agent of URL fetches keeps the server version only.
The pytest snippet header already names both versions.

### 9. Changelogs and GitHub Releases

Root `CHANGELOG.md` continues for the library; its earlier `1.0.0-beta.N`
entries keep their server items. `python/simtest-funnel-mcp/CHANGELOG.md`
starts with a header pointing to the root changelog for the history before
0.1.0. GitHub Releases: library ones as today (`v1.0.0-beta.N`, marked
pre-release on `beta`), server ones titled `simtest-funnel-mcp X` on
`mcp-vX`. Because server releases are final, GitHub's "Latest release"
badge will point at the newest server release while the library is in
beta (accepted; the README badges point at the registries).

### 10. First split release on `beta` (migration)

1. Owner confirms §1, §2, §4 (and the plugin's reading, §11).
2. Commit A, type `ci(release)` (releases neither line): both
   configurations, the path-filter plugin, `pin-library.sh`, workflow
   changes, server `pyproject.toml` version `0.0.0` (the pin stays
   `1.0.0-beta.21`), the server changelog header, `--version`, docs.
3. Before pushing A: tag `mcp-v0.0.0` on A's parent (the current
   `origin/beta` head) with the note `refs/notes/semantic-release-mcp-v0.0.0`
   = `{"channels":[null]}`, pushed with the tag (E9: without the note the
   tag is not found). This is the server line's base; nothing is
   published for it.
4. Dry run of the release workflow on `beta` (spec "Release dry run"):
   expect library "no release" and server `0.1.0` pinning `1.0.0-beta.21`.
5. Commit B, `feat(mcp): own 0.x version line` (the README section on
   versions), pushed with A. The run releases server `0.1.0` (minor from
   0.0.0) pinning `simtest-funnel==1.0.0-beta.21` (on PyPI, the guard
   passes); no library release unless other library commits are pending.
6. Check from PyPI: `uvx --refresh simtest-funnel-mcp@0.1.0 --version`,
   `uv pip compile` of `simtest-funnel-mcp` → `0.1.0`.
7. Owner yanks `1.0.0b12` … `1.0.0b21` (web UI, reason as in §1); check
   that `uv pip compile --prerelease allow` now selects `0.1.0`.
8. `add-claude-skill` proceeds with its plugin pinned to the 0.x version.

Rollback: revert A and B and yank `0.1.0` (otherwise plain `uvx` keeps
choosing the final `0.1.0` over any later `1.0.0bN`, E4); if step 7 has
happened, undo those yanks in the web UI.

### 11. What the plugin reads (add-claude-skill dependency)

The plugin pins the server's 0.x version, never the library's. Its
`publish-plugin` job runs after `publish-pypi-mcp`, only when the server
line released, and takes the version from `release-mcp`'s output (the
same as `python/simtest-funnel-mcp/pyproject.toml` at tag `mcp-vX`).
Plugin `version` = server version, as that design wants; the `--from
'simtest-funnel-mcp==X'` form stays (E7 also showed `@X` works with PEP 440
strings). Because the server releases only from `beta`, plugin pins on
`main` arrive by merge. The MCP registry entry (its step C) uses the same
0.x version for `version` and the PyPI package version, exactly (ranges are
prohibited), and is never published for `1.0.0bN`. **Not yet confirmed by
the owner**, together with §1.

### 12. Documentation

- `python/simtest-funnel-mcp/README.md`: own 0.x line, `--version`, `uvx
  simtest-funnel-mcp@latest` to leave a cached version, uv ≥ 0.12.0,
  changelog link; the `1.0.0bN` releases are yanked.
- Root `README.md`: the two lines in one paragraph.
- `MAINTAINER.md`: both lines, tags and notes, path rule, the dry run,
  failure states and recovery per line, the `main` → `beta` merge after a
  stable library release, the yank record.
- `AGENTS.md` "Releasing" and "Conventional Commits": path rule, scopes
  `mcp`/`skill`, `!` handled for the server line.
- `.github/copilot-instructions.md` if it describes releases.

## Risks / Trade-offs

- [The local path-filter plugin couples to semantic-release's plugin API]
  → Exact versions pinned in the workflow; a unit test (node:test) and the
  dry-run harness run in CI when release files change.
- [A library commit with a non-releasing type that a server change relies
  on] → The server would pin an older library. `smoke-mcp` installs the
  pinned version, so a missing function fails the server build before
  upload.
- [uv < 0.12 after library 1.0.0] → README minimum; the owner decides then
  whether final servers may pin library betas (Open Questions).
- [Cached `uvx` environments keep `1.0.0b21`] → Accepted (beta users are
  not protected); the README and the yank reason name `@latest`.
- [Two release jobs push to the branch in one run] → Serialised in one
  workflow with `concurrency`; `release-mcp` checks out the head after
  `release-lib`.
- [GitHub "Latest release" shows server releases] → Accepted (§9).
- [Server patch releases for every library pre-release] → Intended (§4).

## Open Questions

- After library 1.0.0: keep final servers pinning library pre-releases
  (needs uv ≥ 0.12), or pin only final library versions and offer the
  beta library some other way. Decided when 1.0.0 is near; it changes only
  the pin script's input, not this structure.
- Whether `.github/copilot-instructions.md` mentions releases (checked in
  task 6.4).
