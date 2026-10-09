from typing import Any

import httpx
from fastapi.testclient import TestClient

from trinoGateway import app as gateway_app
from trinoGateway.app import create_app


class FakeCursor:
    description = [("customer_id",), ("name",)]

    def execute(self, query: str) -> None:
        self.query = query

    def fetchall(self) -> list[list[Any]]:
        return [[1, "Ada"]]

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self) -> None:
        self.fake_cursor = FakeCursor()

    def cursor(self) -> FakeCursor:
        return self.fake_cursor

    def close(self) -> None:
        pass


def install_trino_mocks(monkeypatch: Any) -> dict[str, Any]:
    fake_connection = FakeConnection()
    connect_arguments: dict[str, Any] = {}

    def connect(**kwargs: Any) -> FakeConnection:
        connect_arguments.update(kwargs)
        return fake_connection

    monkeypatch.setattr("trino.dbapi.connect", connect)
    return {"connection": fake_connection, "connect_arguments": connect_arguments}


def install_gateway_inventory_mock(monkeypatch: Any, *, routing_group: str) -> None:
    response = httpx.Response(
        200,
        request=httpx.Request("GET", "http://gateway/gateway/backend/all"),
        json=[
            {
                "name": "georestricted",
                "proxyTo": "http://restricted-coordinator:8080",
                "active": True,
                "routingGroup": routing_group,
            },
            {
                "name": "base",
                "proxyTo": "http://base-coordinator:8080",
                "active": True,
                "routingGroup": "adhoc",
            },
        ],
    )
    monkeypatch.setattr(gateway_app.httpx, "get", lambda *args, **kwargs: response)


def test_query_catalog_routes_through_resolved_georestricted_backend(monkeypatch: Any) -> None:
    trino_mocks = install_trino_mocks(monkeypatch)
    install_gateway_inventory_mock(monkeypatch, routing_group="geo-group")
    client = TestClient(create_app(poc_user="poc-user", poc_location="US"))

    response = client.post("/route", json={"query": "select * from trades_raw.market.trades"})

    assert response.status_code == 200
    assert response.json() == {
        "cluster": "georestricted",
        "routing_group": "geo-group",
        "columns": ["customer_id", "name"],
        "data": [[1, "Ada"]],
    }
    assert trino_mocks["connect_arguments"] == {
        "host": "restricted-coordinator",
        "port": 8080,
        "user": "poc-user",
        "http_scheme": "http",
        "catalog": "trades_raw",
    }


def test_query_catalog_routes_tpch_to_unrestricted_backend(monkeypatch: Any) -> None:
    install_trino_mocks(monkeypatch)
    install_gateway_inventory_mock(monkeypatch, routing_group="adhoc")
    client = TestClient(create_app(poc_user="poc-user", poc_location="UK"))

    response = client.post("/route", json={"query": "select * from tpch.sf1.customer"})

    assert response.status_code == 200
    assert response.json()["cluster"] == "unrestricted"
    assert response.json()["routing_group"] == "adhoc"


def test_trades_raw_is_denied_from_uk_before_backend_lookup(monkeypatch: Any) -> None:
    def unexpected_lookup(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("policy denial must happen before backend lookup")

    monkeypatch.setattr(gateway_app.httpx, "get", unexpected_lookup)
    client = TestClient(create_app(poc_user="poc-user", poc_location="UK"))

    response = client.post("/route", json={"query": "select * from trades_raw.market.trades"})

    assert response.status_code == 403


def test_query_without_catalog_qualified_table_is_rejected() -> None:
    client = TestClient(create_app(poc_user="poc-user", poc_location="US"))

    response = client.post("/route", json={"query": "select 1"})

    assert response.status_code == 400


def test_query_referencing_multiple_catalogs_is_denied() -> None:
    client = TestClient(create_app(poc_user="poc-user", poc_location="US"))

    response = client.post(
        "/route",
        json={
            "query": "select * from tpch.sf1.customer join trades_raw.market.trades on true"
        },
    )

    assert response.status_code == 403


def test_empty_query_is_rejected() -> None:
    client = TestClient(create_app(poc_user="poc-user", poc_location="US"))

    response = client.post("/route", json={"query": "  "})

    assert response.status_code == 400
