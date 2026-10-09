"""FastAPI query API that applies policy and executes through Trino clusters."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx
import sqlglot
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlglot import exp
from sqlglot.errors import ParseError

from pdp import decide


class QueryRequest(BaseModel):
    """SQL submitted for policy evaluation and execution."""

    model_config = ConfigDict(extra="forbid")

    query: str


class QueryResponse(BaseModel):
    """Selected cluster and fully fetched query result."""

    cluster: str
    routing_group: str
    columns: list[str]
    data: list[list[Any]]


DEFAULT_CLUSTER_BACKEND_NAMES = {
    "unrestricted": "unrestricted",
    "georestricted": "georestricted",
}


def _configured_location() -> str | None:
    value = os.getenv("POC_LOCATION", "").strip()
    return value.upper() or None


def _configured_cluster_backend_names() -> dict[str, str]:
    value = os.getenv("TRINO_CLUSTER_BACKEND_NAMES", "").strip()
    if not value:
        return DEFAULT_CLUSTER_BACKEND_NAMES.copy()
    try:
        configured = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("TRINO_CLUSTER_BACKEND_NAMES must be a JSON object") from exc
    if not isinstance(configured, dict) or not all(
        isinstance(key, str) and isinstance(name, str)
        for key, name in configured.items()
    ):
        raise ValueError("TRINO_CLUSTER_BACKEND_NAMES must map strings to strings")
    return {key.strip().lower(): name.strip() for key, name in configured.items()}


def _catalogs_in_query(query: str) -> set[str]:
    if not query.strip():
        raise HTTPException(status_code=400, detail="SQL query must not be empty")
    try:
        statements = sqlglot.parse(query, read="trino")
    except ParseError as exc:
        raise HTTPException(status_code=400, detail="SQL query could not be parsed") from exc
    if len(statements) != 1 or statements[0] is None:
        raise HTTPException(status_code=400, detail="Exactly one SQL statement is required")

    catalogs = {
        table.catalog.strip().lower()
        for table in statements[0].find_all(exp.Table)
        if table.catalog and table.catalog.strip()
    }
    if not catalogs:
        raise HTTPException(
            status_code=400,
            detail="Query must reference a catalog-qualified table (catalog.schema.table)",
        )
    return catalogs


def create_app(
    *,
    poc_user: str | None = None,
    poc_location: str | None = None,
    gateway_api_url: str | None = None,
    cluster_backend_names: Mapping[str, str] | None = None,
    trino_password: str | None = None,
) -> FastAPI:
    """Build the query API with server-configured policy and connection context.

    Policy cluster names are mapped to backend names registered in Trino Gateway.
    The Gateway management API supplies each backend's routing group and
    coordinator URL. Configure the API base URL with ``TRINO_GATEWAY_API_URL``.
    """
    fixed_user = poc_user if poc_user is not None else os.getenv("POC_USER", "poc-user")
    fixed_location = poc_location if poc_location is not None else _configured_location()
    fixed_password = (
        trino_password if trino_password is not None else os.getenv("TRINO_PASSWORD")
    )
    backend_names = {
        key.strip().lower(): value.strip()
        for key, value in (cluster_backend_names or _configured_cluster_backend_names()).items()
    }
    gateway_url = (
        gateway_api_url or os.getenv("TRINO_GATEWAY_API_URL", "http://localhost:9093")
    ).rstrip("/")
    app = FastAPI(title="Trino Gateway POC query API", version="0.2.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/route", response_model=QueryResponse)
    def route(request: QueryRequest) -> QueryResponse:
        """Resolve the catalog's policy cluster and execute SQL against it."""
        catalogs = _catalogs_in_query(request.query)
        decision = decide(
            subject=fixed_user,
            location=fixed_location,
            catalogs=catalogs,
        )
        if not decision.permit:
            raise HTTPException(status_code=403, detail=decision.reason)

        cluster_name = decision.cluster_name
        if cluster_name is None:
            raise HTTPException(status_code=500, detail="Policy allowed query without a cluster")
        backend_name = backend_names.get(cluster_name.strip().lower())
        if backend_name is None:
            raise HTTPException(
                status_code=502,
                detail=f"No Trino Gateway backend is configured for policy cluster {cluster_name}",
            )

        try:
            inventory_response = httpx.get(
                f"{gateway_url}/gateway/backend/all",
                timeout=10.0,
            )
            inventory_response.raise_for_status()
            inventory = inventory_response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(
                status_code=502,
                detail="Unable to retrieve Trino Gateway backend inventory",
            ) from exc

        if not isinstance(inventory, list):
            raise HTTPException(status_code=502, detail="Invalid Trino Gateway backend inventory")
        backend = next(
            (
                entry
                for entry in inventory
                if isinstance(entry, dict)
                and str(entry.get("name", "")).strip().lower() == backend_name.lower()
                and entry.get("active") is True
            ),
            None,
        )
        if backend is None:
            raise HTTPException(
                status_code=502,
                detail=f"No active Trino Gateway backend named {backend_name}",
            )

        coordinator_url = backend.get("proxyTo")
        routing_group = backend.get("routingGroup")
        if not isinstance(coordinator_url, str) or not isinstance(routing_group, str):
            raise HTTPException(status_code=502, detail="Gateway backend is missing its URL or routing group")
        try:
            parsed_url = urlsplit(coordinator_url)
            port = parsed_url.port
        except ValueError as exc:
            raise HTTPException(status_code=502, detail="Gateway backend has an invalid coordinator URL") from exc
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise HTTPException(status_code=502, detail="Gateway backend has an invalid coordinator URL")

        try:
            from trino.auth import BasicAuthentication
            from trino.dbapi import connect

            connection_options: dict[str, Any] = {
                "host": parsed_url.hostname,
                "port": port or (443 if parsed_url.scheme == "https" else 80),
                "user": fixed_user,
                "http_scheme": parsed_url.scheme,
                "catalog": next(iter(catalogs)),
            }
            if fixed_password:
                connection_options["auth"] = BasicAuthentication(fixed_user, fixed_password)
            connection = connect(**connection_options)
            try:
                cursor = connection.cursor()
                try:
                    cursor.execute(request.query)
                    columns = [column[0] for column in (cursor.description or [])]
                    rows = cursor.fetchall()
                finally:
                    cursor.close()
            finally:
                connection.close()
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail="Query execution on the selected cluster failed",
            ) from exc

        return QueryResponse(
            cluster=cluster_name,
            routing_group=routing_group,
            columns=columns,
            data=rows,
        )

    return app


app = create_app()
