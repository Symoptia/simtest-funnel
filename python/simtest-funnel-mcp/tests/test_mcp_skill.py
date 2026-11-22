"""Consistency of the agent skill ``funnel-signal-comparison`` with the server.

The skill (``plugins/simtest-funnel/skills/funnel-signal-comparison``) names
tools, arguments, result fields, start-up options and environment variables
and quotes numbers from example calls. These tests fail when any of that no
longer matches the server built from the same commit, and they check the
Agent Skills format rules (frontmatter, size, links, table of contents).

``skills-ref validate`` (the agentskills.io reference validator) is not a
dependency; its checks (portable frontmatter keys, name and description
rules) are implemented below.
"""

from __future__ import annotations

import asyncio
import functools
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest
from conftest import REPO_ROOT
from mcp import Client

import simtest.funnel as funnel
from simtest_funnel_mcp import server, snippet
from simtest_funnel_mcp.fetch import ALLOW_NETWORK_ENV

PLUGIN_DIR = REPO_ROOT / "plugins" / "simtest-funnel"
SKILL_DIR = PLUGIN_DIR / "skills" / "funnel-signal-comparison"
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"

#: The skill lives in the repository, not in the sdist whose tests/ include
#: this module.
pytestmark = pytest.mark.skipif(
    not SKILL_MD.is_file(), reason="the skill (repository plugins/) is not present"
)

#: Frontmatter keys accepted by every client (Agent Skills specification;
#: claude.ai uploads reject anything else).
PORTABLE_KEYS = {"name", "description", "license", "compatibility", "metadata"}
REQUIRED_KEYS = {"name", "description"}
MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_SKILL_LINES = 500
TOC_THRESHOLD = 100
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESERVED = re.compile(r"claude|anthropic", re.I)
REFERENCE_FILES = {"tolerances.md", "results.md", "ci.md", "setup.md", "example-open-meteo.md"}

#: Command-line options of other programs that the skill may show inline.
NON_SERVER_OPTIONS = {"--scope"}

SAMPLE_NAME = "stockholm-2026-11-05-to-19.csv"
CREDIT = "[Weather data by Open-Meteo.com](https://open-meteo.com/)"
LICENCE = "[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)"


# --------------------------------------------------------------------------
# Parsing the skill files
# --------------------------------------------------------------------------


def skill_files() -> list[Path]:
    return [SKILL_MD, *sorted(REFERENCES.glob("*.md"))]


def rel(path: Path) -> str:
    return path.relative_to(SKILL_DIR).as_posix()


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``---`` frontmatter from the body.

    Only the YAML subset the skill uses is accepted: ``key: value`` lines
    and one level of nested ``key: value`` mappings (two-space indent).
    Anything else fails the test, which keeps the frontmatter simple enough
    for every client's parser.
    """
    assert text.startswith("---\n"), "SKILL.md must start with '---' frontmatter"
    end = text.index("\n---\n", 4)
    data: dict[str, Any] = {}
    current: dict[str, str] | None = None
    for line in text[4:end].splitlines():
        nested = re.fullmatch(r"  ([a-z][a-z0-9_-]*): (.+)", line)
        top = re.fullmatch(r"([a-z][a-z0-9_-]*):(?: (.+))?", line)
        if nested and current is not None:
            current[nested.group(1)] = unquote(nested.group(2))
        elif top and top.group(2) is not None:
            value = top.group(2)
            assert ": " not in value and not value.startswith(("'", '"', "|", ">")) or (
                value[0] in "'\"" and value[-1] == value[0]
            ), f"frontmatter value of {top.group(1)} needs quoting or is not a plain scalar"
            data[top.group(1)] = unquote(value)
            current = None
        elif top:
            current = {}
            data[top.group(1)] = current
        else:
            raise AssertionError(f"unsupported frontmatter line: {line!r}")
    return data, text[end + 5:]


def unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


@dataclass(frozen=True)
class CodeBlock:
    path: Path
    line: int
    lang: str
    text: str

    @property
    def where(self) -> str:
        return f"{rel(self.path)}:{self.line}"


_FENCE = re.compile(r"^( *)```(\w*)\n(.*?)^\1```", re.M | re.S)


def code_blocks(path: Path) -> list[CodeBlock]:
    text = path.read_text("utf-8")
    out = []
    for m in _FENCE.finditer(text):
        indent = len(m.group(1))
        body = "\n".join(ln[indent:] for ln in m.group(3).splitlines())
        out.append(CodeBlock(path, text.count("\n", 0, m.start()) + 1, m.group(2), body))
    return out


def prose(path: Path) -> str:
    """The file's text without fenced code blocks."""
    return _FENCE.sub("", path.read_text("utf-8"))


