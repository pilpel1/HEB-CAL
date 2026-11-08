"""לקוחות רשומים מראש. אין DCR פתוח."""
from __future__ import annotations

import json
import secrets
from urllib.parse import urlsplit

from app.database import get_db
from app.oauth.crypto import hash_secret
from app.oauth.time import stamp, utc_now

NAME_MAX = 80
REDIRECT_MAX = 8


class OauthClientError(ValueError):
    pass


def _loopback_http(host: str) -> bool:
    return host.lower() in {"127.0.0.1", "localhost", "::1"}


def validate_redirect_uri(value: str) -> str:
    text = (value or "").strip()
    if not text or len(text) > 500:
        raise OauthClientError("כתובת הפניה לא תקינה")
    parts = urlsplit(text)
    if parts.scheme not in {"https", "http"}:
        raise OauthClientError("כתובת הפניה חייבת להיות https")
    if parts.scheme == "http" and not _loopback_http(parts.hostname or ""):
        raise OauthClientError("http מותר רק ל-localhost")
    if parts.username or parts.password or parts.fragment:
        raise OauthClientError("כתובת הפניה לא תקינה")
    if not parts.netloc:
        raise OauthClientError("כתובת הפניה לא תקינה")
    return text


def parse_redirect_uris(value) -> list[str]:
    if isinstance(value, str):
        items = [item.strip() for item in value.replace("\n", " ").replace(",", " ").split()]
    elif isinstance(value, list):
        items = [str(item).strip() for item in value]
    else:
        items = []
    uris = []
    seen = set()
    for item in items:
        if not item:
            continue
        uri = validate_redirect_uri(item)
        if uri in seen:
            continue
        seen.add(uri)
        uris.append(uri)
    if not uris:
        raise OauthClientError("צריך לפחות כתובת הפניה אחת")
    if len(uris) > REDIRECT_MAX:
        raise OauthClientError("יותר מדי כתובות הפניה")
    return uris


def _clean_name(value) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise OauthClientError("צריך שם ללקוח")
    if len(text) > NAME_MAX:
        raise OauthClientError("השם ארוך מדי")
    return text


def create_client(name, redirect_uris) -> tuple[str, str, dict]:
    """(client_id, secret once, public row)."""
    name = _clean_name(name)
    uris = parse_redirect_uris(redirect_uris)
    client_id = "hcc_" + secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(32)
    now = stamp(utc_now())
    db = get_db()
    db.execute(
        """
        INSERT INTO oauth_clients (client_id, secret_hash, name, redirect_uris, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (client_id, hash_secret(secret), name, json.dumps(uris, ensure_ascii=False), now),
    )
    db.commit()
    return client_id, secret, get_client(client_id)


def get_client(client_id: str | None) -> dict | None:
    if not client_id:
        return None
    db = get_db()
    row = db.execute(
        "SELECT * FROM oauth_clients WHERE client_id = ?",
        (client_id,),
    ).fetchone()
    if row is None:
        return None
    return _public(row)


def get_client_row(client_id: str | None):
    if not client_id:
        return None
    return get_db().execute(
        "SELECT * FROM oauth_clients WHERE client_id = ?",
        (client_id,),
    ).fetchone()


def list_clients() -> list[dict]:
    rows = get_db().execute(
        "SELECT * FROM oauth_clients ORDER BY id DESC"
    ).fetchall()
    return [_public(row) for row in rows]


def revoke_client(client_id: str) -> bool:
    from app.oauth.tokens import revoke_client_grants

    db = get_db()
    now = stamp(utc_now())
    cursor = db.execute(
        "UPDATE oauth_clients SET revoked_at = ? WHERE client_id = ? AND revoked_at IS NULL",
        (now, client_id),
    )
    revoke_client_grants(db, client_id, now)
    db.commit()
    return cursor.rowcount > 0


def redirect_allowed(row, redirect_uri: str) -> bool:
    if row is None or row["revoked_at"]:
        return False
    try:
        uris = json.loads(row["redirect_uris"])
    except (TypeError, ValueError):
        return False
    if not isinstance(uris, list):
        return False
    return redirect_uri in uris


def authenticate_client(client_id: str | None, secret: str | None) -> dict | None:
    from app.oauth.crypto import hashed_equals

    row = get_client_row(client_id)
    if row is None or row["revoked_at"]:
        if secret:
            hashed_equals(None, secret)
        return None
    stored = row["secret_hash"]
    if stored:
        if not secret or not hashed_equals(stored, secret):
            return None
    elif secret:
        return None
    return _public(row)


def _public(row) -> dict:
    try:
        uris = json.loads(row["redirect_uris"])
    except (TypeError, ValueError):
        uris = []
    return {
        "id": row["id"],
        "client_id": row["client_id"],
        "name": row["name"],
        "redirect_uris": uris if isinstance(uris, list) else [],
        "confidential": bool(row["secret_hash"]),
        "created_at": row["created_at"],
        "revoked_at": row["revoked_at"],
        "status": "revoked" if row["revoked_at"] else "active",
    }
