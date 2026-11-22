"""Unknown argument names are refused; schemas, descriptions and versions."""

from __future__ import annotations

import asyncio
import importlib.metadata
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from simtest_funnel_mcp import __version__, library_version, server
from simtest_funnel_mcp.arguments import strip_titles, unknown_message
from simtest_funnel_mcp.fetch import FetchConfig


def _call(name: str, args: dict[str, Any]) -> Any:
    async def run() -> Any:
        async with Client(server.build_server()) as client:
            return await client.call_tool(name, args)

    return asyncio.run(run())


def _tools() -> dict[str, Any]:
    async def run() -> Any:
        async with Client(server.build_server()) as client:
            return await client.list_tools()

    return {t.name: t for t in asyncio.run(run()).tools}


def _error(name: str, args: dict[str, Any]) -> str:
    result = _call(name, args)
    assert result.is_error, result.content
    text = result.content[0].text
    assert isinstance(text, str)
    return text


# --------------------------------------------------------------------------
# Unknown names, top level and nested, in every tool
# --------------------------------------------------------------------------


def test_misspelt_header_line_is_refused_not_ignored(open_meteo: Path) -> None:
    text = _error("describe_signals", {"path": str(open_meteo), "header_lin": 4})
    assert text == (
        "Error executing tool describe_signals: invalid arguments: unknown argument "
        "'header_lin'; did you mean 'header_line'?"
    )
    # Spelled correctly, the same call reads the 360 data rows.
    ok = _call("describe_signals", {"path": str(open_meteo), "header_line": 4})
    assert not ok.is_error and ok.structured_content["row_count"] == 360


@pytest.mark.parametrize(
    ("tool", "args", "expected"),
    [
        ("describe_signals", {"path": "a.csv", "colums": ["x"]},
         "unknown argument 'colums'; did you mean 'columns'?"),
        ("compare_signals", {"reference_path": "a.csv", "test_pth": "b.csv"},
         "unknown argument 'test_pth'; did you mean 'test_path'?"),
        ("plot_signals", {"reference_path": "a.csv", "column": "x", "outputpath": "p.svg"},
         "unknown argument 'outputpath'; did you mean 'output_path'?"),
        ("plot_signals", {"reference_path": "a.csv", "column": "x", "roots": []},
         "unknown argument 'roots' (accepted: reference_path, column, test_path,"),
    ],
)
def test_unknown_top_level_arguments(tool: str, args: dict[str, Any], expected: str) -> None:
    assert expected in _error(tool, args)


@pytest.mark.parametrize(
    ("tool", "args", "expected"),
    [
        ("compare_signals",
         {"reference_path": "a", "test_path": "b", "tolerances": [{"atoly_": 1}]},
         "tolerances[0]: unknown argument 'atoly_'; did you mean 'atoly'?"),
        ("compare_signals",
         {"reference_path": "a", "pairs": [{"reference": "x", "tset": "y"}]},
         "pairs[0]: unknown argument 'tset'; did you mean 'test'?"),
        ("compare_signals",
         {"reference_path": "a", "test_path": "b", "x_range": {"low": 0}},
         "x_range: unknown argument 'low'; did you mean 'lo'?"),
        ("compare_signals",
         {"reference_path": "a", "test_path": "b", "column_tolerances": {"x": {"atolxx": 1}}},
         "column_tolerances.x: unknown argument 'atolxx'; did you mean 'atolx'?"),
        ("plot_signals",
         {"reference_path": "a", "column": "x", "tolerance": {"rtol_y": 0.01}},
         "tolerance: unknown argument 'rtol_y'; did you mean 'rtoly'?"),
        ("plot_signals",
         {"reference_path": "a", "column": "x", "x_range": {"lo": 0, "hi": 1, "high": 2}},
         "x_range: unknown argument 'high'; did you mean 'hi'?"),
    ],
)
def test_unknown_nested_names(tool: str, args: dict[str, Any], expected: str) -> None:
    assert expected in _error(tool, args)


def test_several_faults_are_listed_one_per_line() -> None:
    text = _error("compare_signals", {
        "reference_path": "a", "test_path": "b", "header_line": 0,
        "tolerances": [{"atoly": 1}, {"atolx": -1}],
    })
    assert text.startswith("Error executing tool compare_signals: invalid arguments:\n- ")
    assert "- header_line: Input should be greater than or equal to 1 (got 0)" in text
    assert "- tolerances[1].atolx: Input should be greater than or equal to 0 (got -1)" in text


def test_json_encoded_nested_objects_are_checked_too() -> None:
    text = _error("compare_signals", {
        "reference_path": "a", "test_path": "b", "tolerances": '[{"atly": 1}]',
    })
    assert "unknown argument 'atly'; did you mean 'atoly'?" in text


def test_unknown_message_without_a_close_match_lists_the_names() -> None:
    assert unknown_message(["zzz"], ["lo", "hi"]) == "unknown argument 'zzz' (accepted: lo, hi)"


# --------------------------------------------------------------------------
# The published schemas say the same
# --------------------------------------------------------------------------


def _objects(schema: Any) -> list[dict[str, Any]]:
    """Every sub-schema that lists properties."""
    out: list[dict[str, Any]] = []
    if isinstance(schema, dict):
        if "properties" in schema:
            out.append(schema)
        for key, value in schema.items():
            if key == "properties":
                for sub in value.values():
                    out += _objects(sub)
            else:
                out += _objects(value)
    elif isinstance(schema, list):
        for value in schema:
            out += _objects(value)
    return out