def inline_code(path: Path) -> list[str]:
    return re.findall(r"`([^`\n]+)`", prose(path))


@dataclass(frozen=True)
class ToolCall:
    block: CodeBlock
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class ConfigBlock:
    block: CodeBlock
    file: str
    data: dict[str, Any]


def json_blocks(path: Path) -> tuple[list[ToolCall], list[ConfigBlock]]:
    """Every ``json``/``jsonc`` block, which must start with ``// <tool>``
    (a tool-call example) or ``// config: <file>`` (a client configuration)."""
    calls: list[ToolCall] = []
    configs: list[ConfigBlock] = []
    for block in code_blocks(path):
        if block.lang not in ("json", "jsonc"):
            continue
        first, _, rest = block.text.partition("\n")
        marker = re.fullmatch(r"// (config: )?(\S+)", first.strip())
        assert marker, f"{block.where}: a JSON block must start with '// <tool>' or '// config: <file>'"
        try:
            data = json.loads(rest)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{block.where}: invalid JSON: {exc}") from None
        assert isinstance(data, dict), block.where
        if marker.group(1):
            configs.append(ConfigBlock(block, marker.group(2), data))
        else:
            calls.append(ToolCall(block, marker.group(2), data))
    return calls, configs


def all_calls() -> list[ToolCall]:
    return [c for p in skill_files() for c in json_blocks(p)[0]]


def calls_in(name: str) -> list[ToolCall]:
    return json_blocks(SKILL_DIR / name)[0]


# --------------------------------------------------------------------------
# What the server offers
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def tools() -> dict[str, Any]:
    async def run() -> Any:
        return await server.build_server().list_tools()

    return {t.name: t for t in asyncio.run(run())}


