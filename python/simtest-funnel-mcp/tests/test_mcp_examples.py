"""The bundled Open-Meteo sample, its attribution and the README walkthrough
(offline; the live check runs only with SIMTEST_FUNNEL_LIVE=1)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import pytest
from conftest import OPEN_METEO_SAMPLE, REPO_ROOT, structured

from simtest_funnel_mcp import server
from simtest_funnel_mcp.fetch import ALLOW_NETWORK_ENV
from simtest_funnel_mcp.server import (
    compare_signals_impl,
    describe_signals_impl,
    plot_signals_impl,
)

README = REPO_ROOT / "python" / "simtest-funnel-mcp" / "README.md"
ATTRIBUTION = OPEN_METEO_SAMPLE.parent / "ATTRIBUTION.md"
LIVE_URL = (
    "https://previous-runs-api.open-meteo.com/v1/forecast?latitude=59.3293&longitude=18.0686"
    "&hourly=temperature_2m,temperature_2m_previous_day1,temperature_2m_previous_day3,"
    "temperature_2m_previous_day5&models=ecmwf_ifs&start_date=2026-11-05&end_date=2026-11-19"
    "&format=csv"
)
RAW_URL = (
    "https://raw.githubusercontent.com/Symoptia/simtest-funnel/main/examples/open-meteo/"
    "stockholm-2026-11-05-to-19.csv"
)
COLUMNS = [
    "temperature_2m (°C)",
    "temperature_2m_previous_day1 (°C)",
    "temperature_2m_previous_day3 (°C)",
    "temperature_2m_previous_day5 (°C)",
]
SAMPLE_REL = "examples/open-meteo/stockholm-2026-11-05-to-19.csv"


def _readme() -> str:
    return README.read_text("utf-8")


def _walkthrough() -> str:
    text = _readme()
    start = text.index("## Example: was the forecast made N days ahead close enough?")
    return text[start:text.index("\n## ", start + 10)]


# --------------------------------------------------------------------------
# 7.1 / 7.2 the sample and its attribution
# --------------------------------------------------------------------------


def test_sample_layout() -> None:
    lines = OPEN_METEO_SAMPLE.read_text("utf-8").splitlines()
    assert lines[0].startswith("latitude,longitude,elevation,utc_offset_seconds")
    assert lines[1].split(",")[3:] == ["0", "GMT", "GMT"]
    assert lines[2] == ""
    assert lines[3] == "time," + ",".join(COLUMNS)
    rows = lines[4:]
    assert len(rows) == 360
    assert rows[0].startswith("2026-11-05T00:00,") and rows[-1].startswith("2026-11-19T23:00,")
    assert all(len(r.split(",")) == 5 and all(r.split(",")) for r in rows)


def test_attribution_records_the_sample() -> None:
    text = ATTRIBUTION.read_text("utf-8")
    sha = hashlib.sha256(OPEN_METEO_SAMPLE.read_bytes()).hexdigest()
    assert sha in text
    for needle in (
        "[Weather data by Open-Meteo.com](https://open-meteo.com/)",
        "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/",
        "ECMWF IFS HRES 9 km", "`models=ecmwf_ifs`", LIVE_URL, "2026-11-22",
        "**Changes:** none", "not station measurements", "non-commercial",
        "10,000 calls a day",
    ):
        assert needle in text, needle


def test_describe_the_sample() -> None:
    d = structured(describe_signals_impl(str(OPEN_METEO_SAMPLE), [], header_line=4))
    assert d["header_line"] == 4 and d["time_column"] == "time" and d["row_count"] == 360
    assert d["time"]["kind"] == "datetime" and d["time"]["time_zone"] == "none"
    assert d["time"]["sampling"]["uniform"] is True
    assert d["time"]["sampling"]["median_step_duration"] == "PT1H"
    assert [c["name"] for c in d["columns"]] == COLUMNS
    assert "source" not in d


# --------------------------------------------------------------------------
# 7.3 not packaged
# --------------------------------------------------------------------------


def test_sample_is_not_in_the_wheel_or_sdist(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not on PATH")
    proc = subprocess.run(
        [uv, "build", "--offline", "--quiet", str(README.parent), "-o", str(tmp_path)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    if proc.returncode != 0:
        pytest.skip(f"cannot build offline here: {proc.stderr[-300:]}")
    wheels = list(tmp_path.glob("*.whl"))
    sdists = list(tmp_path.glob("*.tar.gz"))
    assert wheels and sdists
    names = zipfile.ZipFile(wheels[0]).namelist()
    with tarfile.open(sdists[0]) as tar:
        names += tar.getnames()
    assert not [n for n in names if "stockholm" in n or "open-meteo" in n or "ATTRIBUTION" in n]


# --------------------------------------------------------------------------
# 7.4 the README walkthrough
# --------------------------------------------------------------------------


def _calls() -> dict[str, dict[str, Any]]:
    """The walkthrough's tool calls (```jsonc blocks headed // tool)."""
    out: dict[str, dict[str, Any]] = {}
    for block in re.findall(r"```jsonc\n(.*?)```", _walkthrough(), re.S):
        lines = [ln.strip() for ln in block.strip().splitlines()]
        assert lines[0].startswith("// "), block
        args = json.loads("\n".join(lines[1:]))
        for key in ("path", "reference_path"):
            if key in args:
                assert args[key] == SAMPLE_REL
                args[key] = str(OPEN_METEO_SAMPLE)
        out[lines[0][3:]] = args
    return out


