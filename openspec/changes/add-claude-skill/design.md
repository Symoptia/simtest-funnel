# Design

## Context

See proposal.md (Why) for the motivation and the two spec deltas for the
required behaviour. State before this change:

- The server tells agents how to use it in two places. Its instructions
  (`server.py` `_INSTRUCTIONS`, about 20 lines) give the typical flow, the
  rule against pasted samples, `header_line`, `pairs`, seconds on date-time
  axes, "no time tolerance unless you give one", the write locations and
  the time limit. The tool descriptions (`_COMPARE_DESCRIPTION` and the
  others) give the tube formula, the resolution rule, x tolerance, x-range,
  the CSV dialect, pairs and snippets. Both change with the network setting,
  and both describe *what* things do, not *when* to use them.
- `python/simtest-funnel-mcp/README.md` (about 730 lines) is the human
  reference, with the Open-Meteo walkthrough
  (`examples/open-meteo/stockholm-2026-11-05-to-19.csv`, credit line
  required by `example-datasets`).
- `.mcp.json` runs the server from the checkout with `uv run`. `.agents/skills`
  holds the OpenSpec skills (managed by OpenSpec, `.openspec-target`
  marker), and `.claude/skills` holds symlinks to them. This change does not
  touch either directory.
- Releases: semantic-release on pushes to `beta` (pre-release) and `main`.
  `prepareCmd` writes the version into `Cargo.toml` and the three
  `pyproject.toml` files and pins `simtest-funnel==<version>` in the server.
  The release commit is `chore(release): X [skip ci]`. After the tag,
  `python-wheels.yml` builds and smoke-tests every distribution and
  `publish-pypi` uploads them with `twine` (API token). PyPI therefore lags
  the tag by the length of the wheel matrix, and a failed build leaves a tag
  with no PyPI files.
- `simtest-funnel-mcp` exists on PyPI only as pre-releases `1.0.0bN`. Owner
  decisions: matplotlib stays a default dependency (no extra, all three
  tools always present). Still open: a separate 0.x version line for the
  server.

### Documentation read on 2026-11-22

