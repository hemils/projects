# Geo-aware Trino Gateway POC

## Purpose

This project demonstrates geo-restriction policy evaluation and routing through Trino Gateway. The external selector validates an OIDC bearer token, reads a configured location claim, analyzes the query catalog, and returns a Gateway routing group. The selector does not execute SQL.

For this POC, cluster identifiers such as `georestricted` and `unrestricted` represent logical destinations. They demonstrate policy-directed routing; they do not prove that the corresponding clusters or data are physically located in those regions.

## POC behavior

- The selector verifies token signature, issuer, audience, and expiry against the configured Microsoft Entra ID JWKS endpoint. It uses the token `sub` and configured `geo_location` claim; it does not trust user/location request headers.
- `trades_raw` selects the `georestricted` Gateway routing group only for `US`; `tpch` selects `adhoc` for configured locations.
- Missing credentials route only to a bootstrap backend so Trino can issue an OAuth challenge. Invalid tokens and policy denials are returned as Gateway selector errors.
- The FastAPI selector is not itself a Trino authenticator. The currently checked-in Trino values still have HTTP enabled and authentication unset, so Trino-side OAUTH2/TLS setup remains required before user-authenticated execution is demonstrated.
- A token location claim is test input for this POC, not a verified measurement of a user's live physical location. Real geolocation needs a trusted edge and a separately assessed location source.
- Gateway routing is not an authorization boundary. Direct coordinator access and selector transport-failure fallback must be addressed, and authorization must also be enforced by Trino.
- The policy metadata, Entra settings, and local API deployment are described in the [trinoGateway guide](trinoGateway/README.md).

## Applying this model to a deployment

The logical destinations can be connected to Kubernetes clusters on a cloud platform selected to meet business, residency, and operational requirements. In such a deployment, configure each destination's Gateway backend to point to the appropriate cluster and region. The policy-to-destination flow remains the same while the infrastructure determines where the workloads and data are hosted.

This repository is a proof of concept for demonstrating that flow; its configured cluster names and local setup are illustrative rather than a statement of physical data residency.
