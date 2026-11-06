"""עזרים משותפים לבדיקות ה-MCP (לא מודול בדיקות — pytest לא אוסף אותו)."""
from __future__ import annotations

import base64
import json

LEGACY = "2025-11-25"
MODERN = "2026-07-28"


def add_user(app, name="אביחי", google_email=None) -> int:
    with app.app_context():
        from app.database import get_db

        db = get_db()
        cursor = db.execute(
            "INSERT INTO users (name, google_email) VALUES (?, ?)",
            (name, google_email),
        )
        db.commit()
        return cursor.lastrowid


def make_key(app, user_id, permission="write", label="בדיקה", absolute=None) -> str:
    with app.app_context():
        from app.mcp.keys import create_key

        token, _key = create_key(user_id, label, permission, absolute)
        return token


def key_row(app, token=None):
    with app.app_context():
        from app.database import get_db

        rows = get_db().execute("SELECT * FROM mcp_keys ORDER BY id").fetchall()
        return [dict(row) for row in rows]


def post(client, token, message, headers=None, raw=None):
    sent = {"Content-Type": "application/json"}
    if token is not None:
        sent["Authorization"] = f"Bearer {token}"
    sent.update(headers or {})
    body = raw if raw is not None else json.dumps(message, ensure_ascii=False)
    return client.post("/mcp", data=body, headers=sent)


def legacy(client, token, method, params=None, request_id=1, version=LEGACY):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    headers = {"MCP-Protocol-Version": version} if version else {}
    return post(client, token, message, headers)


def modern(client, token, method, params=None, request_id=1, headers=None, version=MODERN):
    params = dict(params or {})
    params["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientInfo": {"name": "pytest", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    sent = {"MCP-Protocol-Version": version, "Mcp-Method": method}
    if method == "tools/call":
        name = params.get("name") or ""
        sent["Mcp-Name"] = name if name.isascii() else "=?base64?" + base64.b64encode(name.encode()).decode() + "?="
    sent.update(headers or {})
    return post(client, token, {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, sent)


def call(client, token, name, arguments=None):
    """``tools/call`` ב-legacy. מחזיר את ה-result (כולל isError)."""
    response = legacy(client, token, "tools/call", {"name": name, "arguments": arguments or {}})
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    assert "result" in body, body
    return body["result"]


def ok(client, token, name, arguments=None) -> dict:
    result = call(client, token, name, arguments)
    assert result["isError"] is False, result
    return result["structuredContent"]


def tool_error(client, token, name, arguments=None) -> dict:
    result = call(client, token, name, arguments)
    assert result["isError"] is True, result
    return result["structuredContent"]["error"]


def db_snapshot(app) -> dict:
    with app.app_context():
        from app.database import get_db

        db = get_db()
        return {
            table: [tuple(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()]
            for table in ("events", "event_exceptions", "reminders")
        }