def test_input_schemas_refuse_additional_properties_everywhere() -> None:
    for name, tool in _tools().items():
        objects = _objects(tool.input_schema)
        assert tool.input_schema in objects, name
        for obj in objects:
            assert obj.get("additionalProperties") is False, (name, sorted(obj["properties"]))
    defs = _tools()["compare_signals"].input_schema["$defs"]
    assert {"ToleranceSet", "ToleranceSpec", "ColumnPair", "XRange"} <= set(defs)


def test_schemas_carry_no_generated_titles() -> None:
    for tool in _tools().values():
        assert '"title"' not in str(tool.input_schema).replace("'", '"')
        assert '"title"' not in str(tool.output_schema).replace("'", '"')


def test_strip_titles_keeps_properties_named_title() -> None:
    schema = {"title": "M", "properties": {"title": {"title": "Title", "type": "string"}}}
    assert strip_titles(schema) == {"properties": {"title": {"type": "string"}}}


def test_output_schema_explains_deviation_difference_and_half_width() -> None:
    defs = _tools()["compare_signals"].output_schema["$defs"]
    worst = defs["Worst"]["properties"]
    assert "OUTSIDE the tube (not test minus reference)" in worst["deviation"]["description"]
    assert "Test value minus the reference value" in worst["difference"]["description"]
    assert "wider than the y tolerance where an x tolerance widens" in (
        worst["tube_half_width_y"]["description"]
    )
    assert "worst_difference" in defs["Interval"]["properties"]
    plot = _tools()["plot_signals"].output_schema["$defs"]
    assert "difference" in plot["Worst"]["properties"]


# --------------------------------------------------------------------------
# Description sizes (the field test found them too long) and wording
# --------------------------------------------------------------------------

#: Upper bounds in characters, about 15 % above the sizes of this change;
#: raise one deliberately, after removing what is no longer needed.
MAX_CHARS = {"instructions": 1200, "describe_signals": 2000, "compare_signals": 4100,
             "plot_signals": 2000}


def test_descriptions_stay_short() -> None:
    sizes = {name: len(t.description or "") for name, t in _tools().items()}
    sizes["instructions"] = len(server.INSTRUCTIONS)
    for name, size in sizes.items():
        assert size <= MAX_CHARS[name], (name, size)
    with_network = server.instructions(FetchConfig(allow_network=True))
    assert len(with_network) <= MAX_CHARS["instructions"] + 500


def test_descriptions_keep_the_decisive_examples() -> None:
    def flat(text: str) -> str:
        return " ".join(text.split())

    compare = flat(server.COMPARE_DESCRIPTION)
    plot = flat(server.PLOT_DESCRIPTION)
    instructions = flat(server.INSTRUCTIONS)
    assert '"atolx": 10800' in compare and "atolx 10800" in instructions
    assert "'pairs'" in instructions and "'test_column'" in instructions
    assert "header_line" in instructions
    assert '"lo": "2026-11-05T00:00"' in compare
    assert "inside a workspace root declared by the client" in plot
    assert "worst.deviation is the distance OUTSIDE the tube" in compare
    assert "worst.difference is test minus reference" in compare
    assert "tube_half_width_y" in compare


# --------------------------------------------------------------------------
# Versions
# --------------------------------------------------------------------------


#: Normalised PEP 440 release and pre-release versions (1.0.0, 1.0.0b21).
PEP440 = re.compile(r"\d+\.\d+\.\d+((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?")


def test_python_packages_report_pep_440_versions() -> None:
    mcp_version = importlib.metadata.version("simtest-funnel-mcp")
    lib_version = importlib.metadata.version("simtest-funnel")
    for v in (mcp_version, lib_version):
        assert PEP440.fullmatch(v), f"{v} is not in normalised PEP 440 form"
    assert __version__ == mcp_version
    assert library_version() == lib_version
    assert server.build_server().version == mcp_version
    parser = server._arg_parser()
    assert parser.format_help()  # --version prints the same string
    action = next(a for a in parser._actions if "--version" in a.option_strings)
    assert action.version == f"%(prog)s {mcp_version}"  # type: ignore[attr-defined]


RELEASE_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release-python-versions.sh"


@pytest.mark.skipif(
    not RELEASE_SCRIPT.is_file() or sys.platform != "linux",
    reason="repository release script (GNU sed) not available",
)
@pytest.mark.parametrize(
    ("semver", "pep440"),
    [("1.0.0-beta.22", "1.0.0b22"), ("1.0.0", "1.0.0"), ("1.1.0-rc.2", "1.1.0rc2"),
     ("0.1.0-alpha.1", "0.1.0a1")],
)
def test_release_writes_pep_440_versions(tmp_path: Path, semver: str, pep440: str) -> None:
    root = RELEASE_SCRIPT.parents[1]
    files = ["crates/simtest-funnel-python/pyproject.toml", "python/simtest-funnel-mcp/pyproject.toml"]
    (tmp_path / "scripts").mkdir()
    shutil.copy(RELEASE_SCRIPT, tmp_path / "scripts")
    for f in files:
        (tmp_path / f).parent.mkdir(parents=True)
        shutil.copy(root / f, tmp_path / f)
    subprocess.run(
        ["bash", str(tmp_path / "scripts" / RELEASE_SCRIPT.name), semver], check=True,
        capture_output=True,
    )
    for f in files:
        assert f'\nversion = "{pep440}"\n' in (tmp_path / f).read_text("utf-8"), f
    assert f'"simtest-funnel=={pep440}"' in (tmp_path / files[1]).read_text("utf-8")
    bad = subprocess.run(
        ["bash", str(tmp_path / "scripts" / RELEASE_SCRIPT.name), "1.0"], capture_output=True,
        check=False,
    )
    assert bad.returncode != 0
