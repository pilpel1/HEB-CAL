"""זרימת OAuth מקומית: JWT, PKCE, scopes, refresh, CSRF, דחיות."""
from __future__ import annotations

from datetime import timedelta

import pytest

from mcp_support import add_user, legacy, post
from oauth_flow_support import (
    AUD,
    EMAIL,
    ISSUER,
    REDIRECT,
    access_jwt_token,
    authorize_url,
    complete_code_flow,
    configure_access,
    jwt_headers,
    make_client,
    pkce_pair,
    rsa_pair,
)


@pytest.fixture(scope="module")
def keys():
    return rsa_pair()


@pytest.fixture
def access_env(monkeypatch, keys):
    configure_access(monkeypatch, keys[1])
    return keys


def test_settings_oauth_card_and_no_gemini_deep_link(client):
    html = client.get("/settings").get_data(as_text=True)
    assert 'data-settings-section="settings-oauth"' in html
    assert "חיבור עם אישור גישה" in html
    assert "אין כפתור חיבור רשמי" in html
    assert "gemini.google.com" in html
    assert "לא נבדק עדיין מול Gemini" in html
    assert "עדיין לא מאומתת" not in html
    assert "גישה קצרה" not in html
    assert "בלי להעתיק מפתח" not in html
    assert "פנו למנהל הלוח" in html
    assert "HEB_CAL_PUBLIC_ORIGIN" not in html
    assert "Cloudflare Access" not in html
    assert "deep link" not in html
    assert "cursor://gemini" not in html
    assert "oauth-settings.js" in client.get("/").get_data(as_text=True)


def test_get_authorize_does_not_grant(app, client, access_env):
    add_user(app, "אביחי", EMAIL)
    client_id, _secret, _row = make_client(app)
    _verifier, challenge = pkce_pair()
    shown = client.get(
        authorize_url(client_id, challenge),
        headers=jwt_headers(access_jwt_token(access_env[0])),
    )
    assert shown.status_code == 200
    html = shown.get_data(as_text=True)
    assert "לאשר גישה ללוח" in html
    assert "hebcal.corcos.app" in html
    assert "code=" not in html
    assert shown.headers["Cache-Control"] == "no-store"


def test_consent_csrf_and_deny(app, client, access_env):
    add_user(app, "אביחי", EMAIL)
    client_id, secret, _row = make_client(app)
    verifier, challenge = pkce_pair()
    headers = jwt_headers(access_jwt_token(access_env[0]))
    url = authorize_url(client_id, challenge)
    shown = client.get(url, headers=headers)
    csrf = shown.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    bad = client.post(url, headers=headers, data={"csrf_token": "nope", "decision": "allow"})
    assert bad.status_code == 403
    denied = client.post(url, headers=headers, data={"csrf_token": csrf, "decision": "deny"})
    assert denied.status_code == 302
    assert "error=access_denied" in denied.headers["Location"]
    assert "code=" not in denied.headers["Location"]


def test_unknown_user_and_bad_jwt_fail_closed(app, client, access_env):
    add_user(app, "אביחי", "other@example.com")
    client_id, _secret, _row = make_client(app)
    _verifier, challenge = pkce_pair()
    url = authorize_url(client_id, challenge)
    unknown = client.get(url, headers=jwt_headers(access_jwt_token(access_env[0], EMAIL)))
    assert unknown.status_code == 403
    assert "code=" not in unknown.get_data(as_text=True)
    email_header_only = client.get(
        url,
        headers={"Cf-Access-Authenticated-User-Email": EMAIL},
    )
    assert email_header_only.status_code == 403
    expired = client.get(
        url,
        headers=jwt_headers(access_jwt_token(access_env[0], "other@example.com", exp_offset=-120)),
    )
    assert expired.status_code == 403
    wrong_aud = client.get(
        url,
        headers=jwt_headers(access_jwt_token(access_env[0], "other@example.com", aud="other")),
    )
    assert wrong_aud.status_code == 403


def test_unconfigured_access_fails_closed(app, client, monkeypatch, keys):
    configure_access(monkeypatch, keys[1])
    monkeypatch.delenv("CF_ACCESS_ISSUER", raising=False)
    monkeypatch.delenv("HEB_CAL_ACCESS_ISSUER", raising=False)
    add_user(app, "אביחי", EMAIL)
    client_id, _secret, _row = make_client(app)
    _verifier, challenge = pkce_pair()
    response = client.get(
        authorize_url(client_id, challenge),
        headers=jwt_headers(access_jwt_token(keys[0])),
    )
    assert response.status_code == 403


