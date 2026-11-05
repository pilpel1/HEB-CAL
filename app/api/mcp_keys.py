"""ניהול מפתחות MCP מעמוד ההגדרות.

הנתיבים כאן מאחורי Cloudflare Access כמו שאר ``/api``. יצירה וביטול דורשים
CSRF. מפתח MCP עצמו לא פותח שום נתיב כאן — הוא תקף רק ב-``/mcp``.
"""
from flask import jsonify, request

from . import api
from app.mcp.keys import McpKeyError, create_key, get_key, list_keys, revoke_key
from app.updates.security import issue_csrf, require_csrf


def _no_store(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@api.route("/mcp-keys", methods=["GET"])
def mcp_keys_index():
    from app.reminders.repository import list_people
    from app.users import current_access_user

    owner = current_access_user()
    users = [{"id": person["id"], "name": person["name"]} for person in list_people()]
    return _no_store(jsonify({
        "keys": list_keys(),
        "users": users,
        "default_user_id": owner["id"] if owner else None,
        "csrf_token": issue_csrf(),
    }))


@api.route("/mcp-keys", methods=["POST"])
def mcp_keys_create():
    blocked = require_csrf()
    if blocked:
        return blocked
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        data = {}
    try:
        token, key = create_key(
            data.get("user_id"),
            data.get("label"),
            data.get("permission"),
            data.get("absolute_expires_on"),
        )
    except McpKeyError as exc:
        return _no_store(jsonify({"error": str(exc), "success": False})), 400
    response = jsonify({"success": True, "token": token, "key": key})
    response.status_code = 201
    return _no_store(response)


@api.route("/mcp-keys/<int:key_id>", methods=["DELETE"])
def mcp_keys_revoke(key_id):
    blocked = require_csrf()
    if blocked:
        return blocked
    if not revoke_key(key_id):
        return jsonify({"error": "המפתח לא נמצא", "success": False}), 404
    return _no_store(jsonify({"success": True, "key": get_key(key_id)}))
