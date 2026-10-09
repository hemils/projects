"""OIDC-aware external routing selector for Trino Gateway."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool

from pdp import decide
from pdp.identity import AuthenticatedIdentity, IdentityTokenError, verify_access_token


TokenVerifier = Callable[[str], AuthenticatedIdentity]

DEFAULT_POLICY_ROUTING_GROUPS = {
    "unrestricted": "adhoc",
    "georestricted": "georestricted",
}


def _configured_routing_groups() -> dict[str, str]:
    """Map PDP destinations to groups registered with Trino Gateway."""
    configured = DEFAULT_POLICY_ROUTING_GROUPS.copy()
    for mapping in os.getenv("TRINO_POLICY_ROUTING_GROUPS", "").split(","):
        if not mapping.strip():
            continue
        policy_cluster, separator, routing_group = mapping.partition("=")
        if not separator or not policy_cluster.strip() or not routing_group.strip():
            raise ValueError("TRINO_POLICY_ROUTING_GROUPS must contain comma-separated cluster=group pairs")
        configured[policy_cluster.strip().lower()] = routing_group.strip()
    return configured


def _external_response(
    *, routing_group: str | None = None, errors: list[str] | None = None
) -> dict[str, Any]:
    """Return Trino Gateway's external-selector response shape."""
    return {
        "routingGroup": routing_group,
        "errors": errors or [],
        "externalHeaders": {},
    }


def _query_catalogs(body: Mapping[str, Any]) -> set[str] | None:
    """Read catalog analysis produced by Gateway's request analyzer."""
    query_properties = body.get("trinoQueryProperties")
    if not isinstance(query_properties, Mapping):
        return None
    if query_properties.get("isQueryParsingSuccessful") is not True:
        return None
    catalogs = query_properties.get("catalogs")
    if not isinstance(catalogs, (list, set, tuple)):
        return None
    return {
        catalog.strip().lower()
        for catalog in catalogs
        if isinstance(catalog, str) and catalog.strip()
    }


def create_app(
    *,
    token_verifier: TokenVerifier | None = None,
    policy_routing_groups: Mapping[str, str] | None = None,
    trino_oauth_enforced: bool | None = None,
) -> FastAPI:
    """Build the Gateway callback API; SQL is never executed by this service."""
    verify_token = token_verifier or verify_access_token
    routing_groups = {
        key.strip().lower(): value.strip()
        for key, value in (policy_routing_groups or _configured_routing_groups()).items()
    }
    bootstrap_group = os.getenv("TRINO_OAUTH_BOOTSTRAP_ROUTING_GROUP", "adhoc").strip()
    oauth_enforced = (
        trino_oauth_enforced
        if trino_oauth_enforced is not None
        else os.getenv("TRINO_OAUTH_ENFORCED", "false").strip().lower() == "true"
    )
    app = FastAPI(title="Trino Gateway OIDC routing selector", version="0.3.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/gateway-rules")
    async def gateway_rules(request: Request) -> dict[str, Any]:
        """Validate caller identity and return a Gateway routing group.

        Unauthenticated requests are sent only to the configured bootstrap
        backend so Trino can issue its own OAuth challenge. Trino must be
        configured to require OAUTH2; the selector is not the authenticator.
        """
        try:
            body = await request.json()
        except Exception:
            return _external_response(errors=["Invalid Gateway selector request"])
        if not isinstance(body, Mapping):
            return _external_response(errors=["Invalid Gateway selector request"])
        if not oauth_enforced:
            return _external_response(
                errors=["Trino OAuth enforcement must be enabled before routing is enabled"]
            )

        request_uri = body.get("requestURI")
        if isinstance(request_uri, str) and request_uri.startswith("/oauth2/"):
            # Keep Trino's authorization-code callback on one backend.
            return _external_response(routing_group=bootstrap_group)

        authorization = request.headers.get("authorization", "")
        scheme, separator, credential = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not credential.strip():
            # Permit only the unauthenticated challenge round-trip. The
            # selected Trino coordinator must reject SQL without OAuth.
            return _external_response(routing_group=bootstrap_group)

        try:
            identity = await run_in_threadpool(verify_token, credential.strip())
        except IdentityTokenError:
            return _external_response(errors=["Access token is invalid or lacks required identity claims"])
        except Exception:
            # Avoid turning an IdP/JWKS outage into a successful default route.
            return _external_response(errors=["Identity validation is temporarily unavailable"])

        catalogs = _query_catalogs(body)
        if catalogs is None:
            return _external_response(errors=["Query catalog analysis is missing or unsuccessful"])

        decision = decide(
            subject=identity.subject,
            location=identity.location,
            catalogs=catalogs,
        )
        if not decision.permit:
            return _external_response(errors=["Request denied by identity-aware routing policy"])

        if decision.cluster_name is None:
            return _external_response(errors=["Policy returned no routing destination"])
        routing_group = routing_groups.get(decision.cluster_name.strip().lower())
        if routing_group is None:
            return _external_response(errors=["Policy destination has no Gateway routing group"])

        return _external_response(routing_group=routing_group)

    return app


app = create_app()
