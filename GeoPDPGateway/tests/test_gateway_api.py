from typing import Any

from fastapi.testclient import TestClient

from pdp.identity import AuthenticatedIdentity, IdentityTokenError
from trinoGateway.app import create_app


def make_app(**kwargs: Any):
    kwargs.setdefault("trino_oauth_enforced", True)
    return create_app(**kwargs)


def gateway_request(catalogs: list[str], *, parsed: bool = True) -> dict[str, Any]:
    return {
        "trinoQueryProperties": {
            "catalogs": catalogs,
            "isQueryParsingSuccessful": parsed,
        },
        "requestURI": "/v1/statement",
        "method": "POST",
    }


def test_verified_us_identity_routes_restricted_catalog_to_georestricted() -> None:
    seen_tokens: list[str] = []

    def verify(token: str) -> AuthenticatedIdentity:
        seen_tokens.append(token)
        return AuthenticatedIdentity(subject="entra-user-object-id")

    client = TestClient(make_app(token_verifier=verify))
    response = client.post(
        "/gateway-rules",
        json=gateway_request(["trades_raw"]),
        headers={"Authorization": "Bearer signed-access-token", "X-Poc-User-Country": "US"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "routingGroup": "georestricted",
        "errors": [],
        "externalHeaders": {},
    }
    assert seen_tokens == ["signed-access-token"]


def test_verified_uk_identity_is_denied_for_restricted_catalog() -> None:
    client = TestClient(
        make_app(
            token_verifier=lambda _: AuthenticatedIdentity(
                subject="entra-user-object-id"
            )
        )
    )

    response = client.post(
        "/gateway-rules",
        json=gateway_request(["trades_raw"]),
        headers={"Authorization": "Bearer token", "X-Poc-User-Country": "GB"},
    )

    assert response.status_code == 200
    assert response.json()["routingGroup"] is None
    assert response.json()["errors"] == [
        "Request denied by identity-aware routing policy"
    ]


def test_uk_identity_routes_unrestricted_catalog_to_unrestricted_group() -> None:
    client = TestClient(
        make_app(
            token_verifier=lambda _: AuthenticatedIdentity(
                subject="entra-user-object-id"
            )
        )
    )

    response = client.post(
        "/gateway-rules",
        json=gateway_request(["tpch"]),
        headers={"Authorization": "Bearer token", "X-Poc-User-Country": "GB"},
    )

    assert response.status_code == 200
    assert response.json()["routingGroup"] == "unrestricted"
    assert response.json()["errors"] == []


def test_missing_bearer_token_only_selects_authentication_bootstrap_backend() -> None:
    def unexpected_verification(_: str) -> AuthenticatedIdentity:
        raise AssertionError("the selector must not trust or invent an identity")

    client = TestClient(make_app(token_verifier=unexpected_verification))

    response = client.post("/gateway-rules", json=gateway_request(["trades_raw"]))

    assert response.status_code == 200
    assert response.json()["routingGroup"] == "unrestricted"
    assert response.json()["errors"] == []


def test_invalid_token_returns_gateway_error_instead_of_default_route() -> None:
    def reject(_: str) -> AuthenticatedIdentity:
        raise IdentityTokenError("bad token")

    client = TestClient(make_app(token_verifier=reject))

    response = client.post(
        "/gateway-rules",
        json=gateway_request(["tpch"]),
        headers={"Authorization": "Bearer invalid"},
    )

    assert response.json()["routingGroup"] is None
    assert response.json()["errors"] == [
        "Access token is invalid or lacks required identity claims"
    ]


def test_identity_provider_failure_returns_gateway_error() -> None:
    def unavailable(_: str) -> AuthenticatedIdentity:
        raise RuntimeError("JWKS unavailable")

    client = TestClient(make_app(token_verifier=unavailable))

    response = client.post(
        "/gateway-rules",
        json=gateway_request(["tpch"]),
        headers={"Authorization": "Bearer token"},
    )

    assert response.json()["routingGroup"] is None
    assert response.json()["errors"] == [
        "Identity validation is temporarily unavailable"
    ]


def test_poc_country_header_drives_policy() -> None:
    client = TestClient(
        make_app(
            token_verifier=lambda _: AuthenticatedIdentity(
                subject="verified-user"
            )
        )
    )

    response = client.post(
        "/gateway-rules",
        json=gateway_request(["trades_raw"]),
        headers={
            "Authorization": "Bearer token",
            "X-Poc-User-Country": "GB",
            "X-Trino-User": "spoofed-user",
            "X-User-Location": "US",
        },
    )

    assert response.json()["routingGroup"] is None
    assert response.json()["errors"] == [
        "Request denied by identity-aware routing policy"
    ]


def test_authenticated_query_is_denied_without_poc_country() -> None:
    client = TestClient(
        make_app(token_verifier=lambda _: AuthenticatedIdentity(subject="verified-user"))
    )

    response = client.post(
        "/gateway-rules",
        json=gateway_request(["tpch"]),
        headers={"Authorization": "Bearer token"},
    )

    assert response.json()["routingGroup"] is None
    assert response.json()["errors"] == [
        "POC country header is missing or invalid"
    ]


def test_multiple_catalogs_and_unparsed_queries_are_denied() -> None:
    client = TestClient(
        make_app(
            token_verifier=lambda _: AuthenticatedIdentity(
                subject="verified-user"
            )
        )
    )
    headers = {"Authorization": "Bearer token", "X-Poc-User-Country": "US"}

    multiple = client.post(
        "/gateway-rules",
        json=gateway_request(["tpch", "trades_raw"]),
        headers=headers,
    )
    unparsable = client.post(
        "/gateway-rules",
        json=gateway_request(["tpch"], parsed=False),
        headers=headers,
    )

    assert multiple.json()["errors"] == [
        "Request denied by identity-aware routing policy"
    ]
    assert unparsable.json()["errors"] == [
        "Query catalog analysis is missing or unsuccessful"
    ]


def test_oauth_callback_uses_bootstrap_group() -> None:
    client = TestClient(make_app())

    response = client.post(
        "/gateway-rules",
        json={"requestURI": "/oauth2/callback"},
        headers={"Authorization": "Bearer token"},
    )

    assert response.json()["routingGroup"] == "unrestricted"
    assert response.json()["errors"] == []


def test_legacy_sql_execution_endpoint_is_not_exposed() -> None:
    client = TestClient(create_app())

    response = client.post("/route", json={"query": "select * from tpch.sf1.customer"})

    assert response.status_code == 404


def test_routing_is_closed_until_trino_oauth_is_explicitly_enabled() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/gateway-rules",
        json=gateway_request(["tpch"]),
        headers={"Authorization": "Bearer token"},
    )

    assert response.json()["routingGroup"] is None
    assert response.json()["errors"] == [
        "Trino OAuth enforcement must be enabled before routing is enabled"
    ]
