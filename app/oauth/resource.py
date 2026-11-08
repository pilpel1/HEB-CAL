"""מסמך RFC 9728 למשאב ``POST /mcp`` ואתגר 401."""
from __future__ import annotations

from app.oauth.origin import public_origin

SCOPES = ("hebcal:read", "hebcal:write")
MCP_PATH = "/mcp"
METADATA_PATH = "/.well-known/oauth-protected-resource"
METADATA_MCP_PATH = "/.well-known/oauth-protected-resource/mcp"
AS_METADATA_PATH = "/.well-known/oauth-authorization-server"
_BEARER_BASE = 'Bearer realm="heb-cal", error="invalid_token"'


def mcp_resource_url(origin: str) -> str:
    return f"{origin}{MCP_PATH}"


def mcp_resource_metadata_url(origin: str) -> str:
    return f"{origin}{METADATA_MCP_PATH}"


def protected_resource_metadata() -> dict | None:
    origin = public_origin()
    if origin is None:
        return None
    return {
        "resource": mcp_resource_url(origin),
        "authorization_servers": [origin],
        "bearer_methods_supported": ["header"],
        "scopes_supported": list(SCOPES),
    }


def mcp_www_authenticate() -> str:
    origin = public_origin()
    if origin is None:
        return _BEARER_BASE
    metadata = mcp_resource_metadata_url(origin)
    if '"' in metadata or "\\" in metadata:
        return _BEARER_BASE
    return f'{_BEARER_BASE}, resource_metadata="{metadata}"'
