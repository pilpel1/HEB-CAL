"""מקור ציבורי מהימן למשאב ה-MCP.

כתובות אבטחה (resource, resource_metadata, issuer) לא נגזרות מ-Host או
מ-X-Forwarded-*. רק ``HEB_CAL_PUBLIC_ORIGIN`` במפורש. ערך חסר, לא תקין,
או שמפיל את המפרס — None (404 / בלי resource_metadata). אף פעם לא 500.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}
_ENV = "HEB_CAL_PUBLIC_ORIGIN"
_BAD_CHARS = set('"\\<>\r\n\t')


def public_origin() -> str | None:
    """``https://hebcal.corcos.app`` או None. בלי סלאש בסוף."""
    try:
        return _parse_public_origin(os.getenv(_ENV) or "")
    except (ValueError, TypeError, AttributeError, UnicodeError, OverflowError):
        return None


def _parse_public_origin(raw: str) -> str | None:
    raw = raw.strip()
    if not raw or any(ch in _BAD_CHARS for ch in raw):
        return None
    parts = urlsplit(raw)
    scheme = (parts.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return None
    if parts.username or parts.password:
        return None
    if parts.query or parts.fragment:
        return None
    if (parts.path or "") not in {"", "/"}:
        return None
    host = (parts.hostname or "").lower()
    if not host or not host.isascii() or any(ch.isspace() for ch in host):
        return None
    if scheme == "http" and host not in _LOOPBACK:
        return None
    port = parts.port
    if port is not None:
        if port < 1 or port > 65535:
            return None
        if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
            port = None
    if ":" in host:
        host = f"[{host}]"
    authority = host if port is None else f"{host}:{port}"
    return f"{scheme}://{authority}"
