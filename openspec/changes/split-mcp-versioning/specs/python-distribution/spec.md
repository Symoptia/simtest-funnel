# Spec Delta

## MODIFIED Requirements

### Requirement: Every file verified before upload

Before uploading, a release SHALL build every distribution file of each
package whose version line released in that run (`release-versioning`)
from that line's release tag, and SHALL install each `simtest-funnel`
wheel and the sdist into a clean environment on the platform it targets,
with the lowest and the newest supported Python, import it and run one
comparison.

#### Scenario: Wheel smoke test
- **WHEN** the release builds the macOS ARM64 wheel
- **THEN** it is installed on a macOS ARM64 machine that did not build it,
  into new environments for the lowest and the newest supported Python,
  and a comparison returns the expected statuses

#### Scenario: Server-only release
- **WHEN** only the server line released in a run
- **THEN** only the `simtest-funnel-mcp` wheel and sdist are built, from
  the `mcp-v` tag, and no library wheel is built

### Requirement: MCP server verified on each operating system

On at least one platform per operating system (Linux, macOS, Windows),
whenever the server line releases, the release SHALL install the freshly
built `simtest-funnel-mcp` wheel together with exactly the library version
it pins (the freshly built wheel if the library released in the same run,
otherwise from PyPI) into a clean environment, start
`python -m simtest_funnel_mcp` over stdio, and check that it answers
`initialize`, lists its tools and completes one `compare_signals` call.

#### Scenario: Server smoke test on Windows
- **WHEN** the release builds the Windows x64 wheel
- **THEN** the server, installed from the new wheels on a Windows machine,
  lists `describe_signals`, `compare_signals` and `plot_signals` and
  compares two small CSV files

#### Scenario: Server released without the library
- **WHEN** only the server line released and it pins `simtest-funnel`
  `1.0.0b22`
- **THEN** the smoke environments contain the new server wheel and
  `simtest-funnel` `1.0.0b22` installed from PyPI

### Requirement: All-or-nothing upload

A release SHALL upload each released package's files to PyPI in one step
per package, which runs only after every build and verification of that
package has passed; the `simtest-funnel-mcp` step SHALL also wait for the
`simtest-funnel` step of the same run, when there is one, to succeed. A
failed library build or verification SHALL therefore block both packages,
and a failed server build or verification only the server.

#### Scenario: One platform fails
- **WHEN** the Windows ARM64 library build or its smoke test fails during a
  release of both lines
- **THEN** no file of either package's new version is uploaded to PyPI

#### Scenario: Upload order
- **WHEN** both lines released in a run and every check passed
- **THEN** every `simtest-funnel` file is uploaded before any
  `simtest-funnel-mcp` file

#### Scenario: Server smoke test fails
- **WHEN** both lines released and only the server's smoke test fails
- **THEN** the `simtest-funnel` files are uploaded and no
  `simtest-funnel-mcp` file is
