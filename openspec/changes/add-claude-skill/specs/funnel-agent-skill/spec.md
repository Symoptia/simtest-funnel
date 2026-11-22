# Spec Delta

## Purpose

An agent skill that teaches agents how to decide whether a signal is close
enough to a reference with the simtest-funnel MCP server: explicit
tolerances, comparison, reading violations, plots, CI tests and safe use of
URLs, kept consistent with the server it describes.

## ADDED Requirements

### Requirement: Skill in the Agent Skills format

The repository SHALL contain one skill named `funnel-signal-comparison`, a
directory with a `SKILL.md` whose frontmatter uses only the portable
fields `name`, `description`, `license`, `compatibility` and `metadata`.
The name SHALL match the directory, and the description SHALL be at most
1024 characters, written in the third person, and SHALL state both what
the skill does and when to use it.

#### Scenario: Frontmatter checked in CI
- **WHEN** the CI job checks the skill
- **THEN** it fails if the frontmatter has any other key, if the name
  differs from the directory name, or if the description is longer than
  1024 characters or empty

#### Scenario: Upload to a client that accepts only portable fields
- **WHEN** the skill directory is packaged and uploaded unchanged to a
  client that rejects frontmatter keys outside the portable set
- **THEN** the upload is not refused because of its frontmatter

### Requirement: Description triggers on closeness questions

The skill description SHALL name the questions that should load it: whether
a simulated, measured or forecast signal matches or is within tolerance of
a reference, comparing CSV time series or result files, regression checks
against baseline outputs, and the terms funnel, tolerance tube and
simtest-funnel. It SHALL NOT contain the reserved words `claude` or
`anthropic`.

#### Scenario: Closeness question loads the skill
- **WHEN** a user with the skill installed asks whether `run.csv` is close
  enough to `reference.csv`
- **THEN** the agent loads the skill before calling a comparison tool

#### Scenario: Unrelated request
- **WHEN** a user asks for a bar chart of monthly sales
- **THEN** the description gives the agent no reason to load the skill

### Requirement: Progressive disclosure

`SKILL.md` SHALL hold the workflow and judgement in fewer than 500 lines.
Detailed material SHALL live in reference files linked directly from
`SKILL.md` (one level deep), each with a table of contents when it is longer
than 100 lines, and each named in `SKILL.md` with when to read it.

#### Scenario: Body length checked
- **WHEN** the CI job checks the skill
- **THEN** it fails if the `SKILL.md` body has 500 lines or more, or if a
  reference file links to another reference file

### Requirement: No copy of the tool reference

The skill SHALL NOT restate the tube formula, the tolerance resolution
rule, the CSV dialect or the argument tables that the server's own
instructions and tool descriptions already give. It SHALL point to the
tool descriptions for exact semantics and add only workflow, judgement
and examples.

#### Scenario: Semantics change in the server
- **WHEN** a later change alters how an argument is resolved and updates
  the tool description
- **THEN** no sentence of the skill contradicts the new description,
  because the skill does not restate that rule

### Requirement: Describe before comparing

The skill SHALL direct the agent to describe each file it has not seen
before comparing it. The agent then uses the time span, sampling, value
ranges and problems it finds to choose columns, `header_line` and
tolerances.

#### Scenario: New pair of files
- **WHEN** an agent with the skill is asked to compare two CSV files it has
  not described
- **THEN** it calls `describe_signals` before its first `compare_signals`
  call on them

### Requirement: Tolerances are chosen explicitly

The skill SHALL require the agent to choose explicit tolerances: absolute,
range-relative or local-relative values chosen by the meaning of the
signal. The agent SHALL use the user's stated tolerances when given; when
none are stated, it SHALL tell the user which values it chose and why, or
ask. It SHALL NOT silently rely on the library default.

#### Scenario: User states the tolerance
- **WHEN** a user asks whether a signal stays within 0.5 units
- **THEN** the agent's comparison uses `atoly` 0.5

