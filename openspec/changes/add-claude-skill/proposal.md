# Proposal

## Why

The MCP server gives an agent the tools for a funnel comparison, but not
the judgement around them. Agents can answer "is this signal close enough
to the reference?" only if they choose tolerances on purpose. They need to
know that there is no time tolerance unless they give one, that date-time
axes count in seconds, and that a single failed verdict tells them little
until they look at where the signal left the tube, by how much and in which
direction. They also need to try several tolerance sets, plot only when a
picture helps, and turn a comparison into a CI test. Today all of that
lives in a long README and in tool descriptions that say *what* each
argument does, not *when* to use it.

Installation is a second obstacle. A user has to register the server by
hand in each client, and nothing tells an agent how to work with it. The
owner wants local agents to use the server on local and CI result files
first and on public URLs second. That needs one install that gives an
agent both the tools and the workflow.

## What Changes

- **Agent skill** `funnel-signal-comparison` (Agent Skills format,
  portable frontmatter only) kept in this repository. Its `SKILL.md` covers
  the workflow and judgement: describe first, choose tolerances deliberately
  (absolute, range-relative or local-relative; time tolerance explicit;
  seconds on date-time axes), compare with several labelled tolerance sets
  in one call, read the violation summary and draw conclusions, plot only
  when useful, handle real-world files (`header_line`, `pairs`), zoom with
  `x_range`, use URLs only when the server allows them, and produce a pytest
  snippet for CI. It also lists what not to do. Reference files are loaded
  only when needed (tolerance strategies, reading results, CI tests, setup,
  a worked example). The skill points to the tool descriptions for exact
  semantics and does not copy them.
- **Consistency checks in CI**: every tool call example in the skill is
  validated against the server's live tool schemas, every start-up option
  it names must exist, and the skill and plugin layouts are validated.
- **Scenario evaluation**: a small suite of scenario prompts on bundled
  data with checkable expected behaviour. The cheap deterministic part
  (argument and tool-order graders) runs on demand with a real agent and a
  cost ceiling; it is not part of ordinary CI.
- **Claude Code plugin** `simtest-funnel` bundling the skill and the MCP
  server configuration (`uvx` with an exact server version, network access
  off, optional allow-listed hosts and output directory as user settings).
  It is published through a plugin marketplace in this repository, with
  `main` as the stable channel and `beta` as the pre-release channel.
- **Release mechanics**: each release updates the plugin's version and
  its pinned server version, but only after the server is on PyPI and
  starts from there. Nothing in the plugin ever points to a server version
  that cannot be installed.
- **Later, separately shippable steps** (planned in design.md, specified
  in their own changes): a Claude Desktop extension (`.mcpb`), the skill as
  an uploadable zip for claude.ai, an entry in the official MCP registry,
  and the shared `.agents/skills` layout for other agent frameworks.

Out of scope: changes to the server's tools or arguments; plotting
packaging (owner decision: matplotlib stays in the default install, so all
three tools are always available); the MCP server's own version line
(pending change; this change depends on it, see design.md).

## Capabilities

### New Capabilities

- `funnel-agent-skill`: the agent skill for funnel comparisons: what it
  teaches, its structure and format limits, how it stays consistent with
  the server, and how its behaviour is evaluated.
- `claude-code-plugin`: the Claude Code plugin and its marketplace: the
  bundled server configuration, distribution channels, updates and
  release coupling with the server package.

### Modified Capabilities

<!-- none: the server's behaviour does not change -->

## Impact

- New files: `.claude-plugin/marketplace.json`, `plugins/simtest-funnel/`
  (plugin manifest, `.mcp.json`, the skill, the evaluation suite), a
  consistency test module, and documentation in the MCP server README and
  root README.
- `release.yml` / `.releaserc.json`: a post-publish step that updates the
  plugin version and server pin once the PyPI upload has been verified.
- CI: one more job (plugin and skill validation, consistency tests); the
  scenario evaluation is a manually triggered workflow that needs an API
  key secret.
- Depends on the pending decision about a separate 0.x version line for
  the MCP server (it decides which version the plugin pins and where the
  release step reads it from).
