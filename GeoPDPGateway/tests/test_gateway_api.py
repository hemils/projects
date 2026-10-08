from fastapi.testclient import TestClient

from trinoGateway.app import create_app


def test_gateway_contract_allows_trades_raw_from_us() -> None:
    client = TestClient(create_app(poc_user="poc-user", poc_location="US"))

    response = client.post(
        "/route",
        json={"trinoQueryProperties": {"catalogs": ["trades_raw"]}},
    )

    assert response.status_code == 200
    assert response.json() == {
        "routingGroup": "georestricted",
        "errors": [],
        "externalHeaders": {},
    }


def test_gateway_contract_denies_trades_raw_from_uk() -> None:
    client = TestClient(create_app(poc_user="poc-user", poc_location="UK"))

    response = client.post(
        "/route",
        json={"trinoQueryProperties": {"catalogs": ["trades_raw"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["routingGroup"] is None
    assert body["errors"]


def test_client_supplied_identity_and_location_headers_are_not_used() -> None:
    client = TestClient(create_app(poc_user="poc-user", poc_location="UK"))

    response = client.post(
        "/route",
        json={
            "headers": {
                "X-Trino-User": ["attacker"],
                "X-User-Location": ["US"],
                "X-Trino-Routing-Group": ["georestricted"],
            },
            "trinoRequestUser": {"user": "attacker"},
            "trinoQueryProperties": {"catalogs": ["trades_raw"]},
        },
    )

    assert response.json()["routingGroup"] is None
    assert response.json()["errors"]


def test_missing_query_analysis_returns_error_in_gateway_schema() -> None:
    client = TestClient(create_app(poc_user="poc-user", poc_location="US"))

    response = client.post("/route", json={})

    assert response.status_code == 200
    assert response.json()["routingGroup"] is None
    assert response.json()["errors"]
