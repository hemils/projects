# Geo-aware Trino Gateway POC

## Purpose

This project demonstrates geo-restriction policy evaluation and routing through Trino Gateway. The external selector validates an OIDC bearer token, reads a POC country supplied by the client, analyzes the query catalog, and returns a Gateway routing group. The selector does not execute SQL.

For this POC, cluster identifiers such as `georestricted` and `unrestricted` represent logical destinations. They demonstrate policy-directed routing; they do not prove that the corresponding clusters or data are physically located in those regions.

## POC behavior

- The selector verifies token signature, issuer, audience, and expiry against the configured OIDC provider's JWKS endpoint. It uses the token `sub` for identity and accepts `X-Poc-User-Country` as the location input so users can simulate changing countries (for example, send `US` before travel and `GB` after travel).
- `X-Poc-User-Country` is user-controlled and spoofable. It is only a policy test input; it does not measure or prove current location and must never be treated as authorization evidence in production.
- `trades_raw` selects the `georestricted` Gateway routing group only for `US`; `tpch` selects `unrestricted` for configured locations.
- Missing credentials route only to a bootstrap backend so Trino can issue an OAuth challenge. Invalid tokens and policy denials are returned as Gateway selector errors.
- The FastAPI selector is not itself a Trino authenticator. The currently checked-in Trino values still have HTTP enabled and authentication unset, so Trino-side OAUTH2/TLS setup remains required before user-authenticated execution is demonstrated.
- The supplied country is test input, not a verified measurement of live physical location. Production enforcement needs a trusted ingress that strips client values, derives country from the observed source IP using a maintained GeoIP source, and forwards a protected country header to the selector. IP geolocation identifies network egress and can be affected by VPNs/proxies.
- Gateway routing is not an authorization boundary. Direct coordinator access and selector transport-failure fallback must be addressed, and authorization must also be enforced by Trino.
- Catalog policy metadata returns the Gateway routing-group name directly; the selector has no duplicate routing-map setting. OIDC values are provider-neutral.
- The policy metadata, OIDC settings, and local API deployment are described in the [trinoGateway guide](trinoGateway/README.md).

## Applying this model to a deployment

The logical destinations can be connected to Kubernetes clusters on a cloud platform selected to meet business, residency, and operational requirements. In such a deployment, configure each destination's Gateway backend to point to the appropriate cluster and region. The policy-to-destination flow remains the same while the infrastructure determines where the workloads and data are hosted.

This repository is a proof of concept for demonstrating that flow; its configured cluster names and local setup are illustrative rather than a statement of physical data residency.
