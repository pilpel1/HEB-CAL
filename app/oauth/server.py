"""שרת הרשאות בתוך האפליקציה: authorize, token, revoke."""
from __future__ import annotations

import base64
import binascii
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session

from app.oauth.access_jwt import (
    ACCESS_JWT_HEADER,
    AccessJwtError,
    configured as access_configured,
    email_from_claims,
    verify_access_jwt,
)
from app.oauth.clients import authenticate_client, get_client_row, redirect_allowed
from app.oauth.origin import public_origin
from app.oauth.pkce import valid_challenge
from app.oauth.resource import mcp_resource_url
from app.oauth.scopes import parse_scopes, scope_string
from app.oauth.tokens import (
    exchange_code,
    issue_code,
    refresh_grant,
    revoke_presented_token,
)
from app.updates.security import issue_csrf

oauth_server = Blueprint("oauth_server", __name__)

_FORM_CSRF = "oauth_consent_csrf"


def _secure(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _html_error(message: str, status: int) -> Response:
    body = render_template("oauth_error.html", message=message)
    return _secure(Response(body, status=status, mimetype="text/html; charset=utf-8"))


def _token_error(error: str, status: int = 400) -> Response:
    response = jsonify({"error": error})
    response.status_code = status
    return _secure(response)


def _add_query(uri: str, extra: dict) -> str:
    parts = urlsplit(uri)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: value for key, value in extra.items() if value is not None})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def _redirect_error(redirect_uri: str, error: str, state: str | None) -> Response:
    return _secure(redirect(_add_query(redirect_uri, {"error": error, "state": state})))


