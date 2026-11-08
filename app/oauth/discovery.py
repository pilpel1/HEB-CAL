"""כתובות well-known: RFC 9728 ו-RFC 8414, רק כשהמקור הציבורי מוגדר."""
from __future__ import annotations

import json

from flask import Blueprint, Response, abort

from app.oauth.resource import (
    AS_METADATA_PATH,
    METADATA_MCP_PATH,
    METADATA_PATH,
    protected_resource_metadata,
)

oauth_discovery = Blueprint("oauth_discovery", __name__)


def _json_doc(document: dict | None, *, cache: str) -> Response:
    if document is None:
        abort(404)
    response = Response(json.dumps(document, ensure_ascii=False), mimetype="application/json")
    response.headers["Cache-Control"] = cache
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@oauth_discovery.get(METADATA_PATH)
def oauth_protected_resource():
    return _json_doc(protected_resource_metadata(), cache="public, max-age=300")


@oauth_discovery.get(METADATA_MCP_PATH)
def oauth_protected_resource_mcp():
    return _json_doc(protected_resource_metadata(), cache="public, max-age=300")


@oauth_discovery.get(AS_METADATA_PATH)
def oauth_authorization_server():
    from app.oauth.server import authorization_server_metadata

    return _json_doc(authorization_server_metadata(), cache="public, max-age=60")
