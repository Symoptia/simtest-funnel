# Spec Delta

## Purpose

A Claude Code plugin that gives an agent the simtest-funnel MCP server and
the funnel comparison skill in one install, published from a marketplace in
this repository and updated together with the server's releases.

## ADDED Requirements

### Requirement: One plugin with server and skill

The repository SHALL contain a Claude Code plugin named `simtest-funnel`
whose manifest names the plugin, its version, description, author,
licence and repository. The plugin SHALL bundle the `funnel-signal-comparison`
skill and exactly one MCP server, `simtest-funnel`, so that installing the
plugin makes both available.

#### Scenario: Install the plugin
- **WHEN** a user installs the plugin and starts a session
- **THEN** the skill is listed as `simtest-funnel:funnel-signal-comparison`
  and the server's three tools are available

#### Scenario: Validation
- **WHEN** CI runs the plugin validator in strict mode on the plugin and on
  the marketplace
- **THEN** both pass without errors or warnings

### Requirement: Server started with uvx at an exact version

The plugin's server configuration SHALL start the server with `uvx` from
PyPI at one exact version of `simtest-funnel-mcp`, the pinned version. It
SHALL NOT use a version range, `@latest` or a pre-release flag, so the
version that runs never depends on uv's version ordering, pre-release
rules or tool cache.

#### Scenario: Pinned version runs
- **WHEN** the plugin pins version V and the user has an older version of
  the server in uv's cache
- **THEN** the server that starts reports version V

#### Scenario: Older pre-releases on PyPI
- **WHEN** PyPI holds pre-releases that sort above the pinned version
- **THEN** the plugin still starts exactly the pinned version

### Requirement: Network access off by default

The plugin SHALL start the server without `--allow-network`. URL inputs
SHALL be enabled only through an optional plugin setting that lists
allowed host names. When the setting is empty, the server starts with
network access off.

#### Scenario: Default install
- **WHEN** a user installs the plugin and leaves the host setting empty
- **THEN** the server instructions say that URLs are accepted only when
  network access is enabled, and a URL argument is refused

#### Scenario: Host configured
- **WHEN** the user sets the host setting to
  `previous-runs-api.open-meteo.com`
- **THEN** the server accepts https URLs on that host only

### Requirement: Optional output directory setting

The plugin SHALL offer an optional setting for a directory in which plots
may be written besides the client's workspace roots. When empty, the
server SHALL start with no configured output directory.

#### Scenario: Setting left empty
- **WHEN** the output directory setting is empty
- **THEN** the server starts and writes plot files only inside workspace
  roots

### Requirement: Marketplace in this repository

The repository root SHALL contain a plugin marketplace that lists the
plugin by a relative path. Users SHALL be able to add the marketplace from
the GitHub repository and install the plugin by its entry name.

#### Scenario: Add and install
- **WHEN** a user runs `/plugin marketplace add Symoptia/simtest-funnel` and
  installs `simtest-funnel` from that marketplace
- **THEN** the plugin is installed at the version recorded on the default
  branch

### Requirement: Stable and pre-release channels

The marketplace on the `main` branch SHALL offer the latest stable release.
On the `beta` branch it SHALL offer the latest pre-release. A user selects
the channel with the branch reference when adding the marketplace.

#### Scenario: Beta channel
- **WHEN** a user adds the marketplace with the reference `#beta`
- **THEN** the installed plugin pins the latest pre-release server version
  published from `beta`

### Requirement: Plugin version follows the server release

The plugin version and its pinned server version SHALL change only at a
release. They SHALL change only after every distribution of that release
has been uploaded to PyPI and the pinned version has been installed from
PyPI and has started. A release that fails before that point SHALL leave
the plugin unchanged.

#### Scenario: Upload fails
- **WHEN** a release's PyPI upload or smoke test fails
- **THEN** the plugin on that branch still pins the previous release

#### Scenario: Successful release
- **WHEN** a release has been published to PyPI and its server started
  with `uvx` at that version
- **THEN** a commit on the release branch sets the plugin version and pin
  to that release

### Requirement: Plugin contents are portable

The plugin directory SHALL contain no top-level `bin/` directory, no path
outside the plugin directory and no symbolic link that leaves it, and no
copy of the bundled example data. Then it installs unchanged from the
marketplace, from a zip upload and through organization sync.

#### Scenario: Plugin directory checked
- **WHEN** CI checks the plugin directory
- **THEN** it fails on a top-level `bin/`, on a symbolic link resolving
  outside the plugin, or on a copy of the Open-Meteo sample

### Requirement: Installation and update documentation

The MCP server README and the root README SHALL document how to add the
marketplace, install, enable auto-update or update by hand, choose the
beta channel and fill in the optional settings. They SHALL also state
that `uv` must be installed and that manual registration remains available.

#### Scenario: Reader wants updates
- **WHEN** a reader looks up how a new release reaches them
- **THEN** the README explains that auto-update is off for third-party
  marketplaces by default and gives both the toggle and the update command
