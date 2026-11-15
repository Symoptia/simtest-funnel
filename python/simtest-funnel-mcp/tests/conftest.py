"""Shared fixtures for the simtest-funnel-mcp tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

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
        p.write_text(text)
        return p

    return write


def structured(result: Any) -> dict[str, Any]:
    """Structured content of a ``CallToolResult`` (asserting it is present)."""
    content = result.structured_content
    assert isinstance(content, dict), result
    return content
