"""Date-time time axes: ISO 8601 formatting, durations and x-range bounds.

Times on a date-time axis are float64 seconds since the Unix epoch (UTC),
as produced by :func:`simtest_funnel_mcp.reader.parse_iso`.
"""

from __future__ import annotations

import datetime as _dt
import math

import pandas as pd

from simtest_funnel_mcp.reader import parse_iso

#: Ordinal (``date.toordinal``) of 1970-01-01.
_EPOCH_ORDINAL = 719163


def format_iso(t: float | None, time_zone: str | None) -> str | None:
    """``t`` (epoch seconds) as ISO 8601 UTC: ``Z`` suffix unless the axis has
    no time zone; seconds always, fraction only when non-zero (at most 6
    digits). ``None`` for absent, non-finite or out-of-range values."""
    if t is None or not math.isfinite(t):
        return None
    sec = math.floor(t)
    us = round((t - sec) * 1e6)  # t - floor(t) is exact
    if us >= 1_000_000:
        sec, us = sec + 1, us - 1_000_000
    days, rem = divmod(int(sec), 86400)
    try:
        date = _dt.date.fromordinal(days + _EPOCH_ORDINAL)
    except (ValueError, OverflowError):
        return None
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    out = f"{date.isoformat()}T{h:02d}:{m:02d}:{s:02d}"
    if us:
        out += f".{us:06d}".rstrip("0")
    return out + ("" if time_zone == "none" else "Z")


def format_duration(seconds: float | None) -> str | None:
    """ISO 8601 duration (``PT3H``, ``P14DT23H``, ``PT0.5S``; microseconds at most)."""
    if seconds is None or not math.isfinite(seconds):
        return None
    sign = "-" if seconds < 0 else ""
    us = round(abs(seconds) * 1e6)
    days, us = divmod(us, 86_400_000_000)
    h, us = divmod(us, 3_600_000_000)
    m, us = divmod(us, 60_000_000)
    s, us = divmod(us, 1_000_000)
    out = f"{sign}P" + (f"{days}D" if days else "")
    time = (f"{h}H" if h else "") + (f"{m}M" if m else "")
    if s or us:
        time += f"{s}.{us:06d}".rstrip("0") + "S" if us else f"{s}S"
    if time:
        out += "T" + time
    elif not days:
        out += "T0S"
    return out


def parse_iso_bound(text: str) -> tuple[float, bool]:
    """``(epoch seconds, has time zone)`` of one ISO 8601 date-time, converted
    exactly as a time cell; raises ``ValueError`` if ``text`` is not one."""
    values, ok, zoned, _ = parse_iso(pd.Series([text.strip()], dtype=object))
    if not bool(ok[0]):
        raise ValueError(f"{text!r} is not an ISO 8601 date-time")
    return float(values[0]), bool(zoned[0])
