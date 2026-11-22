# Tasks

## 1. Preconditions

- [ ] 1.1 Record the owner's answers to the design choices marked "not yet confirmed" in design.md (skill name and description, marketplace in this repository and its name, channels by branch, allow-list and output-directory settings, deferring a claude.ai code-execution fallback) in design.md, and adjust the dependent tasks; verify no "not yet confirmed" marker remains without a recorded decision
- [ ] 1.2 Confirm that the server-versioning change (separate 0.x line) is decided, and record in design.md §5 which version the plugin pins and which `pyproject.toml` the release step reads it from; verify that `uvx --from 'simtest-funnel-mcp==<that version>' simtest-funnel-mcp --version` resolves exactly that version in a clean uv cache (`UV_CACHE_DIR` set to a fresh scratch directory)

## 2. Skill core and consistency test

- [ ] 2.1 Write `python/simtest-funnel-mcp/tests/test_mcp_skill.py` first: it finds the skill directory, checks frontmatter (portable keys only, name equals directory, description 1-1024 characters without `claude`/`anthropic`), body under 500 lines, references one level deep, a table of contents in reference files over 100 lines, and the Open-Meteo credit line wherever the sample is used. It validates every tool-marked JSON block against `build_server().list_tools()` input schemas (no extra properties), and checks that every backticked `--option` is accepted by the server's argument parser and every backticked `*_signals` name is a tool. Verify that it fails on a deliberately wrong argument name and an unknown option in a temporary skill copy
- [ ] 2.2 Write `plugins/simtest-funnel/skills/funnel-signal-comparison/SKILL.md` per design §1-2 (frontmatter, workflow checklist, tolerance decisions, several sets, reading results and drawing conclusions, real-world files, zoom, plots, CI, URLs, do-not list, behaviour without the server, references index) without restating the tube formula, resolution rule, CSV dialect or argument tables; verify that `test_mcp_skill.py` passes and that `skills-ref validate` (agentskills.io reference validator) accepts the folder

## 3. Reference files

- [ ] 3.1 Write `references/tolerances.md` and `references/results.md` (phrase-to-coefficient mappings, sweeps, pitfalls; reading rows, deviation sign, coverage errors, time limit, answer template), each tool call as a tool-marked JSON block; verify `test_mcp_skill.py` passes and every example call returns without argument errors when run against the bundled sample or generated data
- [ ] 3.2 Write `references/ci.md`, `references/setup.md` and `references/example-open-meteo.md` (snippet workflow including URL copies; per-client installation with `uv` as prerequisite, allow-listed hosts and output directory; the forecast walkthrough with the credit line). Verify `test_mcp_skill.py` passes and that the numbers in the walkthrough match a fresh `compare_signals` run on the bundled sample

## 4. Plugin and marketplace

- [ ] 4.1 Add `plugins/simtest-funnel/.claude-plugin/plugin.json` (name, version, description, author, license, repository, `userConfig` `allow_hosts` string and `output_dir` directory, both with default `""`), `plugins/simtest-funnel/.mcp.json` (design §5, exact pin) and a short plugin `README.md`. Verify that `claude plugin validate --strict plugins/simtest-funnel` passes
- [ ] 4.2 Add `.claude-plugin/marketplace.json` listing the plugin by relative path. Verify that `claude plugin validate --strict .` passes and that `claude plugin marketplace add ./` followed by `claude plugin install simtest-funnel@<marketplace>` in a scratch `HOME` lists the skill and the three tools (`claude plugin details simtest-funnel`)
- [ ] 4.3 Extend `test_mcp_skill.py` with plugin checks (the pin in `.mcp.json` equals `plugin.json` `version` and is valid PEP 440, no top-level `bin/`, no symlink leaving the plugin, no copy of the sample CSV) and an in-process check that the server started with `SIMTEST_FUNNEL_MCP_ALLOW_HOSTS=""` and `SIMTEST_FUNNEL_MCP_OUTPUT_DIR=""` has network access off and no output directory. Verify the test fails when the two versions differ
- [ ] 4.4 Document the plugin in `python/simtest-funnel-mcp/README.md` and the root README (add marketplace, install, beta channel via `#beta`, auto-update toggle and manual update commands, the two settings, `uv` prerequisite, manual registration still available). Verify that every command in the new sections works in a scratch `HOME`