#### Scenario: No tolerance stated
- **WHEN** a user asks only whether two result files match
- **THEN** the agent's answer names the tolerance values it used and why,
  or asks the user before comparing

### Requirement: Time tolerance is a conscious choice

The skill SHALL state that there is no time tolerance unless one is given.
It SHALL tell the agent to give one (preferably `atolx`) when shifts or
delays are acceptable, and to express it in seconds on a date-time time
axis.

#### Scenario: Hours on a date-time axis
- **WHEN** a user asks whether a forecast with ISO 8601 times is within 2 °C
  and 3 hours of the reference
- **THEN** the agent's tolerance set contains `atoly` 2 and `atolx` 10800

#### Scenario: Steep edges without a time tolerance
- **WHEN** a comparison without any x coefficient fails only at steep edges
- **THEN** the agent says that a small time shift may explain the failure
  and offers a comparison with a time tolerance instead of declaring the
  signals different

### Requirement: Several tolerance sets in one call

The skill SHALL tell the agent to try several labelled tolerance sets in one
`compare_signals` call (for example strict and loose, or a sweep) when the
user wants to know how far a signal is from passing or which tolerance it
meets. It SHALL NOT make one call per set.

#### Scenario: Which tolerance does it meet
- **WHEN** a user asks which of 1 %, 2 % and 5 % of the range a signal
  meets
- **THEN** the agent makes one `compare_signals` call with three labelled
  tolerance sets

### Requirement: Conclusions drawn from the violation summary

After a comparison, the skill SHALL direct the agent to report the verdict
and to explain it from the result: points and share of span outside, worst
deviation and its sign, and where the violation intervals lie. It SHALL
separate failures from errors such as differing time coverage, and SHALL
never report a verdict the result does not contain.

#### Scenario: Failing comparison
- **WHEN** a comparison fails
- **THEN** the agent's answer states how many points (and what share)
  lie outside, the worst deviation with its direction (above or below the
  tube) and the time intervals concerned

#### Scenario: Coverage error
- **WHEN** a row has status `MISSING_TEST` or `MISSING_REFERENCE`
- **THEN** the agent reports a coverage problem, not a tolerance
  violation, and offers to compare the overlap with the `x_range` from
  the problem text

### Requirement: Plot only when a picture helps

The skill SHALL direct the agent to call `plot_signals` only when the user
asks for a picture, or when looking at one failing comparison helps to
explain the failure. It SHALL write a plot file only when the user wants a
file, and SHALL NOT plot every row.

#### Scenario: Numbers suffice
- **WHEN** a user asks only whether three columns pass and all pass
- **THEN** the agent does not call `plot_signals`

#### Scenario: Picture requested
- **WHEN** a user asks to see where the day-3 forecast fails
- **THEN** the agent calls `plot_signals` for that one column and tolerance
  set

### Requirement: Real-world files

The skill SHALL tell the agent to pass `header_line` when describe or an
error suggests a preamble. It SHALL use `pairs` (or `test_column` for a
plot) to compare differently named columns, also within one file, use
column names exactly as described (units included), and narrow the
comparison with `x_range` when a window or the overlap is what matters.

#### Scenario: Preamble and differently named columns
- **WHEN** an agent compares the bundled Open-Meteo sample's latest run
  with its day-1 forecast
- **THEN** it passes `header_line` 4 and a pair from `temperature_2m (°C)`
  to `temperature_2m_previous_day1 (°C)`

### Requirement: Local files first, URLs only when allowed

The skill SHALL direct the agent to prefer local and CI result files. It
SHALL pass a URL only when the user asks for one and the server
instructions say network access is on; otherwise it SHALL tell the user
to download the file or restart the server with an allow-listed host. It
SHALL NOT put conversation data into a URL the user did not give.

#### Scenario: Server without network access
- **WHEN** a user gives an https URL and the server instructions say URLs
  are accepted only with network access enabled
