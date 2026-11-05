"""גבולות ה-POST /mcp: אימות, Origin, גרסה, גודל, ושמפתח קריאה לא כותב."""
from __future__ import annotations

import json

import pytest
from mcp.types import CallToolResult, DiscoverResult, InitializeResult, ListToolsResult

from app.mcp.tools import TOOLS
from mcp_support import LEGACY, MODERN, add_user, db_snapshot, key_row, legacy, make_key, modern, post

META = "io.modelcontextprotocol/protocolVersion"


def _meta():
    return {
        META: MODERN,
        "io.modelcontextprotocol/clientInfo": {"name": "pytest", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }


def test_only_the_exact_mcp_path_is_registered(app, client):
    rules = {
        rule.rule for rule in app.url_map.iter_rules() if rule.rule == "/mcp" or rule.rule.startswith("/mcp/")
    }
    assert rules == {"/mcp"}
    for path in ("/mcp/extra", "/mcpfoo", "/mcp/keys", "/.well-known/oauth-protected-resource"):
        assert client.get(path).status_code == 404
        assert client.post(path, data=b"{}", headers={"Content-Type": "application/json"}).status_code == 404


def test_get_and_delete_are_rejected(app, client):
    user = add_user(app)
    token = make_key(app, user)
    for method in ("get", "delete"):
        response = getattr(client, method)("/mcp", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 405
        assert response.headers["Allow"] == "POST"
        assert "Mcp-Session-Id" not in response.headers


def test_origin_must_match_the_host(app, client):
    user = add_user(app)
    token = make_key(app, user)
    message = {"jsonrpc": "2.0", "id": 1, "method": "ping"}
    blocked = post(client, token, message, {"Origin": "https://evil.example"})
    assert blocked.status_code == 403
    allowed = post(client, token, message, {"Origin": "http://localhost"})
    assert allowed.status_code == 200
    assert post(client, token, message).status_code == 200


def test_malformed_oversized_and_batched_requests(app, client):
    user = add_user(app)
    token = make_key(app, user)
    before = key_row(app)[0]

    parsed = post(client, token, None, raw=b"{")
    assert parsed.status_code == 400
    assert parsed.get_json()["error"]["code"] == -32700

    batched = post(client, token, [{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
    assert batched.status_code == 400
    assert batched.get_json()["error"]["code"] == -32600

    typed = post(client, token, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"Content-Type": "text/plain"})
    assert typed.status_code == 415

    huge = post(client, token, None, raw=b"{" + b" " * (64 * 1024))
    assert huge.status_code == 413

    assert key_row(app)[0] == before


def test_invalid_key_is_rejected_before_the_body_is_parsed(app, client):
    response = post(
        client,
        "hcal_abcdabcd_" + "A" * 43,
        None,
        raw=b"this is not json and it is fine",
    )
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    assert "WWW-Authenticate" in response.headers
    assert "resource_metadata" not in response.headers["WWW-Authenticate"]
    assert response.get_json()["error"] == "invalid_token"
    missing = client.post("/mcp", data=b"{", headers={"Content-Type": "application/json"})
    assert missing.status_code == 401


def test_legacy_initialize_and_modern_discover_match_the_sdk(app, client):
    user = add_user(app)
    token = make_key(app, user)
    for version in ("2025-11-25", "2025-06-18", "2025-03-26", "1999-01-01"):
        response = legacy(
            client,
            token,
            "initialize",
            {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
            version=None,
        )
        assert response.status_code == 200
        result = InitializeResult.model_validate(response.get_json()["result"])
        assert result.protocol_version == (version if version.startswith("2025") else "2025-11-25")
        assert result.server_info.name == "heb-cal"

    discovered = modern(client, token, "server/discover")
    assert discovered.status_code == 200
    parsed = DiscoverResult.model_validate(discovered.get_json()["result"])
    assert list(parsed.supported_versions) == [MODERN]
    assert parsed.instructions

    listed = modern(client, token, "tools/list")
    tools = ListToolsResult.model_validate(listed.get_json()["result"])
    assert {tool.name for tool in tools.tools} == set(TOOLS)

    called = modern(client, token, "tools/call", {"name": "convert_date", "arguments": {"date": "2026-11-05"}})
    result = CallToolResult.model_validate(called.get_json()["result"])
    assert result.is_error is False
    assert result.structured_content["gregorian_date"] == "2026-11-05"


def test_modern_header_and_version_failures(app, client):
    user = add_user(app)
    token = make_key(app, user)
    params = {"_meta": _meta()}

    mismatch = modern(client, token, "ping", params, headers={"MCP-Protocol-Version": LEGACY})
    assert mismatch.status_code == 400
    assert mismatch.get_json()["error"]["code"] == -32020

    missing_name = modern(
        client,
        token,
        "tools/call",
        {"name": "convert_date", "arguments": {"date": "2026-11-05"}, "_meta": _meta()},
        headers={"Mcp-Name": "other"},
    )
    assert missing_name.status_code == 400
    assert missing_name.get_json()["error"]["code"] == -32020

    unknown = modern(client, token, "ping", version="2026-01-01")
    assert unknown.status_code == 400
    error = unknown.get_json()["error"]
    assert error["code"] == -32022
    assert error["data"]["supported"] == [MODERN]

    legacy_unknown = legacy(client, token, "ping", version="2024-11-05")
    assert legacy_unknown.status_code == 400
    assert legacy_unknown.get_json()["error"]["code"] == -32022


def test_unknown_method_and_session_header(app, client):
    user = add_user(app)
    token = make_key(app, user)
    old = legacy(client, token, "resources/list", version=LEGACY)
    assert old.status_code == 200
    assert old.get_json()["error"]["code"] == -32601
    new = modern(client, token, "resources/list")
    assert new.status_code == 404
    assert new.get_json()["error"]["code"] == -32601

    ignored = legacy(client, token, "ping", version=LEGACY)
    sent = post(
        client,
        token,
        {"jsonrpc": "2.0", "id": 1, "method": "ping"},
        {"MCP-Protocol-Version": LEGACY, "Mcp-Session-Id": "abc"},
    )
    assert sent.status_code == 200
    assert "Mcp-Session-Id" not in sent.headers
    assert ignored.status_code == 200


def test_notification_is_accepted_and_a_bad_one_is_not_a_session(app, client):
    user = add_user(app)
    token = make_key(app, user)
    response = post(client, token, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert response.status_code == 202
    assert response.get_data() == b""
    assert key_row(app)[0]["last_used_at"]


def test_every_tool_declares_a_permission_and_read_only_cannot_write(app, client):
    assert {name for name, tool in TOOLS.items() if tool.write} == {"create_event", "update_event", "delete_event"}
    for tool in TOOLS.values():
        assert isinstance(tool.write, bool)

    user = add_user(app)
    token = make_key(app, user, "read")
    writer = make_key(app, user, "write", label="כתיבה")
    created = modern(client, writer, "tools/call", {"name": "create_event", "arguments": {"title": "קיים", "date": "2026-12-01"}})
    assert created.get_json()["result"]["isError"] is False
    before = db_snapshot(app)

    listed = legacy(client, token, "tools/list").get_json()["result"]["tools"]
    assert {tool["name"] for tool in listed}.isdisjoint({name for name, tool in TOOLS.items() if tool.write})
    for name, tool in TOOLS.items():
        if not tool.write:
            continue
        response = legacy(client, token, "tools/call", {"name": name, "arguments": {}})
        result = response.get_json()["result"]
        assert result["isError"] is True
        assert json.loads(result["content"][0]["text"])["error"]["code"] == "forbidden"
    assert db_snapshot(app) == before


def test_unknown_tool_is_a_protocol_error(app, client):
    user = add_user(app)
    token = make_key(app, user, "write")
    response = legacy(client, token, "tools/call", {"name": "drop_database", "arguments": {}})
    assert response.get_json()["error"]["code"] == -32602
    assert "result" not in response.get_json()
