"""שלב א': גילוי RFC 9728 ואתגר 401. בלי שרת הרשאות ובלי בידוד טוקנים."""
from __future__ import annotations

import json

from app.oauth.origin import public_origin
from app.oauth.resource import (
    METADATA_MCP_PATH,
    METADATA_PATH,
    SCOPES,
    mcp_resource_metadata_url,
    mcp_resource_url,
    mcp_www_authenticate,
    protected_resource_metadata,
)
from mcp_support import add_user, make_key, post

HEBCAL = "https://hebcal.corcos.app"
NAOM = "https://naom-naama.corcos.app"
SPOOF = {
    "Host": "evil.example:4443",
    "X-Forwarded-Host": "naom-naama.corcos.app",
    "X-Forwarded-Proto": "https",
    "X-Forwarded-For": "203.0.113.9",
    "Forwarded": "for=203.0.113.9;host=attacker.test;proto=https",
}


def _set_origin(monkeypatch, value: str | None) -> None:
    if value is None:
        monkeypatch.delenv("HEB_CAL_PUBLIC_ORIGIN", raising=False)
    else:
        monkeypatch.setenv("HEB_CAL_PUBLIC_ORIGIN", value)


def test_public_origin_accepts_https_and_loopback_http_only(monkeypatch):
    cases = {
        "https://hebcal.corcos.app": HEBCAL,
        "https://hebcal.corcos.app/": HEBCAL,
        "HTTPS://Hebcal.Corcos.App": HEBCAL,
        "https://hebcal.corcos.app:443": HEBCAL,
        "https://naom-naama.corcos.app": NAOM,
        "http://127.0.0.1:5000": "http://127.0.0.1:5000",
        "http://localhost": "http://localhost",
        "http://[::1]:5000": "http://[::1]:5000",
        "https://hebcal.corcos.app:8443": "https://hebcal.corcos.app:8443",
    }
    for raw, expected in cases.items():
        _set_origin(monkeypatch, raw)
        assert public_origin() == expected, raw

    rejected = (
        None,
        "",
        "   ",
        "http://hebcal.corcos.app",
        "https://hebcal.corcos.app/mcp",
        "https://user:pass@hebcal.corcos.app",
        "https://hebcal.corcos.app?x=1",
        "https://hebcal.corcos.app#frag",
        "//hebcal.corcos.app",
        "javascript:alert(1)",
        "ftp://hebcal.corcos.app",
        "https://hebcal.corcos.app:99999",
    )
    for raw in rejected:
        _set_origin(monkeypatch, raw)
        assert public_origin() is None, raw


def test_metadata_isolation_is_not_token_isolation(monkeypatch):
    """שני מקורות → שני מזהי משאב. אין כאן טוקנים — בידוד מענקים הוא שלב הבא."""
    _set_origin(monkeypatch, HEBCAL)
    heb = protected_resource_metadata()
    _set_origin(monkeypatch, NAOM)
    naom = protected_resource_metadata()
    assert heb["resource"] == mcp_resource_url(HEBCAL)
    assert naom["resource"] == mcp_resource_url(NAOM)
    assert heb["resource"] != naom["resource"]
    assert heb["authorization_servers"] == [HEBCAL]
    assert naom["authorization_servers"] == [NAOM]
    assert heb["scopes_supported"] == list(SCOPES)
    assert heb["bearer_methods_supported"] == ["header"]


def test_well_known_is_dark_without_public_origin(client, monkeypatch):
    for value in (None, "", "http://hebcal.corcos.app", "https://hebcal.corcos.app/mcp"):
        _set_origin(monkeypatch, value)
        for path in (METADATA_PATH, METADATA_MCP_PATH):
            assert client.get(path).status_code == 404
            assert client.get(path, headers=SPOOF).status_code == 404


def test_well_known_uses_configured_origin_not_forwarded_headers(client, monkeypatch):
    _set_origin(monkeypatch, HEBCAL)
    for path in (METADATA_PATH, METADATA_MCP_PATH):
        response = client.get(path, headers=SPOOF)
        assert response.status_code == 200
        assert response.mimetype == "application/json"
        assert response.headers["Cache-Control"] == "public, max-age=300"
        body = response.get_json()
        assert body["resource"] == "https://hebcal.corcos.app/mcp"
        assert "evil.example" not in json.dumps(body)
        assert "naom-naama" not in json.dumps(body)
        assert "attacker.test" not in json.dumps(body)
        assert body["authorization_servers"] == [HEBCAL]
        assert "registration_endpoint" not in body
        assert body["scopes_supported"] == ["hebcal:read", "hebcal:write"]

    root = client.get(METADATA_PATH).get_json()
    path = client.get(METADATA_MCP_PATH).get_json()
    assert root == path


