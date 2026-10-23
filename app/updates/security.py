"""כניסת מנהל ו-CSRF. הסיסמה נשארת במשתנה סביבה, לא במסד ולא בלוג."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from flask import jsonify, request, session

_FAILS: list[float] = []
_WINDOW_SECONDS = 900
_MAX_FAILS = 8
_CSRF_KEY = "hebcal_csrf"
_ADMIN_KEY = "hebcal_admin"


def reset_failures() -> None:
    _FAILS.clear()


def _too_many() -> bool:
    now = time.time()
    fresh = [stamp for stamp in _FAILS if now - stamp < _WINDOW_SECONDS]
    _FAILS[:] = fresh
    return len(_FAILS) >= _MAX_FAILS


def _note_failure() -> None:
    _FAILS.append(time.time())


def passwords_match(given: str, expected: str) -> bool:
    if not given or not expected:
        return False
    return hmac.compare_digest(
        hashlib.sha256(given.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )


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


def rotate_csrf() -> str:
    token = secrets.token_urlsafe(32)
    session[_CSRF_KEY] = token
    return token


def is_admin() -> bool:
    return session.get(_ADMIN_KEY) is True


def require_csrf():
    sent = request.headers.get("X-CSRF-Token", "")
    expected = session.get(_CSRF_KEY, "")
    if not isinstance(expected, str) or not _same(sent, expected):
        return jsonify({"error": "הבקשה נחסמה. רעננו את העמוד ונסו שוב."}), 403
    return None


def require_admin():
    if not is_admin():
        return jsonify({"error": "צריך להתחבר כמנהל כדי לעדכן."}), 401
    return None


def login_admin(password: str, configured: str | None):
    if _too_many():
        return jsonify({"error": "יותר מדי ניסיונות. נסו שוב בעוד רבע שעה."}), 429
    if not configured:
        return jsonify({
            "error": "עדכון חסום עד שמגדירים ADMIN_PASSWORD בקובץ .env ומפעילים מחדש.",
        }), 403
    if not isinstance(password, str) or len(password) > 200 or not passwords_match(password, configured):
        _note_failure()
        return jsonify({"error": "הסיסמה שגויה."}), 401
    reset_failures()
    session[_ADMIN_KEY] = True
    token = rotate_csrf()
    session.modified = True
    return jsonify({"ok": True, "csrf_token": token})


def logout_admin():
    session.pop(_ADMIN_KEY, None)
    rotate_csrf()
    return jsonify({"ok": True, "csrf_token": session.get(_CSRF_KEY)})