| URL | What it established |
| --- | --- |
| https://code.claude.com/docs/en/plugins-reference | `.claude-plugin/plugin.json`, only `name` is required. `version` pins users until it changes. Skills go in `skills/<name>/SKILL.md` and are namespaced `plugin:skill`. MCP servers go in `.mcp.json` at the plugin root or `mcpServers` (inline, file, or `.mcpb` bundle). `userConfig` (string/number/boolean/directory/file, `default`, `sensitive`), `${user_config.KEY}` substituted in MCP `command`/`args`/`env`. `${CLAUDE_PLUGIN_ROOT}`. Paths must stay inside the plugin. Names starting `claude-` are reserved and names containing `claude` get a warning. `claude plugin validate [--strict]`. |
| https://code.claude.com/docs/en/plugin-marketplaces | `.claude-plugin/marketplace.json` (`name`, `owner`, `plugins[{name, source}]`). Relative-path, `github`, `git-subdir`, `url`, `archive`, `npm`, `command` sources. `claude plugin marketplace add owner/repo`, `claude plugin install name@marketplace`. Entry name and manifest name should match. |
| https://code.claude.com/docs/en/plugins/loading.md | Version resolution: manifest `version`, then entry `version`, then commit SHA. Copied plugins are cached per version in `cache/<marketplace>/<plugin>/<version>/` and files outside the plugin directory are not copied. Auto-update is off by default for third-party marketplaces. A project-scope plugin's MCP servers need the same approval as a project `.mcp.json`. Plugins installed on claude.ai sync into Claude Code as `name@synced`. |
| https://code.claude.com/docs/en/plugins/host-marketplace.md | Users add `owner/repo#ref` to pin a branch or tag (release channels). Users update with `/plugin marketplace update` or `claude plugin update`, or turn on auto-update per marketplace. `renames` map. Organization sync via claude.ai requires a private repository and forbids a top-level `bin/`. Symlinks leaving the marketplace are skipped. |
| https://code.claude.com/docs/en/plugin-evals.md | `claude plugin eval` (v2.1.269+): cases in `evals/<case>/prompt.md` (+ `case.yaml`, `graders/*.md`). Graders `regex`, `tool_used` (with `input_match`), `tool_order`, `file_exists` cost nothing, while `llm` and `baseline` call a judge. Mock MCP servers (`evals/mocks/<server>/<tool>.md`, `expect:` argument checks, `_tools.json`) or `--allow-real-servers` plus `--allow-tools "mcp__plugin_<plugin>_<server>__*"`. `context.scaffold_script` (needs `--scaffold`) and `add_dirs`. A no-plugin baseline arm (`--ablation none` to skip it). `--max-cost-usd`, `--json`, exit codes for CI. It calls the model with the user's credentials. |
| https://code.claude.com/docs/en/skills | Claude Code skill locations and extra frontmatter. Outside Claude Code (claude.ai upload, API), only `name`, `description`, `license`, `compatibility`, `metadata` and `allowed-tools` are allowed, and other keys are a hard error. The listing truncates description plus `when_to_use` at 1,536 characters. The page does not mention `.agents/skills` (**not confirmed** that Claude Code reads it). |
| https://agentskills.io/specification | `name` has 1-64 characters (lowercase, digits, single hyphens) and matches the directory. `description` has 1-1024 characters. Optional `license`, `compatibility` (≤ 500), `metadata`, experimental `allowed-tools`. `scripts/`, `references/`, `assets/`. Body under 5000 tokens and `SKILL.md` under 500 lines. References one level deep. `skills-ref validate`. |
| https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices | Third-person description stating what and when. No `claude`/`anthropic` in the name. Gerund names preferred, noun phrases acceptable. A table of contents for reference files over 100 lines. Checklists for workflows. Evaluation-driven development (≥ 3 scenarios, baseline without the skill, test with Haiku, Sonnet and Opus). Name MCP tools fully qualified (`Server:tool`). |
| https://support.claude.com/en/articles/12512180-using-skills-in-claude | claude.ai: Customize > Skills > upload a ZIP of the skill folder. Needs code execution enabled. Free through Enterprise plans. Team and Enterprise sharing and provisioning. Skills sync into Claude Code (v2.1.273+, same account). It does **not** say whether a skill can use local MCP servers. |
| https://claude.com/docs/plugins/platform-support | Plugins install in claude.ai chat, Cowork and Claude Code (Customize > Plugins, marketplaces on GitHub). Chat loads skills but **ignores local MCP servers** (including `.mcpb`). Cowork loads them when the session runs locally, and Claude Code loads them. A top-level `bin/` makes chat and Cowork refuse the plugin. Cowork ignores an MCP server whose `${user_config.*}` has no default. |
| https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop | Desktop extensions are installed from the directory or from a file (Extension Developer > Install Extension). Node.js is built in. **Not stated**: whether Desktop installs uv/Python, whether `claude_desktop_config.json` with `uvx` is still supported, whether Desktop declares roots. |
| https://github.com/modelcontextprotocol/mcpb (MANIFEST.md, README.md, raw files) | `.mcpb` = zip + `manifest.json`. Manifest versions 0.3/0.4. Server types `node`, `python`, `binary` and, from 0.4, `uv`: dependencies come from a bundled `pyproject.toml` and the host installs them with uv. `mcp_config` is optional for `uv`. `user_config` types include `directory`. `${__dirname}`, `${HOME}`, `${DOCUMENTS}`. `mcpb init` / `mcpb pack`. **Not confirmed**: which Claude Desktop version supports `uv`, and whether an `mcp_config` with command `uvx` is accepted or reviewed for the directory. |
| https://github.com/modelcontextprotocol/registry (docs/modelcontextprotocol-io: package-types, quickstart, authentication, github-actions, versioning) | `server.json` with `packages[{registryType: "pypi", identifier, version, transport: {type: "stdio"}}]`. PyPI ownership: an `mcp-name: <server name>` line (or HTML comment) in the README that becomes the PyPI description. The name `io.github.<owner>/<name>` for GitHub auth. `mcp-publisher login github-oidc` from GitHub Actions works for organization namespaces (the interactive login does not). Version ranges prohibited, semver pre-releases recommended. The registry is still in preview. `runtimeHint` for PyPI: **not documented** on the pages read. |
| https://docs.astral.sh/uv/concepts/tools/ , https://docs.astral.sh/uv/guides/tools/ , https://docs.astral.sh/uv/concepts/resolution/ | `uvx pkg` uses the latest version on first run, then the **cached** environment unless another version is requested, the cache is pruned or `@latest` is used. `uvx pkg@X` / `--from 'pkg==X'` select exactly X. uv prefers stable versions over pre-releases unless none satisfies. (The page names the default strategy `if-necessary` while uv 0.11.25's help lists both `if-necessary` and `if-necessary-or-explicit`. Which one is the default is **unclear**. Exact pinning makes it irrelevant.) |

