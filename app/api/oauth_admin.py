"""ניהול לקוחות OAuth וחיבורים. מאחורי Access כמו שאר /api. CSRF בכתיבה."""
from flask import jsonify, request

from . import api
from app.oauth.clients import OauthClientError, create_client, get_client, list_clients, revoke_client
from app.oauth.origin import public_origin
from app.oauth.resource import mcp_resource_url
from app.oauth.tokens import list_connections, revoke_grant_id
from app.updates.security import issue_csrf, require_csrf


def _no_store(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@api.route("/oauth/overview", methods=["GET"])
def oauth_overview():
    origin = public_origin()
    return _no_store(jsonify({
        "csrf_token": issue_csrf(),
        "public_origin": origin,
        "mcp_url": mcp_resource_url(origin) if origin else None,
        "clients": list_clients(),
        "connections": list_connections(),
    }))


@api.route("/oauth/clients", methods=["POST"])
def oauth_clients_create():
    blocked = require_csrf()
    if blocked:
        return blocked
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        data = {}
    try:
        client_id, secret, row = create_client(data.get("name"), data.get("redirect_uris"))
    except OauthClientError as exc:
        return _no_store(jsonify({"error": str(exc), "success": False})), 400
    return _no_store(jsonify({
        "success": True,
        "client_id": client_id,
        "client_secret": secret,
        "client": row,
    })), 201


@api.route("/oauth/clients/<client_id>", methods=["DELETE"])
def oauth_clients_revoke(client_id):
    blocked = require_csrf()
    if blocked:
        return blocked
    if not revoke_client(client_id):
        return jsonify({"error": "הלקוח לא נמצא", "success": False}), 404
    return _no_store(jsonify({"success": True, "client": get_client(client_id)}))


@api.route("/oauth/connections/<int:grant_id>", methods=["DELETE"])
def oauth_connections_revoke(grant_id):
    blocked = require_csrf()
    if blocked:
        return blocked
    if not revoke_grant_id(grant_id):
        return jsonify({"error": "החיבור לא נמצא", "success": False}), 404
    return _no_store(jsonify({"success": True}))