def test_redirect_and_client_validation(app, client, access_env):
    add_user(app, "אביחי", EMAIL)
    client_id, _secret, _row = make_client(app)
    _verifier, challenge = pkce_pair()
    headers = jwt_headers(access_jwt_token(access_env[0]))
    from urllib.parse import urlencode

    evil = client.get(
        "/oauth/authorize?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "https://evil.example/steal",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": "https://hebcal.corcos.app/mcp",
                "scope": "hebcal:read",
            }
        ),
        headers=headers,
    )
    assert evil.status_code == 400
    assert "evil.example" not in (evil.headers.get("Location") or "")
    unknown_client = client.get(
        authorize_url("hcc_nope", challenge),
        headers=headers,
    )
    assert unknown_client.status_code == 400


def test_full_read_write_and_scope_denial(app, client, access_env):
    add_user(app, "אביחי", EMAIL)
    tokens, _cid, _sec = complete_code_flow(client, app, access_env[0], scope="hebcal:write")
    access = tokens["access_token"]
    assert access.startswith("hcoa_")
    listed = legacy(client, access, "tools/list")
    assert listed.status_code == 200
    names = {tool["name"] for tool in listed.get_json()["result"]["tools"]}
    assert "create_event" in names
    created = legacy(
        client, access, "tools/call",
        {"name": "create_event", "arguments": {"title": "OAuth", "date": "2026-12-01"}},
    )
    assert created.get_json()["result"]["isError"] is False

    read_tokens, _cid2, _sec2 = complete_code_flow(client, app, access_env[0], scope="hebcal:read")
    read_list = legacy(client, read_tokens["access_token"], "tools/list")
    read_names = {tool["name"] for tool in read_list.get_json()["result"]["tools"]}
    assert "create_event" not in read_names
    blocked = legacy(
        client, read_tokens["access_token"], "tools/call",
        {"name": "create_event", "arguments": {"title": "No", "date": "2026-12-02"}},
    )
    assert blocked.get_json()["result"]["isError"] is True
    assert blocked.get_json()["result"]["structuredContent"]["error"]["code"] == "forbidden"