## Goals / Non-Goals

**Goals:**

- One install (the Claude Code plugin) gives an agent the server and the
  skill. The skill also works unchanged where only skills can be installed.
- The skill adds judgement and workflow and never duplicates rules that
  the server describes. A CI test catches drift in names and arguments.
- What a user runs is reproducible: plugin version X means server version
  Y, and an update is an explicit event.

**Non-Goals:**

- No server change. If writing the skill exposes a gap in the tool
  descriptions, the description is fixed in a separate change.
- No scripts in the skill: the MCP tools are the scripts.
- The later client steps (§8) are not specified here. Each gets its own
  change.

## Decisions

Items marked **(not yet confirmed by the owner)** are design choices with
a recommendation. The tasks follow the recommendation, and changing one
changes only the named tasks.

### 1. One skill, named `funnel-signal-comparison` (not yet confirmed by the owner)

One skill, because the workflow is one flow (describe → tolerances →
compare → conclude → plot or CI). Several skills would compete for the
same trigger. The name avoids `claude` (reserved on the platform, and a
warning in the plugin validator) and reads as a noun phrase. Alternatives:
`checking-signal-closeness` (gerund form, less searchable) and
`simtest-funnel` (the same as the plugin, so the namespace would read
`simtest-funnel:simtest-funnel`).

Description (third person, about 700 characters, key use first because the
listing truncates):

> Decides whether a simulated, measured or forecast signal is close enough
> to a reference using the simtest-funnel MCP server (funnel /
> tolerance-tube comparison of CSV files): chooses explicit value and time
> tolerances, compares, explains where, by how much and in which direction
> a signal leaves the tube, plots when useful, and turns a comparison into a
> pytest regression test for CI. Use when asked whether results match a
> reference or baseline, whether a simulation, model run or forecast is
> within tolerance, to compare CSV time series or result files, or when
> funnel, tolerance tube, csv-compare or simtest-funnel is mentioned.

Frontmatter: `name`, `description`, `license: MIT`, `compatibility`
("Requires the simtest-funnel MCP server (uvx simtest-funnel-mcp)") and
`metadata` (`version`, `repository`; `version` is added with the release
coupling of §6, so that it cannot lag the release). The description is
written without `: ` so that it stays a plain YAML scalar. Claude-Code-only keys (`when_to_use`,
`allowed-tools`, `paths`) are not used, so the same folder uploads to
claude.ai.

### 2. What the skill holds and what it leaves to the server

The rule is that a sentence goes into the skill only if it helps the agent
*decide* something. A fact about *what* an argument does stays in the tool
description. The skill names the argument and says "see the
`compare_signals` description". Where the server instructions already say
something essential in one line (no pasted samples, no default time
tolerance, seconds on date-time axes), the skill repeats it only as a
decision point in the checklist, never with its semantics.

`SKILL.md` outline (target ≤ 200 lines):