def test_distinct_household_origins_advertise_distinct_resources(client, monkeypatch):
    seen = {}
    for origin in (HEBCAL, NAOM):
        _set_origin(monkeypatch, origin)
        body = client.get(METADATA_MCP_PATH, headers={"Host": "localhost"}).get_json()
        seen[origin] = body["resource"]
        challenge = mcp_www_authenticate()
        assert mcp_resource_metadata_url(origin) in challenge
        assert origin in challenge
    assert seen[HEBCAL] == "https://hebcal.corcos.app/mcp"
    assert seen[NAOM] == "https://naom-naama.corcos.app/mcp"
    assert seen[HEBCAL] != seen[NAOM]


def test_malformed_public_origin_does_not_500(client, monkeypatch):
    payload = {"error": "invalid_token", "error_description": "מפתח חסר, לא תקף, בוטל או פג תוקף"}
    for raw in ("https://[broken", "https://[", "http://[", "https://hebcal.corcos.app:notaport"):
        _set_origin(monkeypatch, raw)
        assert public_origin() is None
        meta = client.get(METADATA_PATH)
        assert meta.status_code == 404
        assert raw not in meta.get_data(as_text=True)
        denied = post(client, None, None, raw=b"{")
        assert denied.status_code == 401
        assert denied.get_json() == payload
        assert "resource_metadata" not in denied.headers["WWW-Authenticate"]
        assert raw not in denied.get_data(as_text=True)
        assert "HEB_CAL_PUBLIC_ORIGIN" not in denied.get_data(as_text=True)


def test_authorization_server_metadata_is_truthful_when_origin_set(client, monkeypatch):
    _set_origin(monkeypatch, HEBCAL)
    body = client.get("/.well-known/oauth-authorization-server", headers=SPOOF).get_json()
    assert body["issuer"] == HEBCAL
    assert body["authorization_endpoint"] == f"{HEBCAL}/oauth/authorize"
    assert body["token_endpoint"] == f"{HEBCAL}/oauth/token"
    assert body["revocation_endpoint"] == f"{HEBCAL}/oauth/revoke"
    assert "code" in body["response_types_supported"]
    assert body["code_challenge_methods_supported"] == ["S256"]
    assert "registration_endpoint" not in body
    assert "evil.example" not in json.dumps(body)
    _set_origin(monkeypatch, None)
    assert client.get("/.well-known/oauth-authorization-server").status_code == 404
    assert client.get("/oauth/register").status_code == 404
    assert client.post("/oauth/register", json={}).status_code == 404


def test_mcp_401_json_unchanged_and_resource_metadata_only_when_configured(client, monkeypatch):
    payload = {"error": "invalid_token", "error_description": "מפתח חסר, לא תקף, בוטל או פג תוקף"}
    _set_origin(monkeypatch, None)
    dark = post(client, None, None, raw=b"{")
    assert dark.status_code == 401
    assert dark.get_json() == payload
    assert dark.headers["WWW-Authenticate"] == 'Bearer realm="heb-cal", error="invalid_token"'
    assert "resource_metadata" not in dark.headers["WWW-Authenticate"]

    _set_origin(monkeypatch, HEBCAL)
    challenged = post(client, None, None, raw=b"{", headers=SPOOF)
    assert challenged.status_code == 401
    assert challenged.get_json() == payload
    header = challenged.headers["WWW-Authenticate"]
    assert header.startswith('Bearer realm="heb-cal", error="invalid_token"')
    assert (
        'resource_metadata="https://hebcal.corcos.app/.well-known/oauth-protected-resource/mcp"'
        in header
    )
    assert "evil.example" not in header
    assert "naom-naama" not in header
    assert "localhost" not in header


def test_personal_hcal_keys_still_work_when_discovery_is_on(app, client, monkeypatch):
    _set_origin(monkeypatch, HEBCAL)
    user = add_user(app)
    token = make_key(app, user)
    assert token.startswith("hcal_")
    ok = post(
        client,
        token,
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        SPOOF,
    )
    assert ok.status_code == 200
    assert ok.get_json()["result"] == {}
    denied = post(client, "hcal_deadbeef_" + "A" * 43, {"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert denied.status_code == 401
    assert denied.get_json()["error"] == "invalid_token"


def test_env_example_documents_public_origin():
    from pathlib import Path

    env = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "HEB_CAL_PUBLIC_ORIGIN=" in env
    assert "X-Forwarded" in env
    assert "hebcal.corcos.app" in env