## 5. Release coupling

- [ ] 5.1 Add `scripts/set-plugin-version.sh VERSION` (writes `plugin.json` `version` and the `.mcp.json` pin; refuses a non-PEP 440 version) and use it in `test_mcp_skill.py` against a temporary copy. Verify that running it twice is a no-op and that the plugin still validates
- [ ] 5.2 Add the `publish-plugin` job to `.github/workflows/release.yml` (needs `publish-pypi`; waits until `uvx --refresh --from simtest-funnel-mcp==V simtest-funnel-mcp --version` succeeds, runs the script, validates, commits `chore(plugin): simtest-funnel V [skip ci]` to the release branch with one rebase retry). Verify on the `beta` branch with the next pre-release that the commit appears only after the PyPI upload and that a forced failure of `publish-pypi` leaves the plugin unchanged
- [ ] 5.3 Note in `AGENTS.md` (Releasing and Per-Language Workflow) that skill changes use `feat(skill)`/`fix(skill)` to cut a release, and that server argument or option changes must keep `test_mcp_skill.py` passing; verify `make lint` passes

## 6. CI

- [ ] 6.1 Run `test_mcp_skill.py` as part of `make test-python` (it lives in the server's test directory) and verify it runs in the existing CI Python job
- [ ] 6.2 Add a CI step that runs `skills-ref validate` on the skill folder; verify that it fails on a pull request that adds an unsupported frontmatter key in a throwaway branch
- [ ] 6.3 Add a CI step that installs the Claude Code CLI and runs `claude plugin validate --strict` on the plugin and the marketplace. If it needs authentication, drop the step and record that in design.md Open Questions; verify the outcome on a pull request

## 7. Scenario evaluation and manual checks

- [ ] 7.1 Add the evaluation cases of design §7 under `plugins/simtest-funnel/evals/` (prompt, graders, a `scaffold_script` copying data from the checkout, no data files in the plugin directory) and a variant setup that runs the server from the checkout with `uv run`. Verify with `claude plugin eval plugins/simtest-funnel --scaffold --allow-real-servers --allow-tools "mcp__plugin_simtest-funnel_simtest-funnel__*" --ablation none --runs 1` that every case loads and the deterministic graders pass
- [ ] 7.2 Add `.github/workflows/skill-eval.yml` (`workflow_dispatch`, `ANTHROPIC_API_KEY` secret, pinned `--model` and `--judge-model`, `--max-cost-usd`, `--trust-plugin`, `--json` uploaded as artifact). Verify one dispatched run completes and records its cost
- [ ] 7.3 Manual check in Claude Code (macOS and Windows), Cowork and claude.ai chat with the plugin added from the marketplace. Verify: the skill triggers on a closeness question; the server starts via `uvx` in Claude Code and in a local Cowork session (including empty-default settings); and chat runs the skill's "tools missing" path. Record the results in design.md
- [ ] 7.4 Run the suite with Haiku and Sonnet (with and without the plugin), read the transcripts, adjust the skill wording where the agent went wrong, and record the scores in design.md; verify that every deterministic grader passes with the plugin

## 8. Integration checks

- [ ] 8.1 Run `make build`, `make lint`, `make test` and `openspec validate add-claude-skill --strict` and verify all pass

## Workflow follow-up

- Separate changes for the later steps in design.md §8: Claude Desktop extension, skill zip for claude.ai, official MCP registry entry, `.agents/skills` exposure for other agent frameworks.
- Archive this change after release with `openspec archive add-claude-skill`.