def _client_secret_from_request() -> tuple[str | None, str | None]:
    client_id = (request.form.get("client_id") or "").strip() or None
    secret = request.form.get("client_secret")
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "basic" and value:
        try:
            decoded = base64.b64decode(value.strip(), validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None, None
        client_id, _, secret = decoded.partition(":")
        client_id = client_id or None
    if secret == "":
        secret = None
    return client_id, secret


def _identity():
    if not access_configured():
        raise AccessJwtError("unconfigured")
    claims = verify_access_jwt(request.headers.get(ACCESS_JWT_HEADER))
    email = email_from_claims(claims)
    if not email:
        raise AccessJwtError("email")
    from app.reminders.repository import find_person_by_google_email

    person = find_person_by_google_email(email)
    if person is None:
        raise AccessJwtError("unknown_user")
    return person, email


def _validate_authorize_query():
    origin = public_origin()
    if origin is None:
        return None, _html_error("OAuth לא מוגדר בלוח הזה.", 404)
    client_id = (request.values.get("client_id") or "").strip()
    redirect_uri = (request.values.get("redirect_uri") or "").strip()
    response_type = (request.values.get("response_type") or "").strip()
    state = request.values.get("state")
    challenge = request.values.get("code_challenge")
    method = (request.values.get("code_challenge_method") or "").strip()
    resource = (request.values.get("resource") or "").strip()
    scopes = parse_scopes(request.values.get("scope"))
    row = get_client_row(client_id)
    if row is None or row["revoked_at"] or not redirect_allowed(row, redirect_uri):
        return None, _html_error("הלקוח או כתובת ההפניה לא מורשים.", 400)
    if response_type != "code":
        return None, _redirect_error(redirect_uri, "unsupported_response_type", state)
    if method != "S256" or not valid_challenge(challenge):
        return None, _redirect_error(redirect_uri, "invalid_request", state)
    if scopes is None:
        return None, _redirect_error(redirect_uri, "invalid_scope", state)
    expected_resource = mcp_resource_url(origin)
    if resource != expected_resource:
        return None, _redirect_error(redirect_uri, "invalid_target", state)
    return {
        "client_id": client_id,
        "client_name": row["name"],
        "redirect_uri": redirect_uri,
        "state": state,
        "challenge": challenge,
        "scopes": scopes,
        "resource": expected_resource,
        "issuer": origin,
        "board": origin.replace("https://", "").replace("http://", ""),
    }, None


@oauth_server.route("/oauth/authorize", methods=["GET", "POST"])
def authorize():
    params, error = _validate_authorize_query()
    if error is not None:
        return error
    try:
        person, email = _identity()
    except AccessJwtError as exc:
        if exc.args and exc.args[0] == "unknown_user":
            return _html_error(
                "החשבון המחובר לא משויך למשתמש בלוח הזה. הוסיפו את האימייל בהגדרות ← משתמשים.",
                403,
            )
        return _html_error("לא ניתן לאשר גישה. התחברו דרך Cloudflare Access.", 403)

    if request.method == "GET":
        token = issue_csrf()
        session[_FORM_CSRF] = token
        session["oauth_consent"] = {
            "client_id": params["client_id"],
            "redirect_uri": params["redirect_uri"],
            "state": params["state"],
            "challenge": params["challenge"],
            "scopes": params["scopes"],
            "resource": params["resource"],
            "issuer": params["issuer"],
            "user_id": person["id"],
            "email": email,
        }
        html = render_template(
            "oauth_consent.html",
            board=params["board"],
            client_name=params["client_name"],
            scopes=params["scopes"],
            email=email,
            user_name=person["name"],
            csrf_token=token,
        )
        return _secure(Response(html, mimetype="text/html; charset=utf-8"))

    sent = request.form.get("csrf_token") or ""
    expected = session.get(_FORM_CSRF) or ""
    consent = session.get("oauth_consent") or {}
    if not expected or not _csrf_ok(sent, expected):
        return _html_error("הבקשה נחסמה. רעננו את העמוד ונסו שוב.", 403)
    if (
        consent.get("client_id") != params["client_id"]
        or consent.get("redirect_uri") != params["redirect_uri"]
        or consent.get("challenge") != params["challenge"]
        or consent.get("resource") != params["resource"]
        or consent.get("user_id") != person["id"]
    ):
        return _html_error("הבקשה נחסמה. רעננו את העמוד ונסו שוב.", 403)

    decision = request.form.get("decision")
    session.pop("oauth_consent", None)
    session.pop(_FORM_CSRF, None)
    if decision != "allow":
        return _redirect_error(params["redirect_uri"], "access_denied", params["state"])
    code = issue_code(
        client_id=params["client_id"],
        user_id=person["id"],
        resource=params["resource"],
        issuer=params["issuer"],
        redirect_uri=params["redirect_uri"],
        scopes=scope_string(params["scopes"]),
        code_challenge=params["challenge"],
    )
    return _secure(redirect(_add_query(params["redirect_uri"], {"code": code, "state": params["state"]})))


def _csrf_ok(sent: str, expected: str) -> bool:
    import hmac

    if not sent or not expected or len(sent) != len(expected):
        return False
    return hmac.compare_digest(sent, expected)


@oauth_server.route("/oauth/token", methods=["POST"])
def token():
    if public_origin() is None:
        return _token_error("invalid_request", 404)
    grant_type = (request.form.get("grant_type") or "").strip()
    client_id, secret = _client_secret_from_request()
    client = authenticate_client(client_id, secret)
    if client is None:
        return _token_error("invalid_client", 401)

    if grant_type == "authorization_code":
        issued = exchange_code(
            code=request.form.get("code") or "",
            client_id=client["client_id"],
            redirect_uri=request.form.get("redirect_uri") or "",
            code_verifier=request.form.get("code_verifier") or "",
        )
        if issued is None:
            return _token_error("invalid_grant")
        return _secure(jsonify(issued))

    if grant_type == "refresh_token":
        issued = refresh_grant(request.form.get("refresh_token") or "", client["client_id"])
        if issued is None:
            return _token_error("invalid_grant")
        return _secure(jsonify(issued))

    return _token_error("unsupported_grant_type")


@oauth_server.route("/oauth/revoke", methods=["POST"])
def revoke():
    if public_origin() is None:
        return _token_error("invalid_request", 404)
    client_id, secret = _client_secret_from_request()
    client = authenticate_client(client_id, secret)
    if client is None:
        return _token_error("invalid_client", 401)
    token_value = request.form.get("token") or ""
    if token_value:
        revoke_presented_token(token_value, client["client_id"])
    response = Response(status=200)
    return _secure(response)


def authorization_server_metadata() -> dict | None:
    origin = public_origin()
    if origin is None:
        return None
    return {
        "issuer": origin,
        "authorization_endpoint": f"{origin}/oauth/authorize",
        "token_endpoint": f"{origin}/oauth/token",
        "revocation_endpoint": f"{origin}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
            "none",
        ],
        "scopes_supported": ["hebcal:read", "hebcal:write"],
        "authorization_response_iss_parameter_supported": False,
    }
