# Installing and configuring the server

What to tell a user whose agent has this skill but not the simtest-funnel
tools, or who needs a server option. The server is the PyPI package
`simtest-funnel-mcp`, started over stdio. Its full documentation is the
[server README](https://github.com/Symoptia/simtest-funnel/blob/main/python/simtest-funnel-mcp/README.md).

## Contents

- [Diagnose first](#diagnose-first)
- [Prerequisite: uv](#prerequisite-uv)
- [Claude Code](#claude-code)
- [Claude Desktop](#claude-desktop)
- [Other MCP clients](#other-mcp-clients)
- [Reading URLs](#reading-urls)
- [Saving plot files](#saving-plot-files)
- [Platform notes](#platform-notes)

## Diagnose first

- If the skill came with the simtest-funnel plugin, the server is
  configured already. Missing tools then usually mean that `uv` is not
  installed or the server failed to start: ask the user to check the
  client's MCP server list (`/mcp` in Claude Code) and to run
  `uvx simtest-funnel-mcp --version` in a terminal.
- If the tools exist but a call fails, it is not a setup problem: read the
  error message.
- In a client that cannot run local MCP servers (for example a chat in the
  browser), the tools cannot be added. Say so; do not compare by hand.

## Prerequisite: uv

The registrations below start the server with `uvx`, part of
[uv](https://docs.astral.sh/uv/). uv downloads Python and the server on
first start. Install it once from its documentation; afterwards
`uvx simtest-funnel-mcp --version` should print a version.

## Claude Code

```bash
claude mcp add simtest-funnel -- uvx simtest-funnel-mcp
```

Add `--scope user` after `add` to make it available in every project.
Options for the server go after `simtest-funnel-mcp` (see the sections
below). Restart the session, then check `/mcp`.

## Claude Desktop

Add to `claude_desktop_config.json` (Settings, Developer, Edit Config) and
restart the app:

```jsonc
// config: claude_desktop_config.json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uvx",
      "args": ["simtest-funnel-mcp"]
    }
  }
}
```

Claude Desktop declares no workspace folders, so plot files need an output
directory (see [Saving plot files](#saving-plot-files)).

## Other MCP clients

Any client that starts stdio servers works: the command is `uvx`, the
arguments are `simtest-funnel-mcp` followed by any options. Use absolute
paths in tool calls.

## Reading URLs

Network access is off by default. To read public https URLs, the user
restarts the server with an allowed host (repeatable), for example:

```bash
claude mcp add simtest-funnel -- uvx simtest-funnel-mcp --allow-host raw.githubusercontent.com
```

The same as an environment variable in a JSON configuration:

```jsonc
// config: .mcp.json
{
  "mcpServers": {
    "simtest-funnel": {
      "command": "uvx",
      "args": ["simtest-funnel-mcp"],
      "env": {"SIMTEST_FUNNEL_MCP_ALLOW_HOSTS": "raw.githubusercontent.com"}
    }
  }
}
```

Recommend `--allow-host` over `--allow-network` (any public host): a URL
chosen by a model can carry conversation data to whatever host it names.
Downloading the file and passing its local path needs no option at all.

## Saving plot files

`plot_signals` writes files only inside the client's workspace folders
(Claude Code declares the project) or an output directory given at start:

```bash
claude mcp add simtest-funnel -- uvx simtest-funnel-mcp --output-dir /home/me/plots
```

or `SIMTEST_FUNNEL_MCP_OUTPUT_DIR` in the `env` of a JSON configuration. The
directory must exist. Without either, use the inline preview.

## Platform notes

- Prebuilt wheels exist for Linux, macOS and Windows; Python 3.11 or later
  (uv installs one if needed).
- Windows on ARM64: the server needs an x64 Python, which is what uv
  installs there by default. With a native ARM64 Python a dependency has no
  prebuilt wheel.
- CSV files must be UTF-8. A file saved with Excel's plain "CSV" format on
  Windows (Windows-1252) is refused with the line and byte at fault; ask
  for "CSV UTF-8" instead. UTF-8 files with a byte-order mark and CRLF line
  ends read correctly.

Windows 11 x64 (field test with uv and Claude Code):

- The server works with `uvx`. The first start took about 27 s (uv
  downloads about 43 packages); later starts take about 2 s.
- Paths with spaces and non-ASCII characters work, for input files and
  output directories.
- Claude Code in VS Code: a server added with the default local scope may
  not appear, because the stored project path can differ from the
  session's in the case of the drive letter (`C:` against `c:`). Adding it
  with `--scope user` works.
- With only the VS Code extension installed, the `claude` command may not
  be on `PATH`; use a terminal where it is, or the CLI bundled with the
  extension.
