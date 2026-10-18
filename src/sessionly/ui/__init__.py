"""PySide6 user interface. Widgets call services; they never run SQL directly."""

from __future__ import annotations

from datetime import datetime


def local_time(iso_utc: str | None, empty: str = "—") -> str:
    """Render a stored UTC timestamp in the computer's local time zone."""
    if not iso_utc:
        return empty
    return datetime.fromisoformat(iso_utc).astimezone().strftime("%d %b %Y, %H:%M")
