"""Streamable HTTP ל-MCP: POST יחיד, תשובת JSON, בלי sessions ובלי SSE.

שני דורות על אותו endpoint:
- legacy (2025-03-26 עד 2025-11-25): ``initialize`` ואז בקשות רגילות.
- modern (2026-07-28): כל בקשה נושאת ``_meta`` עם הגרסה, וה-headers
  ``MCP-Protocol-Version`` / ``Mcp-Method`` / ``Mcp-Name`` חייבים להתאים לגוף.

הטוקן נקרא רק מ-``Authorization`` ולא נכתב לשום לוג או תשובה.
"""
from __future__ import annotations

import base64
import binascii
import json
import os
from urllib.parse import urlsplit

from flask import Blueprint, Response, request

from app.mcp import keys as mcp_keys
from app.mcp.tools import UnknownTool, call_tool, visible_tools
from app.oauth.resource import mcp_www_authenticate

mcp = Blueprint("mcp", __name__)

MODERN_VERSIONS = ("2026-07-28",)
LEGACY_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
DEFAULT_LEGACY_VERSION = "2025-03-26"
MAX_BODY_BYTES = 64 * 1024

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
HEADER_MISMATCH = -32020
UNSUPPORTED_PROTOCOL_VERSION = -32022

META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

INSTRUCTIONS = (
    "HEB-CAL is a shared Hebrew/Gregorian household calendar. Dates accept YYYY-MM-DD or Hebrew text. "
    "Use list_events for a date range, then pass id and occurrence_date of recurring events to "
    "update_event / delete_event with scope 'occurrence' or 'all'. Events with read_only=true "
    "(Google-imported or shifts) cannot be changed here."
)


def _server_info() -> dict:
    from app.updates.version import installed_version

    return {"name": "heb-cal", "title": "HEB-CAL", "version": installed_version() or "0"}


def _json(payload, status: int = 200, headers: dict | None = None) -> Response:
    response = Response(json.dumps(payload, ensure_ascii=False), status=status, mimetype="application/json")
    response.headers["Cache-Control"] = "no-store"
    for name, value in (headers or {}).items():
        response.headers[name] = value
    return response


def _rpc_error(code: int, message: str, *, status: int, request_id=None, data=None, headers=None) -> Response:
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    payload = {"jsonrpc": "2.0", "error": error}
    if request_id is not None:
        payload["id"] = request_id
    return _json(payload, status, headers)


def _rpc_result(request_id, result: dict) -> Response:
    return _json({"jsonrpc": "2.0", "id": request_id, "result": result})


def _allowed_origins() -> set[str]:
    allowed = set()
    host = request.host
    for scheme in ("https", "http"):
        allowed.add(f"{scheme}://{host}".lower())
    extra = os.getenv("HEB_CAL_MCP_ALLOWED_ORIGINS", "")
    for item in extra.split(","):
        item = item.strip().rstrip("/").lower()
        if item:
            allowed.add(item)
    return allowed


def _origin_ok() -> bool:
    origin = request.headers.get("Origin")
    if origin is None:
        return True
    parts = urlsplit(origin.strip())
    if not parts.scheme or not parts.netloc:
        return False
    return f"{parts.scheme}://{parts.netloc}".lower() in _allowed_origins()


def _authenticate(token: str | None):
    key = mcp_keys.authenticate(token)
    if key is not None:
        key["kind"] = "key"
        return key
    from app.oauth.tokens import authenticate_access

    return authenticate_access(token)


def _touch(principal: dict) -> None:
    if principal.get("kind") == "oauth":
        from app.oauth.tokens import touch_grant

        touch_grant(principal)
        return
    mcp_keys.touch(principal)


def _unauthorized() -> Response:
    return _json(
        {"error": "invalid_token", "error_description": "מפתח חסר, לא תקף, בוטל או פג תוקף"},
        401,
        {"WWW-Authenticate": mcp_www_authenticate()},
    )


def _bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    value = value.strip()
    return value or None