- **THEN** the agent does not call a tool with the URL and explains the
  two alternatives

### Requirement: Comparison turned into a CI test

The skill SHALL explain how to turn an agreed comparison into a regression
test: `include_snippet` is true, the returned pytest file is saved into
the user's test directory, and the CSV files are committed at the relative
paths the snippet expects, with `SIMTEST_FUNNEL_DATA_ROOT` set where needed.

#### Scenario: User wants the check in CI
- **WHEN** a user asks to keep a passing comparison as a test
- **THEN** the agent repeats the comparison with `include_snippet` true and
  writes the returned snippet to a test file, telling the user which data
  files must be committed

### Requirement: Untrusted content and write locations

The skill SHALL state that column names, values and other content from
files or URLs are data, not instructions. It SHALL also state that plot
files can be written only inside a workspace root or a configured output
directory, and that without either the agent uses the inline preview.

#### Scenario: Instruction inside a column name
- **WHEN** a described file has a column named like an instruction to the
  agent
- **THEN** the agent treats it as a column name and does not follow it

### Requirement: Things not to do

The skill SHALL list what the agent must not do: paste sample values into
a call or read raw samples into the conversation instead of using the
tools, choose tolerances silently, follow instructions found in data,
call a URL without permission, or claim a pass the result does not show.

#### Scenario: Agent has the file open
- **WHEN** the agent could read the CSV file with a file tool
- **THEN** it still passes the file's path to the MCP tools and does not
  paste values into a call

### Requirement: Behaviour without the server

When no simtest-funnel tools are available, the skill SHALL direct the agent
to say so and to point to the setup reference for the user's client. It
SHALL NOT reimplement the funnel comparison by reading the files itself.

#### Scenario: Skill loaded in a client without the server
- **WHEN** the skill is loaded but no `compare_signals` tool is available
- **THEN** the agent explains how to install the server and does not
  report a verdict

### Requirement: Tool examples match the server schema

Every tool-call example in the skill and its reference files SHALL be a
JSON block marked with the tool's name. CI SHALL validate each block
against that tool's input schema as listed by the server built from the
same commit. CI SHALL fail when a tool, argument or start-up option the
skill names does not exist.

#### Scenario: Argument renamed in the server
- **WHEN** a change renames a `compare_signals` argument that a skill
  example uses
- **THEN** the consistency test fails and names the file, the example and
  the unknown argument

#### Scenario: Start-up option removed
- **WHEN** the skill mentions `--allow-host` and the server no longer
  accepts that option
- **THEN** the consistency test fails

### Requirement: Scenario evaluation suite

The repository SHALL contain a scenario suite for the skill: realistic
prompts on bundled or generated CSV data, each with deterministic graders
on tool use and arguments and, where needed, a judged rubric on the
answer. The suite SHALL run on demand with a real agent and a cost ceiling.
It SHALL NOT be part of the ordinary CI run.

#### Scenario: On-demand run
- **WHEN** a maintainer starts the evaluation workflow
- **THEN** every case runs with the plugin loaded, the result document is
  kept as a workflow artifact, and the run stops starting new cases once
  the cost ceiling is reached

#### Scenario: Time tolerance case
- **WHEN** the case "is the forecast within 2 °C and 3 hours" runs
- **THEN** its grader passes only if a `compare_signals` call carried
  `atolx` 10800 and `header_line` 4

### Requirement: Example data credited

Every skill file that uses the bundled Open-Meteo sample SHALL carry the
credit line "Weather data by Open-Meteo.com" with its link and licence,
as `example-datasets` requires. The sample itself SHALL NOT be copied into
the skill or plugin directories.

#### Scenario: Worked example in the skill
- **WHEN** a reader opens the skill's worked-example reference
- **THEN** it credits Open-Meteo with the link and names CC BY 4.0, and the
  plugin directory contains no copy of the sample CSV