def test_code_reuse_refresh_rotation_replay_revoke_expiry(app, client, access_env, monkeypatch):
    add_user(app, "אביחי", EMAIL)
    client_id, secret, _row = make_client(app)
    verifier, challenge = pkce_pair()
    headers = jwt_headers(access_jwt_token(access_env[0]))
    url = authorize_url(client_id, challenge, scope="hebcal:read")
    shown = client.get(url, headers=headers)
    csrf = shown.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    allowed = client.post(url, headers=headers, data={"csrf_token": csrf, "decision": "allow"})
    from urllib.parse import parse_qs, urlsplit

    code = parse_qs(urlsplit(allowed.headers["Location"]).query)["code"][0]
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT,
        "client_id": client_id,
        "client_secret": secret,
        "code_verifier": verifier,
    }
    first = client.post("/oauth/token", data=body)
    assert first.status_code == 200
    reuse = client.post("/oauth/token", data=body)
    assert reuse.status_code == 400
    assert reuse.get_json()["error"] == "invalid_grant"
    ping = post(client, first.get_json()["access_token"], {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert ping.status_code == 401

    tokens, cid, sec = complete_code_flow(client, app, access_env[0], scope="hebcal:read")
    refreshed = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": cid,
            "client_secret": sec,
        },
    )
    assert refreshed.status_code == 200
    new_refresh = refreshed.get_json()["refresh_token"]
    assert new_refresh != tokens["refresh_token"]
    ping2 = post(client, refreshed.get_json()["access_token"], {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert ping2.status_code == 200
    replay = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": cid,
            "client_secret": sec,
        },
    )
    assert replay.status_code == 400
    assert post(client, refreshed.get_json()["access_token"], {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401

    tokens3, cid3, sec3 = complete_code_flow(client, app, access_env[0], scope="hebcal:read")
    revoked = client.post(
        "/oauth/revoke",
        data={"token": tokens3["refresh_token"], "client_id": cid3, "client_secret": sec3},
    )
    assert revoked.status_code == 200
    after = post(client, tokens3["access_token"], {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert after.status_code == 401

    tokens2, cid2, sec2 = complete_code_flow(client, app, access_env[0], scope="hebcal:read")
    clock = {"now": __import__("app.oauth.time", fromlist=["utc_now"]).utc_now()}
    monkeypatch.setattr("app.oauth.tokens.utc_now", lambda: clock["now"])
    clock["now"] = clock["now"] + timedelta(minutes=16)
    expired = post(client, tokens2["access_token"], {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert expired.status_code == 401
    still = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens2["refresh_token"],
            "client_id": cid2,
            "client_secret": sec2,
        },
    )
    assert still.status_code == 200
    clock["now"] = clock["now"] + timedelta(days=31)
    idle = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": still.get_json()["refresh_token"],
            "client_id": cid2,
            "client_secret": sec2,
        },
    )
    assert idle.status_code == 400


def test_hcal_key_unchanged_beside_oauth(app, client, access_env):
    from mcp_support import make_key

    user = add_user(app, "אביחי", EMAIL)
    key = make_key(app, user, "write")
    assert post(client, key, {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 200
    complete_code_flow(client, app, access_env[0])
    assert post(client, key, {"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 200


def test_admin_csrf_and_connection_list(app, client, access_env):
    add_user(app, "אביחי", EMAIL)
    tokens, _cid, _sec = complete_code_flow(client, app, access_env[0])
    listing = client.get("/api/oauth/overview")
    assert listing.status_code == 200
    body = listing.get_json()
    assert body["connections"]
    assert tokens["access_token"] not in listing.get_data(as_text=True)
    assert tokens["refresh_token"] not in listing.get_data(as_text=True)
    grant_id = body["connections"][0]["id"]
    blocked = client.delete(f"/api/oauth/connections/{grant_id}")
    assert blocked.status_code == 403
    csrf = body["csrf_token"]
    ok = client.delete(f"/api/oauth/connections/{grant_id}", headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200
    ping = post(client, tokens["access_token"], {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert ping.status_code == 401


def test_no_open_dcr(client, access_env):
    assert client.post("/oauth/register", json={"redirect_uris": ["https://x.example/cb"]}).status_code == 404
    meta = client.get("/.well-known/oauth-authorization-server").get_json()
    assert "registration_endpoint" not in meta
    assert "none" not in meta["token_endpoint_auth_methods_supported"]


def test_consent_post_requires_jwt_and_blocks_scope_escalation(app, client, access_env):
    add_user(app, "אביחי", EMAIL)
    client_id, secret, _row = make_client(app)
    verifier, challenge = pkce_pair()
    headers = jwt_headers(access_jwt_token(access_env[0]))
    read_url = authorize_url(client_id, challenge, scope="hebcal:read")
    shown = client.get(read_url, headers=headers)
    csrf = shown.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    no_jwt = client.post(read_url, data={"csrf_token": csrf, "decision": "allow"})
    assert no_jwt.status_code == 403
    assert "code=" not in (no_jwt.headers.get("Location") or "")
    write_url = authorize_url(client_id, challenge, scope="hebcal:write")
    escalated = client.post(write_url, headers=headers, data={"csrf_token": csrf, "decision": "allow"})
    assert escalated.status_code == 403
    assert "code=" not in (escalated.headers.get("Location") or "")


def test_confidential_client_requires_secret_and_resource_binding(app, client, access_env):
    add_user(app, "אביחי", EMAIL)
    tokens, cid, sec = complete_code_flow(client, app, access_env[0], scope="hebcal:read")
    missing = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": cid,
        },
    )
    assert missing.status_code == 401
    wrong_resource = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "client_id": cid,
            "client_secret": sec,
            "resource": "https://naom-naama.corcos.app/mcp",
        },
    )
    assert wrong_resource.status_code == 400
    ping = post(client, tokens["access_token"], {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert ping.status_code == 200


def test_initialize_and_tools_list_follow_oauth_scope(app, client, access_env):
    add_user(app, "אביחי", EMAIL)
    read_tokens, _cid, _sec = complete_code_flow(client, app, access_env[0], scope="hebcal:read")
    init = post(
        client,
        read_tokens["access_token"],
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
    )
    assert init.status_code == 200
    listed = legacy(client, read_tokens["access_token"], "tools/list")
    names = {tool["name"] for tool in listed.get_json()["result"]["tools"]}
    assert "list_events" in names
    assert "create_event" not in names


def test_inline_jwks_ignored_outside_tests(app, client, monkeypatch, keys):
    configure_access(monkeypatch, keys[1])
    monkeypatch.setitem(app.config, "TESTING", False)
    add_user(app, "אביחי", EMAIL)
    client_id, _secret, _row = make_client(app)
    _verifier, challenge = pkce_pair()
    response = client.get(
        authorize_url(client_id, challenge),
        headers=jwt_headers(access_jwt_token(keys[0])),
    )
    assert response.status_code == 403
