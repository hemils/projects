from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from pdp.identity import IdentityTokenError, verify_access_token


def test_verified_access_token_extracts_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ISSUER", "https://login.microsoftonline.com/test-tenant/v2.0")
    monkeypatch.setenv("OIDC_AUDIENCE", "api://trino-poc")
    monkeypatch.setenv(
        "OIDC_JWKS_URL",
        "https://login.microsoftonline.com/test-tenant/discovery/v2.0/keys",
    )

    class SigningKey:
        key = "verified-public-key"

    class JwksClient:
        def get_signing_key_from_jwt(self, token: str) -> SigningKey:
            assert token == "signed-token"
            return SigningKey()

    monkeypatch.setattr("pdp.identity._jwks_client", lambda _: JwksClient())
    monkeypatch.setattr(
        "pdp.identity.jwt.decode",
        lambda *args, **kwargs: {"sub": "stable-user-subject"},
    )

    identity = verify_access_token("signed-token")

    assert identity.subject == "stable-user-subject"


def test_access_token_validation_requires_oidc_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OIDC_ISSUER", "OIDC_AUDIENCE", "OIDC_JWKS_URL"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(IdentityTokenError, match="must be configured"):
        verify_access_token("token")


def test_verified_token_requires_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OIDC_ISSUER", "https://issuer.example/")
    monkeypatch.setenv("OIDC_AUDIENCE", "api://trino-poc")
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example/keys")

    class SigningKey:
        key = "verified-public-key"

    class JwksClient:
        def get_signing_key_from_jwt(self, token: str) -> SigningKey:
            return SigningKey()

    monkeypatch.setattr("pdp.identity._jwks_client", lambda _: JwksClient())
    monkeypatch.setattr(
        "pdp.identity.jwt.decode",
        lambda *args, **kwargs: {},
    )

    with pytest.raises(IdentityTokenError, match="subject"):
        verify_access_token("signed-token")


def test_access_token_is_cryptographically_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    issuer = "https://login.microsoftonline.com/test-tenant/v2.0"
    audience = "api://trino-poc"
    monkeypatch.setenv("OIDC_ISSUER", issuer)
    monkeypatch.setenv("OIDC_AUDIENCE", audience)
    monkeypatch.setenv("OIDC_JWKS_URL", "https://issuer.example/keys")

    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": "stable-user-subject",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "poc-key"})

    class SigningKey:
        key = signing_key.public_key()

    class JwksClient:
        def get_signing_key_from_jwt(self, _: str) -> SigningKey:
            return SigningKey()

    monkeypatch.setattr("pdp.identity._jwks_client", lambda _: JwksClient())

    identity = verify_access_token(token)

    assert identity.subject == "stable-user-subject"

    wrong_audience = jwt.encode(
        {**claims, "aud": "api://another-api"},
        signing_key,
        algorithm="RS256",
        headers={"kid": "poc-key"},
    )
    with pytest.raises(IdentityTokenError, match="validation failed"):
        verify_access_token(wrong_audience)

