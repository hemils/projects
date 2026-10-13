"""Validate OIDC access tokens for identity-aware Gateway routing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient


class IdentityTokenError(ValueError):
    """Raised when an access token or its trusted identity claims are invalid."""


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """User identity read from a cryptographically verified access token."""

    subject: str


@lru_cache(maxsize=8)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    """Reuse JWKS clients so signing keys are cached across selector requests."""
    return PyJWKClient(jwks_url, cache_keys=True, timeout=5)


def verify_access_token(token: str) -> AuthenticatedIdentity:
    """Validate a bearer JWT using configured OIDC issuer, audience, and JWKS.

    Configuration is intentionally explicit so tokens for another issuer or
    API cannot be accepted by mistake. Network location is resolved separately
    from the verified client connection at a trusted edge.
    """
    issuer = os.getenv("OIDC_ISSUER", "").strip()
    audience = os.getenv("OIDC_AUDIENCE", "").strip()
    jwks_url = os.getenv("OIDC_JWKS_URL", "").strip()
    if not issuer or not audience or not jwks_url:
        raise IdentityTokenError("OIDC issuer, audience, and JWKS URL must be configured")

    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception as exc:
        raise IdentityTokenError("Bearer token validation failed") from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise IdentityTokenError("Verified token is missing a subject")

    return AuthenticatedIdentity(subject=subject.strip())
