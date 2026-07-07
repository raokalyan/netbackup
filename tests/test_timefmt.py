from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from netbackup.timefmt import format_display_timestamp, parse_utc_timestamp


def test_parse_utc_timestamp_handles_z_suffix() -> None:
    parsed = parse_utc_timestamp("2026-07-07T22:15:30+00:00")
    assert parsed == datetime(2026, 7, 7, 22, 15, 30, tzinfo=timezone.utc)


def test_format_display_timestamp_uses_configured_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("netbackup.timefmt.DISPLAY_TIMEZONE", ZoneInfo("America/Los_Angeles"))
    formatted = format_display_timestamp("2026-07-07T22:15:30+00:00")
    assert formatted.startswith("2026-07-07 15:15:30")
