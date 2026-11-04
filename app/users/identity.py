"""זיהוי לפי Cloudflare Access — בלי מערכת התחברות.

אם הכותרת ``Cf-Access-Authenticated-User-Email`` קיימת, ממפים אותה למשתמש
עם אותו ``google_email``. בלי כותרת מחזירים None. אף נתיב לא דורש את זה.
"""
from __future__ import annotations

ACCESS_EMAIL_HEADER = "Cf-Access-Authenticated-User-Email"


def access_email_from_headers(headers) -> str | None:
    """אימייל מהכותרת, מנורמל. בלי כותרת או ערך ריק — None.

    לא זורק על אימייל לא תקין: כותרת חיצונית לא אמורה להפיל את הדף.
    """
    if headers is None:
        return None
    raw = None
    getter = getattr(headers, "get", None)
    if callable(getter):
        raw = getter(ACCESS_EMAIL_HEADER)
        if raw is None:
            raw = getter("CF-Access-Authenticated-User-Email")
    elif isinstance(headers, dict):
        raw = headers.get(ACCESS_EMAIL_HEADER)
        if raw is None:
            lowered = {str(key).lower(): value for key, value in headers.items()}
            raw = lowered.get(ACCESS_EMAIL_HEADER.lower())
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    from app.users.emails import clean_google_email

    try:
        return clean_google_email(text)
    except ValueError:
        return None


def user_for_access_headers(headers) -> dict | None:
    """משתמש לפי האימייל בכותרת, או None אם אין כותרת / אין התאמה."""
    email = access_email_from_headers(headers)
    if not email:
        return None
    from app.reminders.repository import find_person_by_google_email

    return find_person_by_google_email(email)


def current_access_user() -> dict | None:
    """משתמש מהבקשה הנוכחית רק אם הכותרת קיימת. בלי בקשה — None."""
    try:
        from flask import has_request_context, request
    except ImportError:
        return None
    if not has_request_context():
        return None
    return user_for_access_headers(request.headers)
