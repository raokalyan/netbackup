from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .settings import DISPLAY_TIMEZONE


def parse_utc_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_display_timestamp(value: str | None) -> str:
    """Format a stored UTC ISO timestamp for the web UI."""
    if not value:
        return ""
    localized = parse_utc_timestamp(value).astimezone(DISPLAY_TIMEZONE)
    tz_label = localized.tzname() or str(DISPLAY_TIMEZONE)
    return f"{localized.strftime('%Y-%m-%d %H:%M:%S')} {tz_label}"