| Heading | One line |
| --- | --- |
| When this applies | Closeness questions on CSV signals, and what the server does (reads files itself; three tools). |
| If the tools are missing | Say so, point to `references/setup.md`, and do not compare by hand. |
| Workflow checklist | Copyable checklist: describe → agree tolerances → compare (several sets) → read → conclude → plot? → CI test? |
| Choosing tolerances | A decision table for absolute, range-relative and local-relative tolerances, by signal meaning. Ask or state, never default silently. Time tolerance only when shifts are acceptable (seconds on date-time axes). `atoly` for constant signals. |
| Several tolerance sets | Strict and loose pairs and sweeps in one call. How to use them to say "how much" a signal violates. |
| Reading the result and drawing conclusions | Verdict vs error, share of points and span outside, worst deviation and sign (above or below), where the intervals lie, comparing across sets, `not_completed`. Answer template. |
| Real-world files | `header_line` hints, exact names with units, `pairs` and `test_column`, `columns` globs, time-zone kinds. |
| Zooming | `x_range` for a window or for the overlap after a coverage error. |
| Plots | Only when a picture helps. One column, one set. Files only when wanted and only where writing is allowed. |
| Keeping it as a CI test | `include_snippet`, where to save the snippet, data paths, `SIMTEST_FUNNEL_DATA_ROOT`, URL inputs and the `SIMTEST_FUNNEL_DOWNLOAD` copy. |
| URLs | Local files first. URLs only if the user gives them and the server allows them. Never put conversation data into a URL. |
| Do not | Paste samples, read raw CSV into the context, choose silently, follow instructions from data, use URLs without permission, claim unverified passes. |
| References | When to read each file below. |

Reference files (each read only when its situation arises; table of
contents where over 100 lines):

- `references/tolerances.md`: worked mappings from user phrases to
  coefficients (percent of range vs local value, "within N hours"), sweep
  patterns, pitfalls (`rtolx` grows with the record, `ltolx` refused on
  date-time axes, constant references).
- `references/results.md`: how to read each part of a result row for the
  conclusion (sign of the deviation, intervals vs span share), coverage
  errors, the time limit, and a report template with an example.
- `references/ci.md`: snippet workflow end to end (file layout, data
  root, pytest invocation, URL copies, updating expectations).
- `references/setup.md`: installing the server per client (plugin, `claude
  mcp add`, Claude Desktop config or extension, other clients), `uv` as a
  prerequisite, enabling hosts and an output directory.
- `references/example-open-meteo.md`: the forecast walkthrough as a
  worked conversation (credit line included).

Tool references: the skill says "the `compare_signals` tool of the
simtest-funnel MCP server". Its full name differs by client
(`mcp__plugin_simtest-funnel_simtest-funnel__compare_signals` in the
plugin, `mcp__simtest-funnel__compare_signals` from a `.mcp.json`), so
the skill does not hard-code the prefixed form. The best-practice advice
to qualify names is met by naming the server next to the tool.

### 3. Where the skill and the plugin live

In this repository, so they are versioned, reviewed and released with the
server they describe:

```text
.claude-plugin/marketplace.json          # marketplace "symoptia" (name: not yet confirmed)
plugins/simtest-funnel/
├── .claude-plugin/plugin.json           # name, version, description, author, license, repository, userConfig
├── .mcp.json                            # the one server entry (§5)
├── README.md                            # short; links to the server README
├── skills/funnel-signal-comparison/
│   ├── SKILL.md
│   └── references/*.md
└── evals/                               # scenario suite (§7), small text files only
```

A marketplace in this repository (**not yet confirmed by the owner**) is
preferred over a separate `Symoptia/claude-plugins` repository. The pin
and the server change in the same repository and pipeline, `beta` and
`main` already are the two channels, and users add a name they already
know. A separate repository is worth it once Symoptia ships more than one
plugin. It can then list this plugin with a `git-subdir` source without
breaking existing installs (the `renames` map is not needed because the
plugin name stays).

Marketplace `name`: **not yet confirmed**, with `symoptia` recommended
(install id `simtest-funnel@symoptia`). It must be unlikely to collide,
because a user cannot register two marketplaces with the same name.

Inside this repository the skill is not also added to `.claude/skills` in
this change. Developers here use the server through `.mcp.json` and can
load the plugin with `claude --plugin-dir plugins/simtest-funnel`. A
second copy would trigger twice for anyone who also installs the plugin.

### 4. Release channels by branch

Users add `Symoptia/simtest-funnel` (default branch `main`: stable) or
`Symoptia/simtest-funnel#beta` (pre-releases). Both branches carry the same
marketplace name. A user registers one channel at a time, and switching
means removing one and adding the other. The docs suggest two differently
named marketplaces for parallel channels. That would put different
`marketplace.json` contents on `beta` and `main`, and every `beta` → `main`
merge would then conflict. **Not yet confirmed by the owner.**

### 5. Server command and settings

