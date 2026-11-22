"""Shared fixtures for the simtest-funnel-mcp tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DIR = REPO_ROOT / "examples" / "web" / "public"

WriteCsv = Callable[[str, str], Path]


@pytest.fixture
def demo_reference() -> Path:
    return DEMO_DIR / "reference.csv"


@pytest.fixture
def demo_test() -> Path:
    return DEMO_DIR / "test.csv"


@pytest.fixture
def write_csv(tmp_path: Path) -> WriteCsv:
    """Write ``text`` to ``tmp_path / name`` and return the path."""

    def write(name: str, text: str) -> Path:
        p = tmp_path / name
        p.write_text(text, encoding="utf-8")
        return p

    return write


def structured(result: Any) -> dict[str, Any]:
    """Structured content of a ``CallToolResult`` (asserting it is present)."""
    content = result.structured_content
    assert isinstance(content, dict), result
    return content


# --------------------------------------------------------------------------
# Open-Meteo-shaped files (synthetic values, offline)
# --------------------------------------------------------------------------

#: The preamble of an Open-Meteo CSV download (metadata names and values).
OPEN_METEO_PREAMBLE = (
    "latitude,longitude,elevation,utc_offset_seconds,timezone,timezone_abbreviation\n"
    "59.33,18.07,21.0,0,GMT,GMT\n"
    "\n"
)
OPEN_METEO_REF = "temperature_2m (°C)"
OPEN_METEO_DAYS = (1, 3, 5)
#: Time cells run hourly from 2026-11-05T00:00 to 2026-11-19T23:00 (15 days).
OPEN_METEO_START = 1793836800  # 2026-11-05T00:00:00Z
OPEN_METEO_HOURS = 360


def open_meteo_column(day: int) -> str:
    return f"temperature_2m_previous_day{day} (°C)"


def open_meteo_values() -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Epoch-second times and synthetic temperatures (rounded to 0.1 °C like
    Open-Meteo). The forecast made ``day`` days ahead is shifted in time by
    ``day`` hours and offset by ``0.3 * day`` °C, so day 1 is close, day 5 is
    not."""
    t = OPEN_METEO_START + 3600 * np.arange(OPEN_METEO_HOURS)
    hours = np.arange(OPEN_METEO_HOURS, dtype=np.float64)

    def curve(h: np.ndarray) -> np.ndarray:
        return 3.0 + 4.0 * np.sin(2 * np.pi * (h - 9) / 24) + 2.0 * np.sin(h / 50.0)

    cols = {OPEN_METEO_REF: np.round(curve(hours), 1)}
    for day in OPEN_METEO_DAYS:
        cols[open_meteo_column(day)] = np.round(curve(hours - day) + 0.3 * day, 1)
    return t, cols


def open_meteo_text(*, iso: bool = True, preamble: bool = True) -> str:
    """The CSV text: preamble, header ``time,temperature_2m (°C),...`` and
    hourly rows with times like ``2026-11-05T00:00`` (or epoch seconds)."""
    t, cols = open_meteo_values()
    header = "time," + ",".join(cols)
    times = (
        np.datetime_as_string(t.astype("datetime64[s]"), unit="m").tolist()
        if iso else [str(int(v)) for v in t]
    )
    rows = [
        ",".join([times[i]] + [f"{c[i]:.1f}" for c in cols.values()]) for i in range(len(t))
    ]
    return (OPEN_METEO_PREAMBLE if preamble else "") + header + "\n" + "\n".join(rows) + "\n"


@pytest.fixture
def open_meteo(write_csv: WriteCsv) -> Path:
    """Open-Meteo Previous Runs layout: header on line 4, ISO times, no zone."""
    return write_csv("open_meteo.csv", open_meteo_text())
