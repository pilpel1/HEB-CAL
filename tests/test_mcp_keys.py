"""מפתחות MCP: hash בלבד, הצגה חד-פעמית, הרשאות, ביטול, תפוגה מתגלגלת."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest

from mcp_support import add_user, key_row, legacy, make_key

T0 = datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    state = {"now": T0}
    monkeypatch.setattr("app.mcp.keys.utc_now", lambda: state["now"])
    return state


def _csrf(client) -> str:
    return client.get("/api/mcp-keys").get_json()["csrf_token"]


def _create(client, **payload):
    token = _csrf(client)
    return client.post("/api/mcp-keys", json=payload, headers={"X-CSRF-Token": token})


def _list_ok(client, token):
    return legacy(client, token, "tools/list").status_code == 200


def test_token_is_high_entropy_and_only_hash_is_stored(app, client):
    user = add_user(app)
    response = _create(client, user_id=user, label="לפטופ")
    assert response.status_code == 201
    body = response.get_json()
    token = body["token"]
    prefix, public, secret = token.split("_", 2)
    assert prefix == "hcal" and len(public) == 8 and len(secret) == 43
    assert body["key"]["prefix"] == f"hcal_{public}"
    assert body["key"]["permission"] == "read"

    rows = key_row(app)
    assert len(rows) == 1
    row = rows[0]
    assert row["secret_hash"] == hashlib.sha256(token.encode()).hexdigest()
    for value in row.values():
        assert token not in str(value)
        assert secret not in str(value)


def test_create_response_is_no_store_and_list_never_returns_secret(app, client):
    user = add_user(app)
    response = _create(client, user_id=user, label="Cursor", permission="write")
    assert response.headers["Cache-Control"] == "no-store"
    token = response.get_json()["token"]
    stored_hash = key_row(app)[0]["secret_hash"]

    listing = client.get("/api/mcp-keys")
    assert listing.headers["Cache-Control"] == "no-store"
    text = listing.get_data(as_text=True)
    assert token not in text
    assert token.split("_", 2)[2] not in text
    assert stored_hash not in text
    assert "secret_hash" not in text
    keys = listing.get_json()["keys"]
    assert keys[0]["permission"] == "write"
    assert set(keys[0]) == {
        "id", "user_id", "user_name", "label", "prefix", "permission", "created_at",
        "last_used_at", "expires_at", "absolute_expires_at", "effective_expires_at",
        "revoked_at", "status",
    }
    assert keys[0]["effective_expires_at"] == keys[0]["expires_at"]

    revoke_token = _csrf(client)
    revoked = client.delete(f"/api/mcp-keys/{keys[0]['id']}", headers={"X-CSRF-Token": revoke_token})
    assert token not in revoked.get_data(as_text=True)
    assert stored_hash not in revoked.get_data(as_text=True)


def test_management_requires_csrf(app, client):
    user = add_user(app)
    assert client.post("/api/mcp-keys", json={"user_id": user, "label": "x"}).status_code == 403
    assert key_row(app) == []
    token = make_key(app, user)
    key_id = key_row(app)[0]["id"]
    assert client.delete(f"/api/mcp-keys/{key_id}").status_code == 403
    assert client.delete(f"/api/mcp-keys/{key_id}", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert _list_ok(client, token)


@pytest.mark.parametrize(
    "with_user, payload, message",
    [
        (False, {"label": "x"}, "בחרו משתמש"),
        (False, {"user_id": 999999, "label": "x"}, "המשתמש לא נמצא"),
        (True, {"label": "   "}, "צריך שם"),
        (True, {"label": "x" * 61}, "ארוך מדי"),
        (True, {"label": "x", "permission": "admin"}, "הרשאה לא תקינה"),
        (True, {"label": "x", "absolute_expires_on": "2020-01-01"}, "כבר עבר"),
        (True, {"label": "x", "absolute_expires_on": "31/12/2030"}, "לא תקין"),
    ],
)
def test_create_validation(app, client, with_user, payload, message):
    user = add_user(app)
    payload = dict(payload)
    if with_user:
        payload["user_id"] = user
    response = _create(client, **payload)
    assert response.status_code == 400
    assert message in response.get_json()["error"]
    assert key_row(app) == []


def test_cap_ten_active_keys_per_user(app, client):
    user = add_user(app)
    other = add_user(app, "שירה")
    for index in range(10):
        make_key(app, user, label=f"מכשיר {index}")
    response = _create(client, user_id=user, label="אחד עשר")
    assert response.status_code == 400
    assert "10" in response.get_json()["error"]
    assert _create(client, user_id=other, label="של שירה").status_code == 201

    first_id = key_row(app)[0]["id"]
    client.delete(f"/api/mcp-keys/{first_id}", headers={"X-CSRF-Token": _csrf(client)})
    assert _create(client, user_id=user, label="אחרי ביטול").status_code == 201


def test_revoked_key_gets_401(app, client):
    user = add_user(app)
    token = make_key(app, user)
    assert _list_ok(client, token)
    key_id = key_row(app)[0]["id"]
    response = client.delete(f"/api/mcp-keys/{key_id}", headers={"X-CSRF-Token": _csrf(client)})
    assert response.status_code == 200
    assert response.get_json()["key"]["status"] == "revoked"
    assert legacy(client, token, "tools/list").status_code == 401
    assert client.delete("/api/mcp-keys/999999", headers={"X-CSRF-Token": _csrf(client)}).status_code == 404


def test_deleting_user_revokes_their_keys(app, client):
    user = add_user(app)
    other = add_user(app, "שירה")
    token = make_key(app, user)
    other_token = make_key(app, other)
    assert client.delete(f"/api/users/{user}").status_code == 200
    assert legacy(client, token, "tools/list").status_code == 401
    assert _list_ok(client, other_token)
    rows = {row["user_id"]: row for row in key_row(app)}
    assert rows[user]["revoked_at"]
    assert rows[other]["revoked_at"] is None


def test_key_without_user_row_is_rejected(app, client):
    user = add_user(app)
    token = make_key(app, user)
    with app.app_context():
        from app.database import get_db

        db = get_db()
        db.execute("DELETE FROM users WHERE id = ?", (user,))
        db.commit()
    assert legacy(client, token, "tools/list").status_code == 401


def test_sliding_expiry_refreshes_on_tools_list_and_initialize(app, client, clock):
    user = add_user(app)
    token = make_key(app, user)
    assert key_row(app)[0]["expires_at"] == "2026-12-05T12:00:00Z"

    clock["now"] = T0 + timedelta(days=29)
    assert _list_ok(client, token)
    row = key_row(app)[0]
    assert row["last_used_at"] == "2026-12-04T12:00:00Z"
    assert row["expires_at"] == "2027-01-03T12:00:00Z"

    clock["now"] = T0 + timedelta(days=58)
    init = legacy(
        client, token, "initialize",
        {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
        version=None,
    )
    assert init.status_code == 200
    assert key_row(app)[0]["expires_at"] == "2027-02-01T12:00:00Z"

    clock["now"] = T0 + timedelta(days=58 + 30)
    assert legacy(client, token, "tools/list").status_code == 401
    listing = client.get("/api/mcp-keys").get_json()["keys"]
    assert listing[0]["status"] == "expired"


def test_unused_key_expires_after_thirty_days(app, client, clock):
    user = add_user(app)
    token = make_key(app, user)
    clock["now"] = T0 + timedelta(days=30) - timedelta(seconds=1)
    assert _list_ok(client, token)
    fresh = make_key(app, user, label="שני")
    clock["now"] = clock["now"] + timedelta(days=30, seconds=1)
    assert legacy(client, fresh, "tools/list").status_code == 401


def test_invalid_key_does_not_extend_expiry(app, client, clock):
    user = add_user(app)
    token = make_key(app, user)
    before = key_row(app)[0]
    prefix = token.rsplit("_", 1)[0]
    wrong = prefix + "_" + ("A" * 43)
    clock["now"] = T0 + timedelta(days=10)
    for bad in (wrong, token + "x", token[:-1], prefix, "", "hcal_zzzzzzzz_" + "A" * 43):
        response = legacy(client, bad, "tools/list")
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"].startswith("Bearer")
    assert key_row(app)[0] == before


def test_protocol_error_does_not_extend_expiry(app, client, clock):
    user = add_user(app)
    token = make_key(app, user)
    before = key_row(app)[0]
    clock["now"] = T0 + timedelta(days=10)
    assert legacy(client, token, "tools/list", version="1999-01-01").status_code == 400
    assert legacy(client, token, "no/such").get_json()["error"]["code"] == -32601
    assert key_row(app)[0] == before


def test_touch_is_throttled_but_never_late(app, client, clock):
    user = add_user(app)
    token = make_key(app, user)
    clock["now"] = T0 + timedelta(days=1)
    assert _list_ok(client, token)
    first = key_row(app)[0]
    clock["now"] = T0 + timedelta(days=1, seconds=30)
    assert _list_ok(client, token)
    assert key_row(app)[0] == first
    clock["now"] = T0 + timedelta(days=1, seconds=61)
    assert _list_ok(client, token)
    assert key_row(app)[0]["last_used_at"] == "2026-11-06T12:01:01Z"


def test_absolute_expiry_wins_over_activity(app, client, clock):
    user = add_user(app)
    token = make_key(app, user, absolute="2026-11-10")
    row = key_row(app)[0]
    assert row["absolute_expires_at"] == "2026-11-10T22:00:00Z"
    listed = client.get("/api/mcp-keys").get_json()["keys"][0]
    assert listed["expires_at"] == row["expires_at"]
    assert listed["expires_at"] > listed["absolute_expires_at"]
    assert listed["effective_expires_at"] == listed["absolute_expires_at"]
    clock["now"] = T0 + timedelta(days=5, hours=9)
    assert _list_ok(client, token)
    after_use = client.get("/api/mcp-keys").get_json()["keys"][0]
    assert after_use["expires_at"] > after_use["absolute_expires_at"]
    assert after_use["effective_expires_at"] == after_use["absolute_expires_at"]
    clock["now"] = T0 + timedelta(days=5, hours=10)
    assert legacy(client, token, "tools/list").status_code == 401


def test_forged_access_header_does_not_choose_the_key_owner(app, client):
    """כותרת Cf-Access רק ממלאת ברירת מחדל ב-GET. היא לא בוחרת את בעל המפתח."""
    shira = add_user(app, "שירה", google_email="shira@example.com")
    avichay = add_user(app, "אביחי", google_email="avichay@example.com")
    forged = {"Cf-Access-Authenticated-User-Email": "shira@example.com"}
    csrf = client.get("/api/mcp-keys", headers=forged).get_json()["csrf_token"]
    missing = client.post(
        "/api/mcp-keys",
        json={"label": "בלי בחירה"},
        headers={**forged, "X-CSRF-Token": csrf},
    )
    assert missing.status_code == 400
    assert "בחרו משתמש" in missing.get_json()["error"]
    assert key_row(app) == []

    created = client.post(
        "/api/mcp-keys",
        json={"user_id": avichay, "label": "מפורש"},
        headers={**forged, "X-CSRF-Token": csrf},
    )
    assert created.status_code == 201
    body = created.get_json()
    assert body["key"]["user_id"] == avichay
    assert body["key"]["user_id"] != shira
    assert "secret_hash" not in body["key"]
    assert key_row(app)[0]["user_id"] == avichay

    listing = client.get(
        "/api/mcp-keys",
        headers={"Cf-Access-Authenticated-User-Email": "avichay@example.com"},
    ).get_json()
    assert listing["default_user_id"] == avichay
    assert [row["user_id"] for row in listing["keys"]] == [avichay]


def test_default_owner_from_access_email(app, client):
    add_user(app, "שירה")
    owner = add_user(app, "אביחי", google_email="avichay@example.com")
    plain = client.get("/api/mcp-keys").get_json()
    assert plain["default_user_id"] is None
    assert {user["name"] for user in plain["users"]} == {"שירה", "אביחי"}
    mapped = client.get(
        "/api/mcp-keys",
        headers={"Cf-Access-Authenticated-User-Email": "Avichay@Example.com"},
    ).get_json()
    assert mapped["default_user_id"] == owner


def test_token_never_logged(app, client, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    user = add_user(app)
    response = _create(client, user_id=user, label="x", permission="write")
    token = response.get_json()["token"]
    legacy(client, token, "tools/list")
    legacy(client, token, "tools/call", {"name": "list_events", "arguments": {"from": "2026-11-01", "to": "2026-11-30"}})
    legacy(client, token + "bad", "tools/list")
    captured = capsys.readouterr()
    secret = token.split("_", 2)[2]
    for text in (caplog.text, captured.out, captured.err):
        assert secret not in text
    stored_hash = key_row(app)[0]["secret_hash"]
    assert stored_hash not in caplog.text


def test_mcp_key_does_not_unlock_management_routes(app, client):
    user = add_user(app)
    token = make_key(app, user)
    response = client.post(
        "/api/mcp-keys",
        data=json.dumps({"user_id": user, "label": "x"}),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    assert response.status_code == 403
    assert len(key_row(app)) == 1
