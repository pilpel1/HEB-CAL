"""גיבוב סודות. הערך הגולמי לא נשמר."""
from __future__ import annotations

import hashlib
import hmac
import secrets

ACCESS_PREFIX = "hcoa_"
REFRESH_PREFIX = "hcor_"
CODE_PREFIX = "hcac_"


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hashed_equals(stored: str | None, offered: str) -> bool:
    expected = stored if stored else hash_secret("missing-oauth-secret")
    actual = hash_secret(offered)
    return bool(stored) and hmac.compare_digest(expected, actual)


def new_token(prefix: str) -> str:
    return prefix + secrets.token_urlsafe(32)
