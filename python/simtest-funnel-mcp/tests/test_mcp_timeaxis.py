"""Date-time axes: ISO 8601 formatting, durations and x-range bounds."""

from __future__ import annotations

import pytest

from simtest_funnel_mcp.timeaxis import format_duration, format_iso, parse_iso_bound


@pytest.mark.parametrize(
    ("t", "zone", "expected"),
    [
        (1793836800.0, "none", "2026-11-05T00:00:00"),
        (1795132800.25, "offset", "2026-11-20T00:00:00.25Z"),
        (1795132800.123456, "offset", "2026-11-20T00:00:00.123456Z"),
        (0.0, "offset", "1970-01-01T00:00:00Z"),
        (-0.25, "none", "1969-12-31T23:59:59.75"),
        (-62135596800.0, "none", "0001-01-01T00:00:00"),
        (253402300799.0, "none", "9999-12-31T23:59:59"),
        (1795132800.9999996, "none", "2026-11-20T00:00:01"),  # rounds up to the next second
    ],
)
def test_format_iso(t: float, zone: str, expected: str) -> None:
    assert format_iso(t, zone) == expected


def test_format_iso_out_of_range_and_absent() -> None:
    assert format_iso(None, "none") is None
    assert format_iso(float("nan"), "none") is None
    assert format_iso(1e13, "none") is None  # beyond year 9999


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (10800, "PT3H"),
        (1292400, "P14DT23H"),
        (12924, "PT3H35M24S"),
        (0.5, "PT0.5S"),
        (5400, "PT1H30M"),
        (86400 + 3 * 3600, "P1DT3H"),
        (86400, "P1D"),
        (0, "PT0S"),
        (0.000001, "PT0.000001S"),
    ],
)
def test_format_duration(seconds: float, expected: str) -> None:
    assert format_duration(seconds) == expected


def test_parse_iso_bound_follows_the_cell_conversion() -> None:
    assert parse_iso_bound("2026-11-20T00:00") == (1795132800.0, False)
    assert parse_iso_bound("2026-11-20T01:00+01:00") == (1795132800.0, True)
    assert parse_iso_bound("2026-11-20T00:00:00.25Z") == (1795132800.25, True)
    with pytest.raises(ValueError, match="not an ISO 8601 date-time"):
        parse_iso_bound("2026-02-30T00:00")
    with pytest.raises(ValueError):
        parse_iso_bound("yesterday")
