"""Tool registration, schemas, argument validation and roots (in-process client)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp import Client
from mcp_types import ListRootsResult, Root

from simtest_funnel_mcp.server import mcp


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
    assert set(tools) == {"describe_signals", "compare_signals"}
    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.open_world_hint is False
        assert tool.output_schema is not None
        assert "roots" not in tool.input_schema["properties"]
    description = tools["compare_signals"].description or ""
    for needle in (
        "atolx", "atoly", "ltolx", "ltoly", "rtolx", "rtoly",
        "half_x = max(atolx, rtolx * time_span_ref, ltolx * |t|)",
        "TOLERANCE IN X",
        '"1 % in y, 0.5 s in x": {"rtoly": 0.01, "atolx": 0.5}',
        "rtol = 0.002",
    ):
        assert needle in description, needle
    assert set(tools["describe_signals"].input_schema["properties"]) == {
        "path", "columns", "max_columns",
    }
    props = tools["compare_signals"].input_schema["properties"]
    assert set(props) == {
        "reference_path", "test_path", "columns", "tolerances", "column_tolerances",
        "x_range", "max_intervals", "max_rows", "include_snippet",
    }


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


def test_description_states_constant_reference_fallback() -> None:
    from simtest_funnel_mcp.server import COMPARE_DESCRIPTION

    assert "falls back\nto rtol * max|reference value|" in COMPARE_DESCRIPTION
    assert "give atoly explicitly" in COMPARE_DESCRIPTION
    assert "within\nx_range, both files cover the same time span" in COMPARE_DESCRIPTION


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
