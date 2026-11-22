## ADDED Requirements

### Requirement: Versions in PEP 440 form

Both Python packages SHALL carry their version in normalised PEP 440 form
in their distribution metadata, and the server SHALL report the same
string as its MCP `serverInfo.version` and in `--version`. A release SHALL
write the PEP 440 form of its version into both Python projects and the
server's exact library pin. The Rust core's `version()` stays SemVer.

#### Scenario: Pre-release versions agree
- **WHEN** the packages of release `1.0.0-beta.22` are installed
- **THEN** `importlib.metadata` reports `1.0.0b22` for both, and the
  server's `serverInfo.version` and `--version` say `1.0.0b22`

#### Scenario: Release preparation
- **WHEN** the release prepares version `1.1.0-rc.2`
- **THEN** both Python projects get version `1.1.0rc2` and the server pins
  `simtest-funnel==1.1.0rc2`; a version it cannot convert stops the release