def property_names(schema: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "properties" and isinstance(value, dict):
                names |= set(value)
            names |= property_names(value)
    elif isinstance(schema, list):
        for value in schema:
            names |= property_names(value)
    return names


@functools.lru_cache(maxsize=1)
def known_fields() -> frozenset[str]:
    """Argument and result field names of all tools."""
    names: set[str] = set(tools())
    for tool in tools().values():
        names |= property_names(tool.input_schema)
        names |= property_names(tool.output_schema)
    return frozenset(names)


def server_options() -> set[str]:
    return {s for a in server._arg_parser()._actions for s in a.option_strings}


def known_env() -> set[str]:
    snippet_text = snippet._HEADER
    assert "SIMTEST_FUNNEL_DATA_ROOT" in snippet_text
    return {
        ALLOW_NETWORK_ENV, server.ALLOW_HOSTS_ENV, server.MAX_DOWNLOAD_ENV,
        server.FETCH_TIMEOUT_ENV, server.OUTPUT_DIR_ENV, snippet.DOWNLOAD_ENV,
        "SIMTEST_FUNNEL_DATA_ROOT",
    }


# --------------------------------------------------------------------------
# Running the examples against the server
# --------------------------------------------------------------------------


def resolve_paths(args: dict[str, Any]) -> dict[str, Any]:
    """Example paths are relative to a checkout; make them absolute."""
    out = dict(args)
    for key in ("path", "reference_path", "test_path"):
        if key in out:
            p = REPO_ROOT / out[key]
            assert out[key].startswith("examples/") and p.is_file(), (
                f"example input {out[key]!r} must be a file under examples/ of the repository"
            )
            out[key] = str(p)
    return out


@functools.lru_cache(maxsize=None)
def run_example(name: str, index: int) -> dict[str, Any]:
    """Structured result of the ``index``-th tool call of reference file
    ``name`` (or ``SKILL.md``), run through an in-process MCP client."""
    call = json_blocks(SKILL_DIR / name)[0][index]

    async def run() -> Any:
        async with Client(server.build_server()) as client:
            return await client.call_tool(call.tool, resolve_paths(call.args))

    result = asyncio.run(run())
    assert not result.is_error, f"{call.block.where}: {result.content}"
    content = result.structured_content
    assert isinstance(content, dict), call.block.where
    return content


def rows(result: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(r["column"], r["tolerance_set"]): r for r in result["rows"]}


def flatten(text: str) -> str:
    """Text with block-quote markers and line breaks folded into spaces."""
    return re.sub(r"\s+", " ", re.sub(r"(?m)^> ?", "", text))


def percent(fraction: float) -> str:
    return f"{100 * fraction:.1f} %"


# --------------------------------------------------------------------------
# Format: frontmatter, size, layout, links
# --------------------------------------------------------------------------


def test_frontmatter() -> None:
    meta, _ = parse_frontmatter(SKILL_MD.read_text("utf-8"))
    assert set(meta) <= PORTABLE_KEYS, f"non-portable keys: {set(meta) - PORTABLE_KEYS}"
    assert REQUIRED_KEYS <= set(meta)
    name = meta["name"]
    assert name == SKILL_DIR.name
    assert NAME_RE.fullmatch(name) and len(name) <= 64
    assert not RESERVED.search(name)
    description = meta["description"]
    assert isinstance(description, str) and 0 < len(description) <= MAX_DESCRIPTION
    assert not RESERVED.search(description)
    # Third person: starts with a verb in -s, no first or second person.
    assert re.match(r"[A-Z][a-z]+s\b", description), description[:40]
    assert not re.search(r"\b(I|me|my|we|our|you|your)\b", description, re.I)
    # What it does and when to use it, with the trigger terms of the spec.
    assert "Use when" in description
    for term in ("funnel", "tolerance tube", "simtest-funnel", "baseline", "CSV", "forecast"):
        assert term in description, term
    if "compatibility" in meta:
        assert 0 < len(meta["compatibility"]) <= MAX_COMPATIBILITY
    if "metadata" in meta:
        assert isinstance(meta["metadata"], dict)


def test_size_and_layout() -> None:
    text = SKILL_MD.read_text("utf-8")
    _, body = parse_frontmatter(text)
    assert len(text.splitlines()) < MAX_SKILL_LINES
    assert len(body.splitlines()) < MAX_SKILL_LINES
    # Only SKILL.md and one level of reference files; no scripts, no data.
    entries = {p.relative_to(SKILL_DIR).as_posix() for p in SKILL_DIR.rglob("*")}
    assert entries == {"SKILL.md", "references"} | {f"references/{f}" for f in REFERENCE_FILES}
    assert not list(PLUGIN_DIR.rglob("*.csv")), "no data files in the plugin directory"


def slug(heading: str) -> str:
    """GitHub's anchor for a Markdown heading."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    return {slug(h) for h in re.findall(r"^#{1,6} (.+)$", prose(path), re.M)}


def links(path: Path) -> list[str]:
    return re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", prose(path))


@pytest.mark.parametrize("path", skill_files(), ids=rel)
def test_links_resolve_inside_the_skill(path: Path) -> None:
    for link in links(path):
        if link.startswith("https://"):
            continue
        assert not link.startswith("http:"), f"{rel(path)}: use https: {link}"
        target_part, _, anchor = link.partition("#")
        target = (path.parent / target_part).resolve() if target_part else path
        assert target.is_file(), f"{rel(path)}: broken link {link}"
        assert target.is_relative_to(SKILL_DIR), (
            f"{rel(path)}: {link} leaves the skill directory (use an https link)"
        )
        if anchor:
            assert anchor in anchors(target), f"{rel(path)}: no heading for #{anchor}"
        if path != SKILL_MD:
            assert target in (path, SKILL_MD) or target.parent != REFERENCES, (
                f"{rel(path)} links to another reference file ({link}); keep references "
                "one level deep"
            )


def test_every_reference_is_linked_from_skill_md() -> None:
    linked = {
        (SKILL_DIR / ln.partition("#")[0]).resolve()
        for ln in links(SKILL_MD) if not ln.startswith("https://")
    }
    for name in REFERENCE_FILES:
        assert (REFERENCES / name).resolve() in linked, name


@pytest.mark.parametrize("path", skill_files()[1:], ids=rel)
def test_long_references_have_a_table_of_contents(path: Path) -> None:
    text = path.read_text("utf-8")
    if len(text.splitlines()) <= TOC_THRESHOLD:
        return
    assert "\n## Contents\n" in text, f"{rel(path)} has over {TOC_THRESHOLD} lines"
    toc = text.split("\n## Contents\n", 1)[1].split("\n## ", 1)[0]
    listed = set(re.findall(r"\]\(#([^)]+)\)", toc))
    headings = {slug(h) for h in re.findall(r"^## (.+)$", prose(path), re.M)} - {"contents"}
    assert headings <= listed, f"{rel(path)}: not in the contents: {headings - listed}"


@pytest.mark.parametrize("path", skill_files(), ids=rel)
def test_sample_is_credited(path: Path) -> None:
    text = path.read_text("utf-8")
    if SAMPLE_NAME in text or "Open-Meteo Previous Runs" in text:
        assert CREDIT in text and LICENCE in text, rel(path)


@pytest.mark.parametrize("path", skill_files(), ids=rel)
def test_no_copy_of_the_tool_reference(path: Path) -> None:
    """The tube formula and resolution rule stay in the tool description."""
    text = path.read_text("utf-8")
    for needle in ("half_x", "half_y", "= max(", "1e-10", "time_span_ref", "value_range_ref"):
        assert needle not in text, f"{rel(path)} restates the tool reference ({needle})"


# --------------------------------------------------------------------------
# Names: tools, arguments, result fields, options, environment variables
# --------------------------------------------------------------------------


def test_tool_calls_match_the_input_schemas() -> None:
    calls = all_calls()
    assert {c.tool for c in calls} == set(tools()), "every tool has an example"
    for call in calls:
        assert call.tool in tools(), f"{call.block.where}: unknown tool {call.tool}"
        # The input schemas refuse unknown names (additionalProperties:
        # false), so a renamed argument in an example fails here.
        schema = tools()[call.tool].input_schema
        errors = sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(call.args), key=str
        )
        assert not errors, f"{call.block.where} ({call.tool}): " + "; ".join(
            e.message for e in errors
        )


@pytest.mark.parametrize("path", skill_files(), ids=rel)
def test_inline_names_exist(path: Path) -> None:
    options = server_options()
    statuses = {s.name for s in funnel.Status}
    tolerance_schema = tools()["compare_signals"].input_schema["$defs"]["ToleranceSet"]
    for code in inline_code(path):
        where = f"{rel(path)}: `{code}`"
        if re.fullmatch(r"\w+_signals", code):
            assert code in tools(), f"{where} is not a tool"
        elif code.startswith("--"):
            option = code.split()[0]
            assert option in options | NON_SERVER_OPTIONS, f"{where} is not a server option"
        elif re.fullmatch(r"[a-z][a-z0-9]*(_[a-z0-9]+)+|[alr]tol[xy]", code):
            assert code in known_fields(), f"{where} is not an argument or result field"
        elif re.fullmatch(r"[A-Z]+(_[A-Z]+)+", code) and not code.startswith("SIMTEST_"):
            assert code in statuses, f"{where} is not a status name"
        elif code.startswith("{\"") and re.search(r"\"[alr]tol[xy]\"", code):
            errors = list(jsonschema.Draft202012Validator(tolerance_schema).iter_errors(
                json.loads(code)
            ))
            assert not errors, f"{where}: {[e.message for e in errors]}"


@pytest.mark.parametrize("path", skill_files(), ids=rel)
def test_options_and_environment_variables_exist(path: Path) -> None:
    text = path.read_text("utf-8")
    for env in re.findall(r"SIMTEST_FUNNEL_[A-Z_]+", text):
        assert env in known_env(), f"{rel(path)}: unknown environment variable {env}"
    options = server_options()
    for block in code_blocks(path):
        for line in block.text.splitlines():
            if "simtest-funnel-mcp " not in line or block.lang in ("json", "jsonc"):
                continue
            after = line.rsplit("simtest-funnel-mcp ", 1)[1]
            for option in re.findall(r"(?<!\S)--[a-z][a-z-]*", after):
                assert option in options, f"{block.where}: unknown server option {option}"
    for config in json_blocks(path)[1]:
        servers = config.data["mcpServers"]
        for entry in servers.values():
            args = entry.get("args", [])
            assert "simtest-funnel-mcp" in args, config.block.where
            after_args = args[args.index("simtest-funnel-mcp") + 1:]
            for arg in after_args:
                if arg.startswith("--"):
                    assert arg in options, f"{config.block.where}: unknown option {arg}"
            for env in entry.get("env", {}):
                assert env in known_env(), f"{config.block.where}: unknown variable {env}"


# --------------------------------------------------------------------------
# The examples run, and the numbers quoted next to them are the server's
# --------------------------------------------------------------------------


def test_every_example_runs_without_errors() -> None:
    for path in skill_files():
        for index, call in enumerate(json_blocks(path)[0]):
            result = run_example(rel(path), index)
            for row in result.get("rows", []):
                assert row["verdict"] != "error", f"{call.block.where}: {row.get('problem')}"
            assert not result.get("time_limit_reached"), call.block.where


def test_open_meteo_example_numbers() -> None:
    name = "references/example-open-meteo.md"
    text = (SKILL_DIR / name).read_text("utf-8")
    flat = flatten(text)
    tools_used = [c.tool for c in calls_in(name)]
    assert tools_used == ["describe_signals", "compare_signals", "compare_signals",
                          "compare_signals", "plot_signals"]

    d = run_example(name, 0)
    assert d["row_count"] == 360 and d["time"]["kind"] == "datetime"
    assert "360 rows" in text
    latest = next(c for c in d["columns"] if c["name"] == "temperature_2m (°C)")
    assert f"from {latest['min']:g} to {latest['max']:g} °C" in flat

    got = rows(run_example(name, 1))
    table = re.findall(r"\| `(day\d)` \| (pass|fail), (\d+) of 360 \| (pass|fail), (\d+) of 360 \|",
                       text)
    assert len(table) == 3
    for day, v1, n1, v2, n2 in table:
        for label, verdict, outside in (("2C", v1, n1), ("2C_3h", v2, n2)):
            row = got[(day, label)]
            assert row["points_compared"] == 360
            assert (row["verdict"], row.get("points_outside") or 0) == (verdict, int(outside)), (
                day, label,
            )
    day3 = got[("day3", "2C_3h")]
    day5 = got[("day5", "2C_3h")]
    assert f"({got[('day3', '2C')]['points_outside']} to {day3['points_outside']})" in flat
    assert f"({got[('day5', '2C')]['points_outside']} to {day5['points_outside']})" in flat
    assert f"{day3['points_outside']} of 360 hours ({percent(day3['fraction_of_points_outside'])})" in flat
    assert f"misses {day5['points_outside']} hours ({percent(day5['fraction_of_points_outside'])})" in flat
    assert f"up to {day5['worst']['deviation']:g} °C beyond the band" in flat
    worst_below = min(iv["worst_deviation"] for iv in day3["intervals"])
    worst_above = max(iv["worst_deviation"] for iv in day3["intervals"])
    assert day3["interval_count"] == 3
    assert f"worst {worst_below:g} °C beyond it" in flat
    assert f"worst +{worst_above:g} °C" in flat
    assert f"up to {abs(worst_below):g} °C beyond the band" in flat
    assert f"up to {worst_above:g} °C beyond the band" in flat

    sweep = rows(run_example(name, 2))
    assert [sweep[("day3", s)]["verdict"] for s in ("2C_3h", "3C_3h", "4C_3h")] == [
        "fail", "pass", "pass",
    ]
    assert "fails at 2 °C and passes at 3 °C and 4 °C" in flat

    window = rows(run_example(name, 3))
    assert window[("day3", "2C_3h")]["verdict"] == "pass"
    assert "It passes there" in text

    plot = run_example(name, 4)
    assert plot["row"]["points_outside"] == day3["points_outside"]
    assert plot["row"]["interval_count"] == 3 and "three shaded regions" in text


def test_results_example_matches_the_open_meteo_numbers() -> None:
    flat = flatten((REFERENCES / "results.md").read_text("utf-8"))
    day3 = rows(run_example("references/example-open-meteo.md", 1))[("day3", "2C_3h")]
    deviations = [iv["worst_deviation"] for iv in day3["intervals"]]
    assert (
        f"{day3['points_outside']} of 360 hourly points "
        f"({percent(day3['fraction_of_points_outside'])} of the time)"
    ) in flat
    assert f"up to {max(deviations):g} °C beyond the band" in flat
    assert f"up to {abs(min(deviations)):g} °C beyond the band" in flat
    worst = day3["worst"]
    assert worst["deviation"] == min(deviations)
    assert (
        f"up to {abs(worst['deviation']):g} °C beyond the band, "
        f"{abs(worst['difference']):g} °C below the latest run at {worst['x_iso'][11:16]}"
    ) in flat
    skill = flatten(SKILL_MD.read_text("utf-8"))
    assert (
        f"\"{abs(worst['deviation']):g} °C beyond the band, {abs(worst['difference']):g} °C "
        "below the reference\""
    ) in skill
    sweep = rows(run_example("references/example-open-meteo.md", 2))
    assert sweep[("day3", "3C_3h")]["verdict"] == "pass" and "passes with ±3 °C and ±3 h" in flat


def test_tolerances_example_numbers() -> None:
    name = "references/tolerances.md"
    flat = flatten((SKILL_DIR / name).read_text("utf-8"))
    sweep = rows(run_example(name, 0))
    assert sweep[("x", "1pct")]["verdict"] == "fail" and sweep[("x", "2pct")]["verdict"] == "fail"
    assert sweep[("x", "5pct")]["verdict"] == "pass"
    assert f"fails at 1 % ({sweep[('x', '1pct')]['points_outside']} of 1001 points outside)" in flat
    assert f"2 % ({sweep[('x', '2pct')]['points_outside']} of 1001)" in flat

    split = rows(run_example(name, 1))
    assert split[("x", "tight")]["verdict"] == split[("x", "tight_t")]["verdict"] == "pass"
    assert split[("y", "tight")]["verdict"] == "fail" and split[("y", "tight_t")]["verdict"] == "pass"
    assert split[("z", "tight")]["verdict"] == split[("z", "tight_t")]["verdict"] == "fail"
    assert (
        f"({split[('z', 'tight')]['points_outside']} of 1001 points outside without the time "
        f"tolerance, {split[('z', 'tight_t')]['points_outside']} with it)"
    ) in flat
    assert f"({split[('y', 'tight')]['points_outside']} of 1001 outside)" in flat

    per_column = run_example(name, 2)
    z = rows(per_column)[("z", "spec")]
    assert z["tolerances"]["atoly"] == 1.0 and z["tolerances"]["atolx"] == 0.01


def test_ci_example_returns_a_snippet_with_a_relative_path() -> None:
    name = "references/ci.md"
    call = calls_in(name)[0]
    assert call.args.get("include_snippet") is True

    async def run() -> Any:
        from mcp_types import ListRootsResult, Root

        async def roots(context: object) -> ListRootsResult:
            return ListRootsResult(roots=[Root(uri=REPO_ROOT.as_uri())])  # type: ignore[arg-type]

        async with Client(server.build_server(), list_roots_callback=roots) as client:
            return await client.call_tool(call.tool, resolve_paths(call.args))

    result = asyncio.run(run())
    content = result.structured_content
    assert isinstance(content, dict) and content["rows"][0]["verdict"] == "pass"
    expected = f"DATA_ROOT / 'examples/open-meteo/{SAMPLE_NAME}'"
    assert expected in content["snippet"]
    assert expected in (SKILL_DIR / name).read_text("utf-8")


# --------------------------------------------------------------------------
# The scenario evaluation cases (files only; run on demand with
# `claude plugin eval`, never in ordinary CI)
# --------------------------------------------------------------------------

EVALS = PLUGIN_DIR / "evals"
EVAL_CASES = sorted(p.parent for p in EVALS.glob("*/prompt.md"))
TOOL_PREFIX = "mcp__plugin_simtest-funnel_simtest-funnel__"


def test_eval_cases_are_complete() -> None:
    assert len(EVAL_CASES) == 9
    for case in EVAL_CASES:
        assert (case / "case.yaml").is_file() and (case / "scaffold.sh").is_file(), case.name
        assert f"name: {case.name}\n" in (case / "case.yaml").read_text("utf-8")
        graders = list((case / "graders").glob("*.md"))
        assert graders, case.name
        for grader in graders:
            text = grader.read_text("utf-8")
            assert re.match(r"---\ntype: (regex|tool_used|tool_order|file_exists|llm)\n", text), grader
            for tool in re.findall(r"^(?:tool|before|after): (\S+)$", text, re.M):
                if tool.startswith(TOOL_PREFIX):
                    assert tool.removeprefix(TOOL_PREFIX) in tools(), f"{grader}: {tool}"


@pytest.mark.parametrize("case", EVAL_CASES, ids=lambda p: p.name)
def test_eval_data_is_generated(case: Path, tmp_path: Path) -> None:
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(EVALS / "_data" / "make_data.py"), case.name, str(tmp_path)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    prompt = (case / "prompt.md").read_text("utf-8").split("\n---\n", 1)[1]
    for name in re.findall(r"[\w/.-]+\.csv", re.sub(r"https://\S+", "", prompt)):
        assert (tmp_path / name).is_file(), f"{case.name}: {name} is not generated"
