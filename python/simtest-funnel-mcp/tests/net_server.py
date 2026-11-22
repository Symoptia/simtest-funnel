"""Test-only launcher: the real ``simtest-funnel-mcp`` main() whose fetcher
resolves the test host names to 127.0.0.1, allows that address and trusts
the test CA. Usage: ``python net_server.py CA_PEM [server options...]``.

Production code has no such switch; this file lives in the tests only.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from urlserver import CountingResolver, client_context, loopback_allowed

from simtest_funnel_mcp import server
from simtest_funnel_mcp.fetch import FetchConfig, Fetcher


def _create(cls: Any, config: FetchConfig, fetcher: Fetcher | None = None) -> server.Network:
    test = Fetcher(
        config,
        resolver=CountingResolver(),
        address_policy=loopback_allowed,
        ssl_context=client_context(Path(sys.argv[1])),
    )
    return _real(config, test)


_real = server.Network.create
server.Network.create = classmethod(_create)  # type: ignore[method-assign, assignment]

if __name__ == "__main__":
    server.main(sys.argv[2:])
