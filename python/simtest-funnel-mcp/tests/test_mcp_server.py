"""Tool registration, schemas, argument validation and roots (in-process client)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from mcp import Client
from mcp_types import ListRootsResult, Root

from simtest_funnel_mcp import server
from simtest_funnel_mcp.server import OUTPUT_DIR_ENV, mcp, parse_output_dirs


def _roots_callback(*dirs: Path) -> Any:
    async def callback(context: object) -> ListRootsResult:
        return ListRootsResult(roots=[Root(uri=d.resolve().as_uri()) for d in dirs])  # type: ignore[arg-type]

    return callback


def _call(name: str, args: dict[str, Any], roots: tuple[Path, ...] | None = None) -> Any:
    async def run() -> Any:
        kwargs: dict[str, Any] = {}
        if roots is not None:
            kwargs["list_roots_callback"] = _roots_callback(*roots)
        async with Client(mcp, **kwargs) as client:
            return await client.call_tool(name, args)

    return asyncio.run(run())


def test_tools_are_listed_with_annotations_and_schemas() -> None:
    async def run() -> Any:
        async with Client(mcp) as client:
            return await client.list_tools()

    tools = {t.name: t for t in asyncio.run(run()).tools}
    assert set(tools) == {"describe_signals", "compare_signals", "plot_signals"}
    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.open_world_hint is False
        assert tool.output_schema is not None
        assert "roots" not in tool.input_schema["properties"]
    for name in ("describe_signals", "compare_signals"):
        annotations = tools[name].annotations
        assert annotations is not None
        assert annotations.read_only_hint is True
        assert annotations.destructive_hint is False
    plot = tools["plot_signals"].annotations
    assert plot is not None
    assert plot.read_only_hint is False
    assert plot.destructive_hint is True
    assert plot.idempotent_hint is True
    assert set(tools["plot_signals"].input_schema["properties"]) == {
        "reference_path", "test_path", "column", "tolerance", "x_range", "output_path",
        "overwrite", "max_intervals", "time_limit",
        "test_column", "header_line", "test_header_line",
    }
    assert set(tools["plot_signals"].input_schema["required"]) == {
        "reference_path", "column",
    }
    description = _flat(tools["compare_signals"].description)
    for needle in (
        "atolx", "atoly", "ltolx", "ltoly", "rtolx", "rtoly",
        "half_x = max(atolx, rtolx * time_span_ref, ltolx * |t|)",
        "TOLERANCE IN X",
        '"1 % in y, 0.5 s in x": {"rtoly": 0.01, "atolx": 0.5}',
        "rtoly = 0.002",
        "x: all 0 (NO time tolerance)",
    ):
        assert needle in description, needle
    assert set(tools["describe_signals"].input_schema["properties"]) == {
        "path", "columns", "max_columns", "header_line",
    }
    props = tools["compare_signals"].input_schema["properties"]
    assert set(props) == {
        "reference_path", "test_path", "columns", "tolerances", "column_tolerances",
        "x_range", "max_intervals", "max_rows", "include_snippet", "time_limit",
        "pairs", "header_line", "test_header_line",
    }
    for name in ("compare_signals", "plot_signals"):
        limit = tools[name].input_schema["properties"]["time_limit"]
        assert limit["default"] == 60
        assert limit["exclusiveMinimum"] == 0
        assert "time_limit" not in tools[name].input_schema.get("required", [])
    assert "time_limit" in (tools["compare_signals"].description or "")
    assert "not_completed" in (tools["compare_signals"].description or "")
    assert "time_limit" in (tools["plot_signals"].description or "")


def test_unknown_coefficient_is_rejected(demo_reference: Path, demo_test: Path) -> None:
    result = _call(
        "compare_signals",
        {
            "reference_path": str(demo_reference),
            "test_path": str(demo_test),
            "tolerances": [{"rtol_y": 0.01}],
        },
    )
    assert result.is_error
    assert "rtol_y" in result.content[0].text


def test_negative_tolerance_is_rejected(demo_reference: Path, demo_test: Path) -> None:
    result = _call(
        "compare_signals",
        {
            "reference_path": str(demo_reference),
            "test_path": str(demo_test),
            "tolerances": [{"atoly": -1}],
        },
    )
    assert result.is_error


def test_missing_file_is_an_error_result(tmp_path: Path, demo_test: Path) -> None:
    result = _call(
        "compare_signals",
        {"reference_path": str(tmp_path / "nope.csv"), "test_path": str(demo_test)},
    )
    assert result.is_error
    assert str(tmp_path / "nope.csv") in result.content[0].text


def test_roots_refuse_outside_paths(demo_reference: Path, tmp_path: Path) -> None:
    result = _call("describe_signals", {"path": str(demo_reference)}, roots=(tmp_path,))
    assert result.is_error
    text = result.content[0].text
    assert "outside the client's workspace roots" in text
    assert str(tmp_path.resolve()) in text


def test_roots_accept_inside_paths_and_resolve_relative(demo_reference: Path) -> None:
    root = demo_reference.parent
    result = _call("describe_signals", {"path": "reference.csv"}, roots=(root,))
    assert not result.is_error, result.content
    assert result.structured_content["path"] == str(demo_reference.resolve())


def test_no_roots_capability_accepts_any_path(demo_reference: Path) -> None:
    result = _call("describe_signals", {"path": str(demo_reference)})
    assert not result.is_error


def test_root_uris_are_converted_with_url2pathname(monkeypatch: Any) -> None:
    # Regression: urlparse().path dropped the host and kept '/C:/...'.
    import nturl2path

    from simtest_funnel_mcp import server

    seen: list[str] = []

    def fake(path: str) -> str:
        seen.append(path)
        return "/converted"

    monkeypatch.setattr(server, "url2pathname", fake)
    notes: list[str] = []
    roots = ListRootsResult(
        roots=[
            Root(uri="file:///C:/Users/me/My%20Proj"),  # type: ignore[arg-type]
            Root(uri="file://localhost/srv/data"),  # type: ignore[arg-type]
            Root(uri="file://fileserver/share/proj"),  # type: ignore[arg-type]
        ]
    )
    paths = server.root_paths(roots, notes)
    assert seen == ["/C:/Users/me/My%20Proj", "/srv/data"]
    assert paths == [Path("/converted"), Path("/converted")]
    assert len(notes) == 1 and "fileserver" in notes[0] and "not local" in notes[0]
    # What the Windows implementation makes of the first one.
    assert nturl2path.url2pathname(seen[0]) == "C:\\Users\\me\\My Proj"


def test_non_local_root_is_ignored_with_a_note(demo_reference: Path) -> None:
    async def callback(context: object) -> ListRootsResult:
        return ListRootsResult(
            roots=[Root(uri="file://fileserver/share")]  # type: ignore[arg-type]
        )

    async def run() -> Any:
        async with Client(mcp, list_roots_callback=callback) as client:
            return await client.call_tool("describe_signals", {"path": str(demo_reference)})

    result = asyncio.run(run())
    assert not result.is_error, result.content
    assert any("fileserver" in n for n in result.structured_content["notes"])


def _flat(text: str | None) -> str:
    """``text`` with every run of whitespace folded into one space."""
    return " ".join((text or "").split())


def test_description_states_constant_reference_fallback() -> None:
    from simtest_funnel_mcp.server import COMPARE_DESCRIPTION

    text = _flat(COMPARE_DESCRIPTION)
    assert "falls back to rtol * max|reference value|" in text
    assert "give atoly explicitly" in text
    assert "within x_range, both files cover the same time span" in text


def test_non_finite_x_range_is_rejected_over_the_protocol(
    demo_reference: Path, demo_test: Path
) -> None:
    result = _call(
        "compare_signals",
        {
            "reference_path": str(demo_reference),
            "test_path": str(demo_test),
            "x_range": {"lo": "-inf"},
        },
    )
    assert result.is_error


# --------------------------------------------------------------------------
# Where plot files may be written (roots or a configured output directory)
# --------------------------------------------------------------------------


def _plot_args(demo_reference: Path, demo_test: Path, output: str) -> dict[str, Any]:
    return {
        "reference_path": str(demo_reference),
        "test_path": str(demo_test),
        "column": "z",
        "output_path": output,
    }


def test_plot_without_roots_or_output_dir_refuses_to_write(
    demo_reference: Path, demo_test: Path, tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(server, "_output_dirs", [])
    target = tmp_path / "z.svg"
    result = _call("plot_signals", _plot_args(demo_reference, demo_test, str(target)))
    assert result.is_error
    text = result.content[0].text
    assert "--output-dir" in text and OUTPUT_DIR_ENV in text and "workspace roots" in text
    assert not target.exists()
    preview = _call(
        "plot_signals",
        {"reference_path": str(demo_reference), "test_path": str(demo_test), "column": "z"},
    )
    assert not preview.is_error and preview.content[1].mime_type == "image/png"


def test_plot_writes_into_configured_output_dir_without_roots(
    demo_reference: Path, demo_test: Path, tmp_path: Path, monkeypatch: Any
) -> None:
    out = (tmp_path / "plots").resolve()
    out.mkdir()
    monkeypatch.setattr(server, "_output_dirs", [out])
    ok = _call("plot_signals", _plot_args(demo_reference, demo_test, "z.svg"))
    assert not ok.is_error, ok.content
    assert ok.structured_content["file"]["path"] == str(out / "z.svg")
    refused = _call("plot_signals", _plot_args(demo_reference, demo_test, str(tmp_path / "z.svg")))
    assert refused.is_error
    assert "outside the configured output directories" in refused.content[0].text
    # With roots as well, a path inside either is allowed.
    root = (tmp_path / "root").resolve()
    root.mkdir()
    both = _call("plot_signals", _plot_args(demo_reference, demo_test, str(out / "b.svg")),
                 roots=(root, demo_reference.parent))
    assert not both.is_error, both.content
    in_root = _call("plot_signals", _plot_args(demo_reference, demo_test, "c.svg"),
                    roots=(root, demo_reference.parent))
    assert in_root.structured_content["file"]["path"] == str(root / "c.svg")


def test_parse_output_dirs(tmp_path: Path, monkeypatch: Any) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.chdir(tmp_path)
    assert parse_output_dirs([], None) == []
    assert parse_output_dirs([], "") == []
    assert parse_output_dirs(["a"], None) == [a.resolve()]
    assert parse_output_dirs(["a"], f"{b}{os.pathsep}{a}") == [a.resolve(), b.resolve()]
    with pytest.raises(ValueError, match=r"output directory 'missing' .* does not exist"):
        parse_output_dirs(["missing"], None)
    (tmp_path / "f.txt").write_text("x")
    with pytest.raises(ValueError, match="is not a directory"):
        parse_output_dirs([], str(tmp_path / "f.txt"))


def test_main_rejects_a_missing_output_dir(tmp_path: Path, capsys: Any) -> None:
    with pytest.raises(SystemExit) as info:
        server.main(["--output-dir", str(tmp_path / "missing")])
    assert info.value.code == 2
    err = capsys.readouterr().err
    assert "does not exist" in err and "--output-dir" in err


# --------------------------------------------------------------------------
# Pairs, header lines and date-time axes
# --------------------------------------------------------------------------


def _tools() -> dict[str, Any]:
    async def run() -> Any:
        async with Client(mcp) as client:
            return await client.list_tools()

    return {t.name: t for t in asyncio.run(run()).tools}


def _x_range_description(tool: Any) -> str:
    """The description of the ``x_range`` argument (may sit on a $ref'd wrapper)."""
    prop = tool.input_schema["properties"]["x_range"]
    return str(prop.get("description", ""))


def test_x_range_argument_descriptions_agree() -> None:
    """Both tools explain the bound units and the tube beyond the window."""
    tools = _tools()
    for name in ("compare_signals", "plot_signals"):
        text = _x_range_description(tools[name])
        assert "(seconds since 1970 on a date-time axis)" in text, name
        assert "only test points inside it are judged" in text, name
        assert "the tube of the whole reference there" in text, name
        assert "extended beyond the window as far as needed" in text, name
    plot = _flat(tools["plot_signals"].description)
    assert "x_range also sets the time window shown" in plot


def test_schemas_list_the_new_arguments() -> None:
    tools = _tools()
    for name in ("describe_signals", "compare_signals", "plot_signals"):
        props = tools[name].input_schema["properties"]
        assert props["header_line"]["minimum"] == 1 and props["header_line"]["default"] == 1
    for name in ("compare_signals", "plot_signals"):
        schema = tools[name].input_schema
        assert "test_path" not in schema["required"]
        assert schema["properties"]["test_header_line"]["default"] is None
    assert "pairs" in tools["compare_signals"].input_schema["properties"]
    assert "test_column" in tools["plot_signals"].input_schema["properties"]
    # x_range bounds accept numbers and ISO strings.
    defs = tools["compare_signals"].input_schema["$defs"]
    lo = defs["XRange"]["properties"]["lo"]
    assert {t.get("type") for t in lo["anyOf"]} >= {"number", "string"}


def test_output_schemas_list_the_new_optional_fields() -> None:
    tools = _tools()
    compare = tools["compare_signals"].output_schema
    assert compare is not None
    defs = compare["$defs"]
    assert {"header_line", "time_kind", "time_zone", "time_start_iso", "time_end_iso"} <= set(
        defs["FileInfo"]["properties"]
    )
    assert {"lo_iso", "hi_iso"} <= set(defs["RangeOut"]["properties"])
    assert "x_iso" in defs["Worst"]["properties"]
    assert {"start_x_iso", "end_x_iso", "worst_x_iso"} <= set(defs["Interval"]["properties"])
    assert {"reference_column", "test_column", "time_tolerance"} <= set(
        defs["Row"]["properties"]
    )
    assert {"reference_column", "test_column"} <= set(defs["NotCompleted"]["properties"])
    assert "time_tolerance" in defs["ToleranceSetOut"]["properties"]
    assert set(defs["TimeTolerance"]["properties"]) == {"seconds", "duration"}
    for field in ("reference_column", "test_column", "time_tolerance"):
        assert field not in defs["Row"].get("required", [])
    describe = tools["describe_signals"].output_schema
    assert describe is not None
    assert "header_line" in describe["properties"]
    d_defs = describe["$defs"]
    assert {"kind", "time_zone", "start_iso", "end_iso", "span_duration"} <= set(
        d_defs["TimeInfo"]["properties"]
    )
    assert "median_step_duration" in d_defs["Sampling"]["properties"]


def test_descriptions_explain_pairs_header_line_and_date_axis() -> None:
    from simtest_funnel_mcp.server import (
        COMPARE_DESCRIPTION,
        CSV_HELP,
        DESCRIBE_DESCRIPTION,
        INSTRUCTIONS,
        PLOT_DESCRIPTION,
    )

    compare = _flat(COMPARE_DESCRIPTION)
    for needle in (
        '"within 2 °C and 3 hours": {"atoly": 2, "atolx": 10800}',
        "'pairs' compares differently named columns",
        '"test": "temperature_2m_previous_day1 (°C)"',
        "row key",
        "label, else the test column",
        "test_path is optional with pairs",
        "test_header_line",
        "ltolx is refused",
        "time_tolerance",
        '{"lo": "2026-11-05T00:00", "hi": "2026-11-10T00:00"}',
        "x is seconds since 1970-01-01 UTC",
        "describe_signals",
    ):
        assert needle in compare, needle
    for needle in (
        "HEADER LINE: header_line", "suggests the header_line to pass",
        "seconds since 1970-01-01 UTC", "read as UTC", "both without time zone", "UTF-8",
    ):
        assert needle in CSV_HELP, needle
    # The CSV rules are stated once, in describe_signals (the first call).
    assert CSV_HELP in DESCRIBE_DESCRIPTION
    assert CSV_HELP not in COMPARE_DESCRIPTION and CSV_HELP not in PLOT_DESCRIPTION
    plot = _flat(PLOT_DESCRIPTION)
    assert "test_column" in plot and "(no time zone)" in plot
    assert "header_line" in INSTRUCTIONS and "'pairs'" in INSTRUCTIONS
    assert "atolx 10800" in INSTRUCTIONS
    # Fields the descriptions promise exist in the output schemas.
    tools = _tools()
    compare = tools["compare_signals"].output_schema
    assert compare is not None
    assert "time_tolerance" in compare["$defs"]["ToleranceSetOut"]["properties"]
    assert "reference_column" in compare["$defs"]["Row"]["properties"]


def test_one_file_pair_call_in_process(open_meteo: Path) -> None:
    result = _call(
        "compare_signals",
        {
            "reference_path": str(open_meteo),
            "header_line": 4,
            "pairs": [{"reference": "temperature_2m (°C)",
                       "test": "temperature_2m_previous_day1 (°C)", "label": "day1"}],
            "tolerances": [{"atoly": 2, "atolx": 10800}],
            "x_range": {"lo": "2026-11-06T00:00"},
        },
    )
    assert not result.is_error, result.content
    d = result.structured_content
    assert d["rows"][0]["column"] == "day1" and d["rows"][0]["verdict"] == "pass"
    assert d["x_range"]["lo_iso"] == "2026-11-06T00:00:00"


def test_bad_arguments_over_the_protocol(open_meteo: Path) -> None:
    base = {"reference_path": str(open_meteo)}
    assert _call("compare_signals", base).is_error  # neither test_path nor pairs
    assert _call("describe_signals", {"path": str(open_meteo), "header_line": 0}).is_error
    bad_pair = _call("compare_signals", {**base, "pairs": [{"reference": "a", "tst": "b"}]})
    assert bad_pair.is_error
    bad_bound = _call("compare_signals", {**base, "header_line": 4, "pairs": [
        {"reference": "temperature_2m (°C)", "test": "temperature_2m_previous_day1 (°C)"}],
        "x_range": {"lo": "next tuesday"}})
    assert bad_bound.is_error


def test_readme_open_meteo_example_runs_against_the_fixture(open_meteo: Path) -> None:
    import json
    import re

    from conftest import REPO_ROOT

    readme = (REPO_ROOT / "python" / "simtest-funnel-mcp" / "README.md").read_text("utf-8")
    blocks = [b for b in re.findall(r"```json\n(.*?)```", readme, re.S) if '"pairs"' in b]
    assert len(blocks) == 1
    args = json.loads(blocks[0])
    args["reference_path"] = str(open_meteo)
    result = _call("compare_signals", args)
    assert not result.is_error, result.content
    d = result.structured_content
    assert {r["column"] for r in d["rows"]} == {"day1", "day3", "day5"}
    assert d["tolerance_sets"][0]["time_tolerance"]["duration"] == "PT3H"


# --------------------------------------------------------------------------
# Network start-up options (add-mcp-url-ingestion)
# --------------------------------------------------------------------------


def _net_config(cli: list[str], env: dict[str, str] | None = None) -> Any:
    args = server._arg_parser().parse_args(cli)
    return server.parse_network_config(
        args.allow_network, args.allow_host, args.max_download_mb, args.fetch_timeout,
        env or {},
    )


def test_network_is_off_by_default() -> None:
    cfg = _net_config([])
    assert cfg.allow_network is False and cfg.allow_hosts == ()
    assert cfg.max_download_mb == 20 and cfg.fetch_timeout == 30


def test_network_options_and_environment() -> None:
    assert _net_config(["--allow-network"]).allow_network is True
    for value in ("1", "true", "YES", "on"):
        assert _net_config([], {"SIMTEST_FUNNEL_MCP_ALLOW_NETWORK": value}).allow_network
    for value in ("0", "false", "no", "off", ""):
        assert not _net_config([], {"SIMTEST_FUNNEL_MCP_ALLOW_NETWORK": value}).allow_network
    # --allow-host implies network access; hosts from CLI and env are united.
    cfg = _net_config(
        ["--allow-host", "Previous-Runs-API.open-meteo.com", "--allow-host", "a.example"],
        {"SIMTEST_FUNNEL_MCP_ALLOW_HOSTS": "b.example, a.example"},
    )
    assert cfg.allow_network is True
    assert cfg.allow_hosts == ("previous-runs-api.open-meteo.com", "a.example", "b.example")
    assert _net_config([], {"SIMTEST_FUNNEL_MCP_ALLOW_HOSTS": "x.example"}).allow_network
    # Numbers: the command line wins over the environment.
    env = {"SIMTEST_FUNNEL_MCP_MAX_DOWNLOAD_MB": "5", "SIMTEST_FUNNEL_MCP_FETCH_TIMEOUT": "7"}
    assert _net_config([], env).max_download_mb == 5
    assert _net_config([], env).fetch_timeout == 7
    cfg = _net_config(["--max-download-mb", "2.5", "--fetch-timeout", "12"], env)
    assert cfg.max_download_mb == 2.5 and cfg.fetch_timeout == 12
    assert _net_config(["--allow-host", "[2001:db8::1]"]).allow_hosts == ("2001:db8::1",)
    assert _net_config(["--allow-host", "Bücher.example"]).allow_hosts == (
        "xn--bcher-kva.example",
    )


@pytest.mark.parametrize(
    ("cli", "env", "needle"),
    [
        ([], {"SIMTEST_FUNNEL_MCP_ALLOW_NETWORK": "maybe"}, "SIMTEST_FUNNEL_MCP_ALLOW_NETWORK"),
        (["--allow-host", "https://example.org"], {}, "a scheme"),
        (["--allow-host", "*.example.org"], {}, "a wildcard"),
        (["--allow-host", "example.org/data"], {}, "a path"),
        (["--allow-host", "example.org:443"], {}, "a port"),
        (["--allow-host", "user@example.org"], {}, "user info"),
        ([], {"SIMTEST_FUNNEL_MCP_ALLOW_HOSTS": "a.example,*.b"}, "a wildcard"),
        (["--max-download-mb", "0"], {}, "--max-download-mb"),
        (["--max-download-mb", "-1"], {}, "--max-download-mb"),
        (["--max-download-mb", "lots"], {}, "--max-download-mb"),
        ([], {"SIMTEST_FUNNEL_MCP_MAX_DOWNLOAD_MB": "inf"}, "SIMTEST_FUNNEL_MCP_MAX_DOWNLOAD_MB"),
        (["--fetch-timeout", "0"], {}, "--fetch-timeout"),
        (["--fetch-timeout", "601"], {}, "at most 600"),
    ],
)
def test_bad_network_settings_are_rejected(
    cli: list[str], env: dict[str, str], needle: str
) -> None:
    with pytest.raises(ValueError) as info:
        _net_config(cli, env)
    assert needle in str(info.value)


def test_main_exits_on_a_bad_network_setting(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    monkeypatch.setenv("SIMTEST_FUNNEL_MCP_ALLOW_NETWORK", "maybe")
    with pytest.raises(SystemExit) as info:
        server.main([])
    assert info.value.code == 2
    err = capsys.readouterr().err
    assert "SIMTEST_FUNNEL_MCP_ALLOW_NETWORK" in err and "'maybe'" in err and "1, true" in err
    monkeypatch.delenv("SIMTEST_FUNNEL_MCP_ALLOW_NETWORK")
    with pytest.raises(SystemExit):
        server.main(["--max-download-mb", "0"])
    assert "--max-download-mb" in capsys.readouterr().err
