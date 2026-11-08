"""בידוד מופעים: טוקן/קוד של hebcal נדחים ב-naom גם עם אותו אימייל."""
from __future__ import annotations

import os

import pytest

from app.database import init_db
from mcp_support import add_user, post
from oauth_flow_support import complete_code_flow, configure_access, rsa_pair

HEBCAL = "https://hebcal.corcos.app"
NAOM = "https://naom-naama.corcos.app"
EMAIL = "avichay@example.com"


@pytest.fixture(scope="module")
def keys():
    return rsa_pair()


def _close_db():
    from flask import g

    db = g.pop("db", None)
    if db is not None:
        db.close()


def test_token_from_hebcal_rejected_on_naom_db(app, client, monkeypatch, tmp_path, keys):
    original_db = os.environ["DATABASE_PATH"]
    naom_db = str(tmp_path / "naom.sqlite")
    configure_access(monkeypatch, keys[1], origin=HEBCAL)
    add_user(app, "אביחי", EMAIL)
    tokens, _cid, _sec = complete_code_flow(client, app, keys[0])
    access = tokens["access_token"]
    assert post(client, access, {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 200

    monkeypatch.setenv("DATABASE_PATH", naom_db)
    monkeypatch.setenv("HEB_CAL_PUBLIC_ORIGIN", NAOM)
    with app.app_context():
        _close_db()
        init_db()
    add_user(app, "אביחי", EMAIL)
    denied = post(client, access, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert denied.status_code == 401
    assert denied.get_json()["error"] == "invalid_token"
    assert access not in denied.get_data(as_text=True)

    monkeypatch.setenv("DATABASE_PATH", original_db)
    monkeypatch.setenv("HEB_CAL_PUBLIC_ORIGIN", HEBCAL)
    with app.app_context():
        _close_db()
    still = post(client, access, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert still.status_code == 200


def test_same_hashes_wrong_issuer_rejected(app, client, monkeypatch, keys):
    """גם אם השורה קיימת במסד, issuer/resource של מופע אחר נדחים."""
    from app.database import get_db
    from app.oauth.crypto import hash_secret
    from app.oauth.time import stamp, utc_now

    configure_access(monkeypatch, keys[1], origin=HEBCAL)
    user = add_user(app, "אביחי", EMAIL)
    raw = "hcoa_" + "B" * 43
    now = utc_now()
    from datetime import timedelta

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO oauth_grants (
                family_id, client_id, user_id, resource, issuer, scopes,
                access_hash, refresh_hash, access_expires_at, refresh_expires_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "fam-x",
                "hcc_other",
                user,
                f"{NAOM}/mcp",
                NAOM,
                "hebcal:read",
                hash_secret(raw),
                hash_secret("hcor_" + "C" * 43),
                stamp(now + timedelta(minutes=10)),
                stamp(now + timedelta(days=10)),
                stamp(now),
            ),
        )
        db.commit()
    denied = post(client, raw, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert denied.status_code == 401
    monkeypatch.setenv("HEB_CAL_PUBLIC_ORIGIN", NAOM)
    # same DB, other origin — still not a live naom instance, but binding matches
    # Wait: if we switch origin to NAOM on the SAME db, the planted row WOULD match.
    # Cross-board denial is: hebcal origin must reject naom-bound grant (already asserted).
    # Inverse: plant hebcal grant, set origin to NAOM.
    monkeypatch.setenv("HEB_CAL_PUBLIC_ORIGIN", HEBCAL)
    tokens, _cid, _sec = complete_code_flow(client, app, keys[0])
    monkeypatch.setenv("HEB_CAL_PUBLIC_ORIGIN", NAOM)
    flipped = post(client, tokens["access_token"], {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert flipped.status_code == 401
