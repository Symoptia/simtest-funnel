"""Local MCP server for funnel (tolerance-tube) comparison of CSV signals.

The server is a thin adapter over :mod:`simtest.funnel`: it reads local CSV
files, calls the library and returns compact, bounded results. Start it with
the ``simtest-funnel-mcp`` console script (stdio transport).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

try:
    __version__ = _dist_version("simtest-funnel-mcp")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"

__all__ = ["__version__"]
