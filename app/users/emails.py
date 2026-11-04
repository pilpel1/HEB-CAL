"""אימייל גוגל למשתמש: lowercase, ייחודי, אופציונלי."""
from __future__ import annotations

import re

_EMAIL = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
_EMAIL_MAX = 254


def clean_google_email(value) -> str | None:
    """מחזיר אימייל מנורמל או None. מחרוזת ריקה = אין אימייל."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if len(text) > _EMAIL_MAX:
        raise ValueError("האימייל ארוך מדי")
    if not _EMAIL.fullmatch(text):
        raise ValueError("אימייל גוגל לא תקין")
    return text