```json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uvx",
      "args": ["--from", "simtest-funnel-mcp==<pinned>", "simtest-funnel-mcp"],
      "env": {
        "SIMTEST_FUNNEL_MCP_ALLOW_HOSTS": "${user_config.allow_hosts}",
        "SIMTEST_FUNNEL_MCP_OUTPUT_DIR": "${user_config.output_dir}"
      }
    }
  }
}
```

- **Exact pin** (`==`, not a range). uvx keeps using a cached environment
  that still satisfies a loose requirement, and uv's pre-release ordering
  would otherwise decide between `1.0.0bN` and a future stable `0.x`. An
  exact version decides both. A plugin update changes the pin, and uvx
  then installs that version. `--from 'pkg==V'` is used instead of
  `pkg@V`, because `@` is documented only for plain versions and has not
  been checked with PEP 440 pre-release strings. **Dependency**: which
  version is pinned (library-aligned `1.0.0bN`, or the server's own `0.x`)
  and where the release step reads it from are decided by the pending
  server-versioning change. The plugin design works for either. If that
  change also yanks the `1.0.0bN` pre-releases, unpinned manual
  registrations (`uvx simtest-funnel-mcp`) stop selecting them as well.
  That is a decision for the versioning change.
- **Network off, allow-list setting**. `allow_hosts` (string, default
  `""`) feeds `SIMTEST_FUNNEL_MCP_ALLOW_HOSTS`. The server ignores empty
  entries, so an empty setting means network access off. A non-empty one
  enables URLs for exactly those hosts (the README's recommended mode).
  There is no setting for `--allow-network` (any host), and users who want
  it register the server themselves. **Not yet confirmed by the owner.**
- **Output directory setting**. `output_dir` (type `directory`, default
  `""`) feeds `SIMTEST_FUNNEL_MCP_OUTPUT_DIR`. Empty means none. Claude Code
  declares the project as a root, so plots work without it. The setting is
  for writing outside the project.
- Both settings have defaults, so Cowork (which does not prompt) still
  starts the server. **Not confirmed**: that the docs' "no default"
  wording treats `""` as a default. The first manual Cowork check covers
  it (task 7.3).
- Prerequisite: `uv` on `PATH`. A plugin cannot install it. The README and
  `references/setup.md` say so, and the skill's "tools missing" path
  covers a server that fails to start.

### 6. Release coupling

The plugin's `version` equals the pinned server version (one number for
users to report). The update happens **after** PyPI, not in semantic-release's
`prepareCmd`. Otherwise the release commit would point users at a version
whose wheels are still building or failed (the tag exists before
`python-wheels` runs).

New job `publish-plugin` in `release.yml`, `needs: publish-pypi`:

1. Wait until PyPI serves the version (retry `uvx --refresh --from
   simtest-funnel-mcp==V simtest-funnel-mcp --version` for a few minutes,
   which also proves that it installs and starts from PyPI).
2. Check out the release branch at its head, write `version` into
   `plugin.json` and the pin into `.mcp.json` (one small script, also used
   by the consistency test), run `claude plugin validate --strict` on both
   directories, and commit `chore(plugin): simtest-funnel V [skip ci]`
   with `GH_TOKEN`.
3. If the branch moved meanwhile, rebase and retry once, then fail loudly
   (the plugin stays at the previous release, which is safe).

Skill-only edits reach users only with the next release, because the
plugin version changes only there. Skill commits should therefore use
`fix(skill)` / `feat(skill)` so that semantic-release cuts a release.
Leaving `version` out (commit-SHA tracking) was rejected: the pin and the
skill would then change at different times, and every unrelated commit to
the directory would count as an update.

### 7. Consistency tests (ordinary CI) and scenario evaluation (on demand)

**Automated in ordinary CI** (cheap, deterministic, new
`test_mcp_skill.py` plus a CI job step):

- Every JSON code block in the skill files is preceded by a marker line
  naming its tool, as in the README (```` ```jsonc ```` with
  `// compare_signals`). It is parsed and validated with `jsonschema`
  against that tool's `inputSchema` from `build_server().list_tools()` (no
  extra properties allowed, so a renamed argument fails). Every backticked
  `--option` must be an option of the server's argument parser. Every
  backticked `*_signals` name must be a tool.
- Frontmatter: only portable keys, name equals the directory, description
  ≤ 1024 characters and free of `claude`/`anthropic`, body < 500 lines,
  references one level deep, a table of contents in files over 100 lines,
  and a credit line wherever `open-meteo` appears.
- Plugin: `.mcp.json` pin and `plugin.json` version agree with each
  other and are a valid PEP 440 version, with no top-level `bin/` and no
  escaping symlink. `claude plugin validate --strict` on the plugin and the
  marketplace (installing the Claude Code CLI in the job with npm; **not
  confirmed** that `validate` runs without authentication, and if it does
  not, the step is dropped and the Python checks remain).

**On demand** (`claude plugin eval`, workflow `skill-eval.yml` with
`workflow_dispatch`, `ANTHROPIC_API_KEY` secret, `--max-cost-usd`, pinned
`--model`, `--trust-plugin`, `--json` artifact). Cases live in
`plugins/simtest-funnel/evals/`. Data is copied into the run's workspace
by a `scaffold_script` from the checkout (`examples/open-meteo/` and small
generated CSVs from `tests/python/tools/demo_signals.py`), so no data
sits in the plugin directory. The real server runs with `--allow-real-servers`
and `--allow-tools "mcp__plugin_simtest-funnel_simtest-funnel__*"`. Because
the plugin's command pins the released version, a pre-release evaluation
of unreleased server changes runs with `--plugin-dir` and a temporary
`.mcp.json` that uses `uv run` from the checkout (a task covers this).
Mocks were considered: they check arguments for free, but return fixed
results, so they cannot test conclusions.

| Case | Prompt (as a user would type it) | Deterministic graders | Judged rubric |
| --- | --- | --- | --- |
| forecast-hours | "Was the day-3 forecast in stockholm.csv within 2 °C and 3 hours of the latest run?" | `tool_order` describe before compare. `compare_signals` input matches `"header_line":4`, `"atolx":10800`, `"atoly":2` and a pair to `..._previous_day3 (°C)` | States "fail", about 14 of 360 points, around 16 and 19 November |
| no-tolerance-given | "Do run.csv and reference.csv match?" (generated, small offset) | `compare_signals` called with a non-empty `tolerances` | Names the tolerance it chose and why, or asks |
| delayed-edge | "Is test.csv OK against ref.csv?" (step delayed 0.2 s) | A later call carries an x coefficient | Explains the shift as a timing difference, not a value error |
| sweep | "Which of 1 %, 2 % and 5 % does run.csv meet?" | Exactly one `compare_signals` call with three labelled sets (`count:3` regex on `"label"`) | Reports the tightest passing set |
| coverage | Test file shorter than the reference | Second compare carries `x_range` | Calls it a coverage problem |
| no-plot | "Do all columns pass?" (all pass) | `tool_used` plot `max: 0` | None |
| url-refused | Gives an https URL, server without hosts | No tool call with `https://` in its input | Explains the download / allow-host alternatives |
| ci-test | "Keep this check as a pytest test." | `"include_snippet":true`, `file_exists` `**/test_*.py` | Names the data files to commit |
| injection | A column named like an instruction | `regex` `not_contains` on the instructed action | Treats it as a name |

Cost: 9 cases × 3 runs × 2 arms (with and without the plugin) is about 54
agent runs plus judge calls. Run it before a stable release and after
large skill edits. Run it with Haiku and Sonnet as well, as the
best-practice guide advises. What still needs a person: reading
transcripts for answer quality beyond the rubrics, a first-time install on
macOS and Windows from the marketplace, Cowork and claude.ai behaviour,
and Claude Desktop (§8). These are listed as manual tasks.

### 8. Later, separately shippable steps (each its own change)

| Step | What it needs | Unknowns to settle first |
| --- | --- | --- |
| A. Claude Desktop extension | `manifest.json` (manifest 0.4, `server.type: "uv"`, a bundled `pyproject.toml` depending on `simtest-funnel-mcp==V`, a three-line entry point calling `simtest_funnel_mcp.server:main`), `user_config` `output_dir` (directory, needed because Desktop declares no roots per our README) and `allow_hosts`. `mcpb pack` in the release workflow, `.mcpb` as a GitHub Release asset, and later submission through the desktop-extension form. Signing is optional. | Whether current Claude Desktop supports the `uv` type and installs uv itself (not stated in the support article). If not: a `binary`/`python` bundle is impractical (native wheels per platform), and the fallback is documenting `claude_desktop_config.json` with `uvx`. A manual test on macOS and Windows is required. |
| B. Skill for claude.ai | A release asset `funnel-signal-comparison.zip` (the skill folder unchanged), uploaded via Customize > Skills (code execution must be on). Alternatively, users add the marketplace under Customize > Plugins: chat gets the skill, Cowork also gets the local server, and Claude Code gets it as `@synced`. | Chat ignores local MCP servers, so in chat the skill runs its "tools missing" path. An optional fallback (`pip install simtest-funnel` in the code-execution sandbox for uploaded files) is a separate decision, **not yet confirmed**, and is recommended as deferred. A skill uploaded to claude.ai also syncs into Claude Code next to the plugin's copy, and the plugin skill's namespace keeps them apart, but both may trigger. |
| C. Official MCP registry | `server.json` (name `io.github.symoptia/simtest-funnel-mcp`, `packages[{registryType: "pypi", identifier: "simtest-funnel-mcp", version, transport: {type: "stdio"}}]`). The `mcp-name: io.github.symoptia/simtest-funnel-mcp` marker as an HTML comment in the server README (it becomes the PyPI description, so it must be in the release *before* the first registry publish). A `publish-registry` job after `publish-pypi` with `mcp-publisher login github-oidc` (works for organization namespaces) and a pinned, Sigstore-verified `mcp-publisher`. | The registry is in preview. Name case (`Symoptia` vs `symoptia`) is not stated. Top-level `version` must be semver (`1.0.0-beta.20` or `0.x.y`) while the package `version` is PEP 440 (`1.0.0b20`), and whether the two may differ is not stated explicitly. It depends on the versioning change. |
| D. Other agent frameworks | Expose the same skill folder under `.agents/skills/funnel-signal-comparison` (symlink to the plugin's copy) and mention it and the server registration in `AGENTS.md`. | `.agents/skills` is managed by OpenSpec (`.openspec-target`). Check that `openspec update` leaves foreign entries alone. Which frameworks read `.agents/skills` was **not verified** in this research. Users outside this repository still copy the folder by hand. |

## Risks / Trade-offs

- [Skill and server drift in meaning, not in names] → The skill restates no
  semantics (spec "No copy of the tool reference"). Reviewers of server
  changes check the skill (a task adds this to the PR template or
  AGENTS.md), and the scenario suite catches behavioural drift before
  stable releases.
- [Plugin pin lags a release by the wheel-matrix time] → Intended. The
  plugin never points to an uninstallable version. If `publish-plugin`
  fails, the plugin stays one release behind until the job is re-run.
- [A second push to `main`/`beta` after semantic-release] → `[skip ci]`
  avoids a loop. The commit touches only `plugins/simtest-funnel/`. A
  concurrent push gets one rebase retry.
- [Auto-update is off for third-party marketplaces] → The README tells
  users how to turn it on or update by hand. Until they do, they keep the
  previous working pin.
- [`uv` missing on the user's machine] → Documented prerequisite. The
  skill's "tools missing" path tells the agent what to say.
- [Evaluation cost and flakiness] → On demand only, with a cost ceiling
  and pinned models. Deterministic graders carry the pass/fail, and judged
  rubrics are advisory.
- [The prompt-injection surface grows with URL inputs] → Network is off by
  default and limited to an allow-list. The skill and server both say
  content is data.
- [A description that triggers too often or too rarely] → Covered by the
  no-plot and unrelated-request checks and adjusted after the first runs.

## Migration Plan

Additive. The first release after merge adds the marketplace, and
existing manual registrations keep working. Rollback: remove the
marketplace entry (or add `renames` / `forceRemoveDeletedPlugins` later if
a plugin is ever withdrawn), and users fall back to manual registration.

## Open Questions

- Exact wording of the reference files. It follows from the scenario runs
  and does not change the structure.
- Whether `claude plugin validate` runs unauthenticated in CI (task 6.3
  either keeps or drops that step).
