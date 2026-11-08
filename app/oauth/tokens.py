"""קודי הרשאה, טוקני גישה ורענון. סודות מגובבים. refresh מסתובב."""
from __future__ import annotations

import secrets
from datetime import timedelta

from app.database import get_db
from app.oauth.crypto import (
    ACCESS_PREFIX,
    CODE_PREFIX,
    REFRESH_PREFIX,
    hash_secret,
    hashed_equals,
    new_token,
)
from app.oauth.origin import public_origin
from app.oauth.pkce import verify_s256
from app.oauth.resource import mcp_resource_url
from app.oauth.scopes import permission_for
from app.oauth.time import parse_stamp, stamp, utc_now

CODE_SECONDS = 5 * 60
ACCESS_SECONDS = 15 * 60
REFRESH_DAYS = 30


def current_issuer() -> str | None:
    return public_origin()


def current_resource() -> str | None:
    origin = public_origin()
    return mcp_resource_url(origin) if origin else None


def bound_to_this_instance(issuer: str, resource: str) -> bool:
    here = current_issuer()
    mine = current_resource()
    return bool(here and mine and issuer == here and resource == mine)


def issue_code(
    *,
    client_id: str,
    user_id: int,
    resource: str,
    issuer: str,
    redirect_uri: str,
    scopes: str,
    code_challenge: str,
) -> str:
    now = utc_now()
    code = new_token(CODE_PREFIX)
    db = get_db()
    db.execute(
        """
        INSERT INTO oauth_codes (
            code_hash, client_id, user_id, resource, issuer, redirect_uri,
            scopes, code_challenge, expires_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            hash_secret(code),
            client_id,
            user_id,
            resource,
            issuer,
            redirect_uri,
            scopes,
            code_challenge,
            stamp(now + timedelta(seconds=CODE_SECONDS)),
            stamp(now),
        ),
    )
    db.commit()
    return code


def exchange_code(
    *,
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
) -> dict | None:
    now = utc_now()
    db = get_db()
    row = db.execute(
        "SELECT * FROM oauth_codes WHERE code_hash = ?",
        (hash_secret(code),),
    ).fetchone()
    dummy = hash_secret("missing-oauth-code")
    hashed_equals(row["code_hash"] if row else dummy, code if row else "x")
    if row is None:
        return None
    if row["consumed_at"]:
        _revoke_family(db, row["grant_family"], stamp(now))
        db.commit()
        return None
    expires = parse_stamp(row["expires_at"])
    if expires is None or now >= expires:
        return None
    if row["client_id"] != client_id or row["redirect_uri"] != redirect_uri:
        return None
    if not bound_to_this_instance(row["issuer"], row["resource"]):
        return None
    if not verify_s256(code_verifier, row["code_challenge"]):
        return None

    family = secrets.token_urlsafe(18)
    access, refresh, access_exp, refresh_exp = _mint_pair(now)
    db.execute(
        """
        INSERT INTO oauth_grants (
            family_id, client_id, user_id, resource, issuer, scopes,
            access_hash, refresh_hash, access_expires_at, refresh_expires_at,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            family,
            row["client_id"],
            row["user_id"],
            row["resource"],
            row["issuer"],
            row["scopes"],
            hash_secret(access),
            hash_secret(refresh),
            stamp(access_exp),
            stamp(refresh_exp),
            stamp(now),
        ),
    )
    db.execute(
        "UPDATE oauth_codes SET consumed_at = ?, grant_family = ? WHERE id = ?",
        (stamp(now), family, row["id"]),
    )
    db.commit()
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": ACCESS_SECONDS,
        "scope": row["scopes"],
        "resource": row["resource"],
    }


def refresh_grant(refresh_token: str, client_id: str) -> dict | None:
    now = utc_now()
    db = get_db()
    digest = hash_secret(refresh_token)
    row = db.execute(
        "SELECT * FROM oauth_grants WHERE refresh_hash = ? OR previous_refresh_hash = ?",
        (digest, digest),
    ).fetchone()
    if row is None:
        return None
    if row["revoked_at"] or row["previous_refresh_hash"] == digest:
        _revoke_family(db, row["family_id"], stamp(now))
        db.commit()
        return None
    if row["client_id"] != client_id:
        return None
    if not bound_to_this_instance(row["issuer"], row["resource"]):
        return None
    refresh_exp = parse_stamp(row["refresh_expires_at"])
    if refresh_exp is None or now >= refresh_exp:
        return None

    access, new_refresh, access_exp, new_refresh_exp = _mint_pair(now)
    db.execute(
        """
        UPDATE oauth_grants
        SET access_hash = ?, refresh_hash = ?, previous_refresh_hash = ?,
            access_expires_at = ?, refresh_expires_at = ?, last_used_at = ?
        WHERE id = ?
        """,
        (
            hash_secret(access),
            hash_secret(new_refresh),
            digest,
            stamp(access_exp),
            stamp(new_refresh_exp),
            stamp(now),
            row["id"],
        ),
    )
    db.commit()
    return {
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": "Bearer",
        "expires_in": ACCESS_SECONDS,
        "scope": row["scopes"],
        "resource": row["resource"],
    }


