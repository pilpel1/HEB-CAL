"""כתובת iCal סודית: אימות, מיסוך, ומחיקת הסוד מהודעות."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

from app.gcal.errors import GcalUserError

_ALLOWED_HOST = "calendar.google.com"
_URL_IN_TEXT = re.compile(r"https?://\S+", re.IGNORECASE)
_MAX_LEN = 2000

INVALID_URL = (
    "הכתובת לא תקינה. צריך את הכתובת הסודית בפורמט iCal מיומן גוגל (מתחילה ב-https)."
)


def is_google_ical_url(value: str) -> bool:
    """רק https ל-calendar.google.com, בלי שם משתמש, עם נתיב iCal."""
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or len(text) > _MAX_LEN or any(ord(ch) < 32 for ch in text):
        return False
    parts = urlsplit(text)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or host != _ALLOWED_HOST:
        return False
    if parts.username or parts.password:
        return False
    if parts.port not in (None, 443):
        return False
    path = parts.path or ""
    if "\\" in path or not path.startswith("/calendar/ical/") or not path.endswith(".ics"):
        return False
    return True


def require_google_ical_url(value) -> str:
    """מחזיר את הכתובת אחרי strip. זורק הודעה בעברית בלי להדביק את הקלט.

    מסכה מהממשק (עם …) נדחית, כדי שלא תחליף את הסוד שנשמר.
    """
    if not isinstance(value, str) or "…" in value or "..." in value or not is_google_ical_url(value):
        raise GcalUserError(INVALID_URL)
    return value.strip()


def mask_ical_url(url: str | None = None) -> str:
    """אותה מסכה לכל מקור. לא חושפת מזהה יומן, מייל, או את הסוד."""
    del url
    return "https://calendar.google.com/calendar/ical/…/basic.ics"


def redact(text: str, secret: str | None = None) -> str:
    """מוריד כתובות מטקסט לפני שמירה או הדפסה."""
    cleaned = text or ""
    if secret:
        cleaned = cleaned.replace(secret, "[כתובת הוסרה]")
    return _URL_IN_TEXT.sub("[כתובת הוסרה]", cleaned)
