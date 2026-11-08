"""אימות קריפטוגרפי של Cf-Access-Jwt-Assertion.

אין אמון בכותרת אימייל לבדה. בלי issuer/audience מוגדרים — כישלון סגור.
JWKS מגיע מה-issuer שבקונפיג, או מ-``HEB_CAL_ACCESS_JWKS`` לבדיקות (בלי רשת).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ACCESS_JWT_HEADER = "Cf-Access-Jwt-Assertion"
JWKS_MAX_BYTES = 64 * 1024
JWKS_TIMEOUT = 5

_jwks_cache: dict = {"key": None, "value": None}


class AccessJwtError(Exception):
    pass


def access_issuer() -> str | None:
    raw = (os.getenv("CF_ACCESS_ISSUER") or os.getenv("HEB_CAL_ACCESS_ISSUER") or "").strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.username or parts.password:
        return None
    if parts.query or parts.fragment or (parts.path or "") not in {"", "/"}:
        return None
    host = (parts.hostname or "").lower()
    if not host or not host.isascii():
        return None
    return f"https://{host}"


def access_audience() -> str | None:
    raw = (os.getenv("CF_ACCESS_AUD") or os.getenv("HEB_CAL_ACCESS_AUD") or "").strip()
    return raw or None


def configured() -> bool:
    return bool(access_issuer() and access_audience())


def verify_access_jwt(token: str | None) -> dict:
    """מחזיר claims. זריקה אם לא תקף."""
    issuer = access_issuer()
    audience = access_audience()
    if not issuer or not audience:
        raise AccessJwtError("unconfigured")
    if not token or not isinstance(token, str) or token.count(".") != 2:
        raise AccessJwtError("missing")
    try:
        import jwt
        from jwt import PyJWK
    except ImportError as exc:
        raise AccessJwtError("unavailable") from exc

    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise AccessJwtError("invalid") from exc
    if header.get("alg") != "RS256":
        raise AccessJwtError("alg")
    jwks = _jwks(issuer)
    kid = header.get("kid")
    key = None
    for item in jwks.get("keys") or []:
        if not isinstance(item, dict):
            continue
        if kid and item.get("kid") not in (None, kid):
            continue
        try:
            key = PyJWK.from_dict(item).key
            if kid is None or item.get("kid") == kid:
                break
        except (ValueError, TypeError, AttributeError):
            continue
    if key is None:
        raise AccessJwtError("jwks")
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            leeway=30,
            options={"require": ["exp", "iss", "aud"]},
        )
    except jwt.InvalidTokenError as exc:
        raise AccessJwtError("invalid") from exc
    return claims


def email_from_claims(claims: dict) -> str | None:
    from app.users.emails import clean_google_email

    raw = claims.get("email")
    try:
        return clean_google_email(raw)
    except ValueError:
        return None


def _jwks(issuer: str) -> dict:
    inline = (os.getenv("HEB_CAL_ACCESS_JWKS") or "").strip()
    if inline:
        data = json.loads(inline)
        if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
            raise AccessJwtError("jwks")
        return data
    url = f"{issuer}/cdn-cgi/access/certs"
    cache_key = url
    cached = _jwks_cache
    if cached["key"] == cache_key and cached["value"] is not None:
        return cached["value"]
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=JWKS_TIMEOUT) as response:
            raw = response.read(JWKS_MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise AccessJwtError("jwks") from exc
    if len(raw) > JWKS_MAX_BYTES:
        raise AccessJwtError("jwks")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AccessJwtError("jwks") from exc
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise AccessJwtError("jwks")
    _jwks_cache["key"] = cache_key
    _jwks_cache["value"] = data
    return data
