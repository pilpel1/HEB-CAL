"""CSRF לעדכון גרסה. אין סיסמה נפרדת: מי שכבר משתמש בלוח יכול לבדוק ולעדכן."""
from __future__ import annotations

import hmac
import secrets

from flask import jsonify, request, session

_CSRF_KEY = "hebcal_csrf"


def _same(left: str, right: str) -> bool:
    if not left or not right or len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def issue_csrf() -> str:
    token = session.get(_CSRF_KEY)
    if not isinstance(token, str) or len(token) < 16:
        token = secrets.token_urlsafe(32)
        session[_CSRF_KEY] = token
    return token


def require_csrf():
    sent = request.headers.get("X-CSRF-Token", "")
    expected = session.get(_CSRF_KEY, "")
    if not isinstance(expected, str) or not _same(sent, expected):
        return jsonify({"error": "הבקשה נחסמה. רעננו את העמוד ונסו שוב."}), 403
    return None
