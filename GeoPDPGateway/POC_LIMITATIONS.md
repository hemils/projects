# Geo-aware Trino Gateway POC: scope and limitations

## What is implemented

This local-only proof of concept separates policy evaluation from the Gateway-facing REST adapter:

- `pdp/` contains hard-coded catalog policy metadata and a generic Python evaluator with no web-framework dependency.
- `trinoGateway/` contains the FastAPI `/route` endpoint that accepts Trino Gateway's external-routing request and returns its routing response shape.
- The fixed POC subject is `poc-user` by default (`POC_USER` can override it). The location is set server-side with `POC_LOCATION`; use `US` or `UK` to exercise the two agreed cases. Client headers are not used as identity or location claims.
- `trades_raw` is permitted only when the configured location is `US`, and routes to `georestricted`.
- `tpch` is permitted for any non-empty configured location, and routes to `adhoc` (the base cluster).
- Missing/unparsed catalog information, unknown catalogs, multiple catalogs in a query, missing location, and a non-US `trades_raw` request produce a non-empty `errors` array and no routing group. With the Gateway's `propagateErrors: true`, this is intended to fail the request rather than select a fallback group.

The POC uses an environment setting for the location so a developer can switch test scenarios. That setting represents trusted context only for local testing; it is not a method for deriving a real user's location.

## Local run and integration boundary

See the [trinoGateway run guide](trinoGateway/README.md) for dependency installation, the Uvicorn command, and sample API requests. Running the API locally does not make it reachable from the Kubernetes Gateway.

The catalog rules are stored in `pdp.policy.CATALOG_POLICIES` as metadata: each catalog has an allowed-location set (or `None` for any configured region) and a Gateway routing group. `decide()` evaluates that metadata generically; adding a catalog rule does not require adding a catalog-specific branch.

The API expects Gateway request analysis to be enabled so that `trinoQueryProperties.catalogs` (or `defaultCatalog`) is included. The current Helm values enable analysis, but leave `routingRules.rulesEngineEnabled` false. The Python service is not deployed into Kubernetes, so the Gateway pod cannot call this local process using the placeholder `routing-api.default.svc.cluster.local` address. Connecting the running Gateway requires a reachable service endpoint, enabling external rules, and validating the pinned Gateway version's error propagation with an end-to-end deny test.

## Security and functional limitations

1. **No authentication.** `poc-user` is a server-side constant, not an authenticated identity. OAuth, token verification, user-to-location claims, and spoof-resistant network location are out of scope.
2. **No production-grade location derivation.** `POC_LOCATION` is configured by the operator and applies to every request handled by that process. It cannot safely represent multiple consumers concurrently.
3. **Routing is not authorization.** Returning `georestricted` or `adhoc` selects a Trino cluster; it does not grant/revoke catalog privileges. This POC does not add Trino access-control rules, prevent direct coordinator access, or validate permissions inside Trino. Do not use it to protect real confidential data.
4. **Single-catalog constraint.** Queries that reference more than one catalog are denied. Gateway's SQL analysis is syntactic and may not resolve all resources (for example, objects accessed through views); Trino-side authorization is needed for complete enforcement.
5. **No physical residency guarantee.** Both clusters currently run in the local Kubernetes environment and the repository documents shared metastore/database and storage credentials/locations. A `georestricted` routing-group name does not establish a cloud region or data residency boundary.
6. **No distributed PDP yet.** `pdp/` is a separate in-repository Python module invoked by the REST adapter in-process, not an independently deployed PDP service. Policy is hard-coded for this milestone, with a function boundary intended for a future Rego/OPA integration.
7. **Gateway denial behavior must be verified.** The adapter uses the Gateway external-selector response's `errors` field for deny decisions. Keep `propagateErrors: true`, disable unsafe fallback behavior, and test deny, PDP/network failure, malformed analysis, and unknown catalog against the exact deployed Gateway version before relying on this flow.

## POC is not a security control

The implementation is for demonstrating and testing the policy-to-routing flow only. Do not connect it to production credentials or treat a successful route as an authorization grant. Before handling protected data, add authenticated identity and location claims, enforce policy in Trino or another trusted authorization layer, isolate regional data and credentials, secure the service-to-service connection, and perform end-to-end security testing.
