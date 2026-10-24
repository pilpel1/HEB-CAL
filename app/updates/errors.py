"""שגיאות עדכון וטשטוש סודות לפני שהן מגיעות ללוג או למסך."""
from __future__ import annotations

import re

_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/=]+")
_GITHUB_TOKEN = re.compile(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]+")
_ACCESS = re.compile(r"(?i)x-access-token:[^@\s]+")
_AUTH_HEADER = re.compile(r"(?i)(authorization\s*[:=]\s*)\S+")
_NAMED_SECRET = re.compile(r"(?i)((?:token|password|secret|passwd)\s*[:=]\s*)\S+")


class UpdateError(Exception):
    """הודעה בעברית שמותר להראות למשתמש. `step` הוא שלב פנימי, לא פקודה."""

    def __init__(self, message: str, step: str = "error"):
        super().__init__(message)
        self.message = message
        self.step = step


def redact(text: str) -> str:
    """מוחק טוקנים אם הם דלפו לטקסט. לא נוגעים במחרוזת המקורית בזיכרון של הטוקן עצמו."""
    if not text:
        return ""
    cleaned = _ACCESS.sub("x-access-token:[מוסתר]", text)
    cleaned = _BEARER.sub("Bearer [מוסתר]", cleaned)
    cleaned = _GITHUB_TOKEN.sub("[מוסתר]", cleaned)
    cleaned = _AUTH_HEADER.sub(r"\1[מוסתר]", cleaned)
    cleaned = _NAMED_SECRET.sub(r"\1[מוסתר]", cleaned)
    return cleaned


def safe_detail(text: str) -> bool:
    """פרט שמותר לצרף להודעה. סוד, או טקסט ארוך, נשארים בחוץ."""
    if not text or len(text) > 180:
        return False
    lowered = text.lower()
    blocked = ("token", "bearer", "authorization", "ghp_", "github_pat_", "password", "secret")
    return not any(word in lowered for word in blocked)
