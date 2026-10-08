"""FastAPI endpoint implementing Trino Gateway's external routing contract."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from pdp import decide


class TrinoQueryProperties(BaseModel):
    """Analyzed request properties posted by Trino Gateway."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    catalogs: list[str] = Field(default_factory=list)
    default_catalog: str | None = Field(default=None, alias="defaultCatalog")
    error_message: str | None = Field(default=None, alias="errorMessage")


class GatewayRoutingRequest(BaseModel):
    """Subset of Gateway's external selector request needed by this POC."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    trino_query_properties: TrinoQueryProperties | None = Field(
        default=None, alias="trinoQueryProperties"
    )
    headers: dict[str, Any] = Field(default_factory=dict)


class GatewayRoutingResponse(BaseModel):
    """Response schema expected by Trino Gateway's external selector."""

    model_config = ConfigDict(populate_by_name=True)

    routing_group: str | None = Field(default=None, alias="routingGroup")
    errors: list[str] = Field(default_factory=list)
    external_headers: dict[str, str] = Field(default_factory=dict, alias="externalHeaders")


def _configured_location() -> str | None:
    value = os.getenv("POC_LOCATION", "").strip()
    return value.upper() or None


def create_app(*, poc_user: str | None = None, poc_location: str | None = None) -> FastAPI:
    """Build the API with fixed, server-side POC identity and location values.

    If arguments are omitted, identity/location are read from ``POC_USER`` and
    ``POC_LOCATION``. Incoming request headers are deliberately not used as
    identity or location claims.
    """

    fixed_user = poc_user if poc_user is not None else os.getenv("POC_USER", "poc-user")
    fixed_location = poc_location if poc_location is not None else _configured_location()
    app = FastAPI(title="Trino Gateway POC routing adapter", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/route", response_model=GatewayRoutingResponse, response_model_by_alias=True)
    def route(request: GatewayRoutingRequest) -> GatewayRoutingResponse:
        properties = request.trino_query_properties
        if properties is None or properties.error_message:
            reason = "Gateway did not provide successfully analyzed catalog properties"
            return GatewayRoutingResponse(errors=[reason])

        catalogs = {catalog for catalog in properties.catalogs if catalog.strip()}
        if not catalogs and properties.default_catalog:
            catalogs.add(properties.default_catalog)

        # Static server-side context is intentional for this POC. Do not trust
        # X-Trino-User, location headers, or X-Trino-Routing-Group from clients.
        decision = decide(subject=fixed_user, location=fixed_location, catalogs=catalogs)
        if not decision.permit:
            return GatewayRoutingResponse(errors=[decision.reason])

        return GatewayRoutingResponse(routing_group=decision.routing_group)

    return app


app = create_app()
