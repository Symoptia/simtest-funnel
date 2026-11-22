# Spec Delta

## MODIFIED Requirements

### Requirement: Tool annotations

`plot_signals` SHALL be annotated as not read-only, destructive (it can
replace a file when asked) and idempotent, and as closed-world unless network
access was enabled at start-up (`mcp-url-sources`), in which case it is
open-world.

#### Scenario: Client inspects annotations
- **WHEN** a client lists the tools
- **THEN** `plot_signals` is marked not read-only and destructive, while the
  other two tools stay read-only

#### Scenario: Network access enabled
- **WHEN** the server was started with `--allow-network` and a client lists
  the tools
- **THEN** `plot_signals` is marked open-world, not read-only and destructive

## ADDED Requirements

### Requirement: Plot inputs from URLs

`plot_signals` SHALL accept URLs for its reference and test inputs as
`mcp-url-sources` defines. The output path SHALL stay a local path: a URL as
output path SHALL be refused, and all output path checks SHALL happen before
any input is fetched.

#### Scenario: Plot a pair from a URL
- **WHEN** network access is enabled and an agent plots the day-1 pair from
  an Open-Meteo URL with header line 4 and an output path inside a root
- **THEN** the URL is fetched (or its cached copy reused), the plot file is
  written locally and the result reports the URL's fetch time, size and
  SHA-256

#### Scenario: URL as output path
- **WHEN** an agent passes `https://example.org/plot.svg` as output path
- **THEN** the call fails with an error saying the output path must be a
  local path, and nothing is fetched or written

#### Scenario: Refused output path
- **WHEN** the output path lies outside the roots and the inputs are URLs
- **THEN** the call fails before any URL is fetched