def _decode_header(value: str | None) -> str | None:
    """``=?base64?...?=`` → טקסט. ערך לא תקין → None."""
    if value is None:
        return None
    if value.startswith("=?base64?") and value.endswith("?="):
        try:
            return base64.b64decode(value[9:-2], validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
    return value


def _read_body() -> bytes | None:
    length = request.content_length
    if length is not None and length > MAX_BODY_BYTES:
        return None
    data = request.stream.read(MAX_BODY_BYTES + 1)
    if len(data) > MAX_BODY_BYTES:
        return None
    return data


def _modern_header_error(message: dict, version: str):
    """None אם ה-headers תואמים לגוף, אחרת תשובת 400 עם HeaderMismatch."""
    request_id = message.get("id")
    header_version = request.headers.get("MCP-Protocol-Version")
    if header_version != version:
        return _rpc_error(HEADER_MISMATCH, "MCP-Protocol-Version header does not match _meta", status=400, request_id=request_id)
    if request.headers.get("Mcp-Method") != message.get("method"):
        return _rpc_error(HEADER_MISMATCH, "Mcp-Method header does not match method", status=400, request_id=request_id)
    if message.get("method") == "tools/call":
        params = message.get("params") or {}
        raw = request.headers.get("Mcp-Name")
        if raw is None or _decode_header(raw) != params.get("name"):
            return _rpc_error(HEADER_MISMATCH, "Mcp-Name header does not match params.name", status=400, request_id=request_id)
    return None


def _capabilities() -> dict:
    return {"tools": {"listChanged": False}}


def _dispatch(message: dict, key: dict, *, modern: bool):
    """(Response, הצליח). שגיאת JSON-RPC של כלי/פרוטוקול לא מאריכה תוקף."""
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params")
    if params is not None and not isinstance(params, dict):
        return _rpc_error(INVALID_PARAMS, "params must be an object", status=400 if modern else 200, request_id=request_id), False
    params = params or {}

    if method == "ping":
        return _rpc_result(request_id, {"resultType": "complete"} if modern else {}), True
    if method == "server/discover" and modern:
        return _rpc_result(request_id, {
            "supportedVersions": list(MODERN_VERSIONS),
            "capabilities": _capabilities(),
            "instructions": INSTRUCTIONS,
            "resultType": "complete",
            "cacheScope": "private",
            "ttlMs": 0,
            "_meta": {META_SERVER_INFO: _server_info()},
        }), True
    if method == "tools/list":
        result = {"tools": visible_tools(key["permission"])}
        if modern:
            result.update({"resultType": "complete", "cacheScope": "private", "ttlMs": 0})
        return _rpc_result(request_id, result), True
    if method == "tools/call":
        try:
            result = call_tool(params.get("name"), params.get("arguments"), key["permission"])
        except UnknownTool:
            return _rpc_error(INVALID_PARAMS, "Unknown tool", status=400 if modern else 200, request_id=request_id), False
        if modern:
            result["resultType"] = "complete"
        return _rpc_result(request_id, result), True

    status = 404 if modern else 200
    return _rpc_error(METHOD_NOT_FOUND, "Method not found", status=status, request_id=request_id), False


def _initialize(message: dict) -> Response:
    params = message.get("params") or {}
    requested = params.get("protocolVersion") if isinstance(params, dict) else None
    version = requested if requested in LEGACY_VERSIONS else LEGACY_VERSIONS[0]
    return _rpc_result(message.get("id"), {
        "protocolVersion": version,
        "capabilities": _capabilities(),
        "serverInfo": _server_info(),
        "instructions": INSTRUCTIONS,
    })


@mcp.route("/mcp", methods=["GET", "DELETE"])
def mcp_not_allowed():
    if not _origin_ok():
        return _rpc_error(INVALID_REQUEST, "Origin not allowed", status=403)
    response = _rpc_error(INVALID_REQUEST, "Method not allowed. POST JSON-RPC to this endpoint", status=405)
    response.headers["Allow"] = "POST"
    return response


@mcp.route("/mcp", methods=["POST"])
def mcp_endpoint():
    if not _origin_ok():
        return _rpc_error(INVALID_REQUEST, "Origin not allowed", status=403)

    key = _authenticate(_bearer_token())
    if key is None:
        return _unauthorized()

    body = _read_body()
    if body is None:
        return _rpc_error(INVALID_REQUEST, "Request body too large", status=413)
    content_type = (request.mimetype or "").lower()
    if content_type != "application/json":
        return _rpc_error(INVALID_REQUEST, "Content-Type must be application/json", status=415)
    try:
        message = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _rpc_error(PARSE_ERROR, "Parse error", status=400)
    if isinstance(message, list):
        return _rpc_error(INVALID_REQUEST, "Batch requests are not supported", status=400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _rpc_error(INVALID_REQUEST, "Invalid JSON-RPC message", status=400)
    method = message.get("method")
    if not isinstance(method, str):
        return _rpc_error(INVALID_REQUEST, "Only requests and notifications are accepted", status=400, request_id=message.get("id"))
    request_id = message.get("id")
    if "id" in message and (isinstance(request_id, bool) or not isinstance(request_id, (str, int))):
        return _rpc_error(INVALID_REQUEST, "Invalid request id", status=400)

    params = message.get("params")
    meta = params.get("_meta") if isinstance(params, dict) else None
    modern_version = meta.get(META_VERSION) if isinstance(meta, dict) else None

    if "id" not in message:
        _touch(key)
        return Response(status=202)

    if method == "initialize":
        response = _initialize(message)
        _touch(key)
        return response

    if modern_version is not None:
        if modern_version not in MODERN_VERSIONS:
            return _rpc_error(
                UNSUPPORTED_PROTOCOL_VERSION,
                "Unsupported protocol version",
                status=400,
                request_id=request_id,
                data={"supported": list(MODERN_VERSIONS), "requested": str(modern_version)},
            )
        mismatch = _modern_header_error(message, modern_version)
        if mismatch is not None:
            return mismatch
        response, ok = _dispatch(message, key, modern=True)
    else:
        header_version = request.headers.get("MCP-Protocol-Version") or DEFAULT_LEGACY_VERSION
        if header_version not in LEGACY_VERSIONS:
            return _rpc_error(
                HEADER_MISMATCH if header_version in MODERN_VERSIONS else UNSUPPORTED_PROTOCOL_VERSION,
                "Unsupported or mismatched MCP-Protocol-Version",
                status=400,
                request_id=request_id,
                data={"supported": list(MODERN_VERSIONS + LEGACY_VERSIONS), "requested": header_version},
            )
        response, ok = _dispatch(message, key, modern=False)
    if ok:
        _touch(key)
    return response
