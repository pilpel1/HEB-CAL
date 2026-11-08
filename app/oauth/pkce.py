"""PKCE S256 בלבד. בלי plain."""
from __future__ import annotations

import base64
import hashlib
import re

_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43,128}$")


def s256_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def valid_verifier(value: str | None) -> bool:
    return isinstance(value, str) and _VERIFIER.fullmatch(value) is not None


def valid_challenge(value: str | None) -> bool:
    return isinstance(value, str) and _CHALLENGE.fullmatch(value) is not None


def verify_s256(verifier: str, challenge: str) -> bool:
    if not valid_verifier(verifier) or not valid_challenge(challenge):
        return False
    computed = s256_challenge(verifier)
    if len(computed) != len(challenge):
        return False
    import hmac

    return hmac.compare_digest(computed, challenge)
