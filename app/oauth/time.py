"""שעון UTC ל-OAuth. בדיקות מחליפות את ``utc_now``."""
from __future__ import annotations

from datetime import datetime, timezone

_STAMP = "%Y-%m-%dT%H:%M:%SZ"


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(_STAMP)


def parse_stamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, _STAMP).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
