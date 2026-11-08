"""עזרי בדיקה ל-OAuth: JWT חתום, PKCE, לקוח רשום. בלי סודות קבועים בריפו."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from jwt.algorithms import RSAAlgorithm
from cryptography.hazmat.primitives.asymmetric import rsa

from app.oauth.clients import create_client
from app.oauth.pkce import s256_challenge

ISSUER = "https://access.test.invalid"
AUD = "test-audience"
EMAIL = "avichay@example.com"
REDIRECT = "http://127.0.0.1:3999/cb"


def rsa_pair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    public_jwk["kid"] = "test-1"
    public_jwk["use"] = "sig"
    public_jwk["alg"] = "RS256"
    return private, {"keys": [public_jwk]}


def configure_access(monkeypatch, jwks, *, origin="https://hebcal.corcos.app"):
    monkeypatch.setenv("HEB_CAL_PUBLIC_ORIGIN", origin)
    monkeypatch.setenv("CF_ACCESS_ISSUER", ISSUER)
    monkeypatch.setenv("CF_ACCESS_AUD", AUD)
    monkeypatch.setenv("HEB_CAL_ACCESS_JWKS", json.dumps(jwks))
    from app.oauth import access_jwt

    access_jwt._jwks_cache["key"] = None
    access_jwt._jwks_cache["value"] = None


def access_jwt_token(private, email=EMAIL, *, exp_offset=3600, aud=AUD, iss=ISSUER, nbf_offset=None):
    now = datetime.now(timezone.utc)
    claims = {
        "iss": iss,
        "aud": aud,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_offset)).timestamp()),
    }
    if nbf_offset is not None:
        claims["nbf"] = int((now + timedelta(seconds=nbf_offset)).timestamp())
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "test-1"})


def jwt_headers(token: str) -> dict:
    return {"Cf-Access-Jwt-Assertion": token}


def pkce_pair():
    verifier = secrets.token_urlsafe(48)
    if len(verifier) < 43:
        verifier += "A" * (43 - len(verifier))
    return verifier, s256_challenge(verifier)


def make_client(app, name="בדיקה", redirects=None):
    with app.app_context():
        return create_client(name, redirects or [REDIRECT])


def authorize_url(client_id, challenge, *, resource="https://hebcal.corcos.app/mcp", scope="hebcal:read", state="st"):
    from urllib.parse import urlencode

    return "/oauth/authorize?" + urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "resource": resource,
            "scope": scope,
            "state": state,
        }
    )


def complete_code_flow(client, app, private, *, email=EMAIL, scope="hebcal:read hebcal:write"):
    client_id, secret, _row = make_client(app)
    verifier, challenge = pkce_pair()
    token = access_jwt_token(private, email)
    headers = jwt_headers(token)
    shown = client.get(authorize_url(client_id, challenge, scope=scope), headers=headers)
    assert shown.status_code == 200, shown.get_data(as_text=True)
    csrf = shown.get_data(as_text=True).split('name="csrf_token" value="', 1)[1].split('"', 1)[0]
    allowed = client.post(
        authorize_url(client_id, challenge, scope=scope),
        headers=headers,
        data={"csrf_token": csrf, "decision": "allow"},
    )
    assert allowed.status_code == 302
    location = allowed.headers["Location"]
    assert "code=" in location
    from urllib.parse import parse_qs, urlsplit

    code = parse_qs(urlsplit(location).query)["code"][0]
    exchanged = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": client_id,
            "client_secret": secret,
            "code_verifier": verifier,
        },
    )
    assert exchanged.status_code == 200, exchanged.get_data(as_text=True)
    return exchanged.get_json(), client_id, secret