def authenticate_access(token: str | None) -> dict | None:
    if not token or not isinstance(token, str) or not token.startswith(ACCESS_PREFIX):
        return None
    now = utc_now()
    db = get_db()
    row = db.execute(
        "SELECT * FROM oauth_grants WHERE access_hash = ?",
        (hash_secret(token),),
    ).fetchone()
    if row is None or row["revoked_at"]:
        return None
    if not bound_to_this_instance(row["issuer"], row["resource"]):
        return None
    access_exp = parse_stamp(row["access_expires_at"])
    if access_exp is None or now >= access_exp:
        return None
    from app.reminders.repository import get_person

    if get_person(row["user_id"]) is None:
        return None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "permission": permission_for(row["scopes"]),
        "last_used_at": row["last_used_at"],
        "kind": "oauth",
        "scopes": row["scopes"],
        "client_id": row["client_id"],
        "resource": row["resource"],
        "issuer": row["issuer"],
        "family_id": row["family_id"],
    }


def touch_grant(grant: dict) -> None:
    if grant.get("kind") != "oauth":
        return
    now = utc_now()
    last = parse_stamp(grant.get("last_used_at"))
    if last is not None and (now - last).total_seconds() < 60:
        return
    db = get_db()
    db.execute(
        "UPDATE oauth_grants SET last_used_at = ? WHERE id = ? AND revoked_at IS NULL",
        (stamp(now), grant["id"]),
    )
    db.commit()


def revoke_presented_token(token: str, client_id: str) -> None:
    """RFC 7009: תמיד מצליח כלפי חוץ. טוקן לא מוכר לא מדליף."""
    now = stamp(utc_now())
    db = get_db()
    digest = hash_secret(token)
    row = db.execute(
        "SELECT * FROM oauth_grants WHERE access_hash = ? OR refresh_hash = ?",
        (digest, digest),
    ).fetchone()
    if row is not None and row["client_id"] == client_id:
        _revoke_family(db, row["family_id"], now)
    db.commit()


def revoke_grant_id(grant_id: int) -> bool:
    db = get_db()
    row = db.execute("SELECT family_id FROM oauth_grants WHERE id = ?", (grant_id,)).fetchone()
    if row is None:
        return False
    _revoke_family(db, row["family_id"], stamp(utc_now()))
    db.commit()
    return True


def revoke_client_grants(db, client_id: str, now_stamp: str) -> None:
    db.execute(
        "UPDATE oauth_grants SET revoked_at = ?, access_hash = NULL, refresh_hash = NULL "
        "WHERE client_id = ? AND revoked_at IS NULL",
        (now_stamp, client_id),
    )


def revoke_grants_for_user(db, user_id: int) -> None:
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'oauth_grants'"
    ).fetchone():
        return
    db.execute(
        "UPDATE oauth_grants SET revoked_at = ?, access_hash = NULL, refresh_hash = NULL "
        "WHERE user_id = ? AND revoked_at IS NULL",
        (stamp(utc_now()), user_id),
    )


def list_connections() -> list[dict]:
    db = get_db()
    people = _people_table(db)
    rows = db.execute(
        f"""
        SELECT g.id, g.family_id, g.client_id, g.user_id, g.scopes, g.resource,
               g.issuer, g.created_at, g.last_used_at, g.revoked_at, g.refresh_expires_at,
               c.name AS client_name, p.name AS user_name
        FROM oauth_grants g
        LEFT JOIN oauth_clients c ON c.client_id = g.client_id
        LEFT JOIN {people} p ON p.id = g.user_id
        ORDER BY g.id DESC
        """
    ).fetchall()
    now = utc_now()
    out = []
    for row in rows:
        status = "revoked" if row["revoked_at"] else "active"
        exp = parse_stamp(row["refresh_expires_at"])
        if status == "active" and (exp is None or now >= exp):
            status = "expired"
        out.append(
            {
                "id": row["id"],
                "family_id": row["family_id"],
                "client_id": row["client_id"],
                "client_name": row["client_name"] or row["client_id"],
                "user_id": row["user_id"],
                "user_name": row["user_name"] or "",
                "scopes": row["scopes"],
                "resource": row["resource"],
                "issuer": row["issuer"],
                "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
                "refresh_expires_at": row["refresh_expires_at"],
                "status": status,
            }
        )
    return out


def _people_table(db) -> str:
    from app.users.table import quote_people_table, resolve_people_table

    return quote_people_table(resolve_people_table(db))


def _mint_pair(now):
    access = new_token(ACCESS_PREFIX)
    refresh = new_token(REFRESH_PREFIX)
    return (
        access,
        refresh,
        now + timedelta(seconds=ACCESS_SECONDS),
        now + timedelta(days=REFRESH_DAYS),
    )


def _revoke_family(db, family_id: str | None, now_stamp: str) -> None:
    if not family_id:
        return
    db.execute(
        "UPDATE oauth_grants SET revoked_at = ?, access_hash = NULL, refresh_hash = NULL "
        "WHERE family_id = ? AND revoked_at IS NULL",
        (now_stamp, family_id),
    )