def _table() -> dict[str, list[tuple[str, int, int, float]]]:
    """``{day: [(verdict, outside, total, percent) for 2C, 2C_3h]}`` from the README."""
    cell = r"(pass|fail), (\d+) of (\d+) \(([\d.]+) %\)"
    rows = re.findall(rf"\| `(day\d)`[^|]*\| {cell} \| {cell} \|", _walkthrough())
    assert len(rows) == 3, rows
    return {
        r[0]: [(r[1], int(r[2]), int(r[3]), float(r[4])),
               (r[5], int(r[6]), int(r[7]), float(r[8]))]
        for r in rows
    }


def test_walkthrough_numbers_match_the_server() -> None:
    calls = _calls()
    assert set(calls) == {"describe_signals", "compare_signals", "plot_signals"}
    d = structured(describe_signals_impl(
        calls["describe_signals"]["path"], [], header_line=calls["describe_signals"]["header_line"]
    ))
    assert d["row_count"] == 360 and d["time"]["kind"] == "datetime"

    c = calls["compare_signals"]
    from simtest_funnel_mcp.models import ColumnPair, ToleranceSet

    assert [t["label"] for t in c["tolerances"]] == ["2C", "2C_3h"]
    assert c["tolerances"] == [
        {"label": "2C", "atoly": 2}, {"label": "2C_3h", "atoly": 2, "atolx": 10800}
    ]
    result = structured(compare_signals_impl(
        c["reference_path"], None, [], header_line=c["header_line"],
        pairs=[ColumnPair(**p) for p in c["pairs"]],
        tolerances=[ToleranceSet(**t) for t in c["tolerances"]],
    ))
    got = {(r["column"], r["tolerance_set"]): r for r in result["rows"]}
    table = _table()
    for day, cells in table.items():
        for label, (verdict, outside, total, percent) in zip(("2C", "2C_3h"), cells):
            row = got[(day, label)]
            assert row["verdict"] == verdict, (day, label)
            assert row["points_compared"] == total == 360
            assert row.get("points_outside", 0) == outside, (day, label)
            assert round(100 * outside / total, 1) == percent
            if outside:
                assert round(100 * row["fraction_of_points_outside"], 1) == percent
        # The time tolerance forgives shifted forecasts.
        assert cells[1][1] <= cells[0][1], day
    assert table["day3"][1][1] < table["day3"][0][1]

    p = calls["plot_signals"]
    plot = structured(plot_signals_impl(
        p["reference_path"], None, [], column=p["column"], test_column=p["test_column"],
        header_line=p["header_line"], tolerance=ToleranceSet(**p["tolerance"]),
    ))
    assert plot["row"]["points_outside"] == table["day3"][1][1]


def test_walkthrough_credits_and_caveats() -> None:
    text = _walkthrough()
    for needle in (
        "[Weather data by Open-Meteo.com](https://open-meteo.com/)", "CC BY 4.0",
        "ATTRIBUTION.md", "not\nmeasured station temperature", "future both columns hold\nforecasts",
        "times are GMT", "non-commercial use\nonly", "fewer than 10,000 calls a day",
        "--allow-host raw.githubusercontent.com", "--allow-host previous-runs-api.open-meteo.com",
        "--allow-network", RAW_URL, LIVE_URL, '"header_line": 4',
    ):
        assert needle in text, needle


def test_readme_url_options_match_the_parser() -> None:
    parser = server._arg_parser()
    options = {
        s for a in parser._actions for s in a.option_strings
        if s.startswith(("--allow", "--max-download", "--fetch-timeout"))
    }
    assert options == {"--allow-network", "--allow-host", "--max-download-mb", "--fetch-timeout"}
    text = _readme()
    start = text.index("## Reading files from URLs")
    section = text[start:text.index("\n## ", start + 5)]
    for option in options:
        assert f"`{option}" in section, option
    envs = {
        ALLOW_NETWORK_ENV, server.ALLOW_HOSTS_ENV, server.MAX_DOWNLOAD_ENV,
        server.FETCH_TIMEOUT_ENV,
    }
    for env in envs:
        assert f"`{env}`" in section, env
    # No option or variable in the section that the server does not know.
    mentioned = set(re.findall(r"--(?:allow|max-download|fetch-timeout)[a-z-]*", section))
    assert mentioned <= options, mentioned - options
    vars_mentioned = set(re.findall(r"SIMTEST_FUNNEL_MCP_[A-Z_]+", section))
    assert vars_mentioned <= envs, vars_mentioned - envs
    assert "SIMTEST_FUNNEL_DOWNLOAD=1" in section
    help_text = parser.format_help()
    for env in envs:
        assert env in help_text, env


# --------------------------------------------------------------------------
# 7.5 optional live check
# --------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SIMTEST_FUNNEL_LIVE") != "1",
    reason="live Open-Meteo check; set SIMTEST_FUNNEL_LIVE=1 to run it",
)
def test_live_open_meteo_url(tmp_path: Path) -> None:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "simtest_funnel_mcp", "--allow-host", "previous-runs-api.open-meteo.com"],
        cwd=str(tmp_path),
    )

    async def run() -> Any:
        async with Client(params, read_timeout_seconds=90) as client:
            return await client.call_tool(
                "describe_signals", {"path": LIVE_URL, "header_line": 4}
            )

    result = asyncio.run(run())
    assert not result.is_error, result.content
    d = result.structured_content
    assert d["row_count"] == 360 and [c["name"] for c in d["columns"]] == COLUMNS
    assert d["source"]["url"] == LIVE_URL
    print("live source:", json.dumps(d["source"]))
