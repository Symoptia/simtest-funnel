"""Local MCP server for funnel (tolerance-tube) comparison of CSV signals.

The server is a thin adapter over :mod:`simtest.funnel`: it reads local CSV
files, calls the library and returns compact, bounded results. Start it with
the ``simtest-funnel-mcp`` console script (stdio transport).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

# Versions as the installed distributions report them (PEP 440, e.g.
# 1.0.0b21): also the MCP serverInfo.version and the --version output.
try:
    __version__ = _dist_version("simtest-funnel-mcp")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0"


def library_version() -> str:
    """The installed ``simtest-funnel`` distribution's version (PEP 440)."""
    try:
        return _dist_version("simtest-funnel")
    except PackageNotFoundError:  # pragma: no cover - library not installed as a distribution
        import simtest.funnel as funnel

        return funnel.version()


__all__ = ["__version__", "library_version"]
