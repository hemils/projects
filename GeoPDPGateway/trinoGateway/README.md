# Run the Trino Gateway POC query API

The FastAPI application lives in `trinoGateway.app`. It accepts SQL, extracts
catalogs from table references, asks the policy layer for a cluster, resolves
that cluster to an active Trino Gateway backend, then connects to the backend's
`proxyTo` coordinator URL with the Trino Python client. Run commands from the
repository root so the sibling `pdp` package resolves.

## Install dependencies

```sh
python -m pip install -r requirements.txt
```

## Start the API

Set the fixed, server-side POC location and the Trino Gateway management API
URL when starting Uvicorn. The documented port-forward maps Gateway to
`localhost:9093`; the default `TRINO_GATEWAY_API_URL` uses this URL. The API
process also needs network access to the coordinator URLs returned by the
Gateway backend inventory.

```sh
POC_USER=poc-user POC_LOCATION=US TRINO_GATEWAY_API_URL=http://localhost:9093 uvicorn trinoGateway.app:app --host 0.0.0.0 --port 8080
```

To exercise the UK policy case, restart with `POC_LOCATION=UK`. `POC_USER`
defaults to `poc-user`; set `TRINO_PASSWORD` only when the backend requires
basic authentication. The API uses `POC_USER` as the Trino username and never
accepts user/location claims in the query body.

By default, policy cluster `unrestricted` resolves to Gateway backend `base`,
and `georestricted` resolves to backend `georestricted`. Override the backend
names with `TRINO_CLUSTER_BACKEND_NAMES`, a JSON object such as
`{"unrestricted":"unrestricted","georestricted":"georestricted"}` if
those are the names registered with Gateway.

## Call the API

Check readiness:

```sh
curl -sS http://localhost:8080/health
```

Submit a query and return its columns and rows:

```sh
curl -sS -X POST http://localhost:8080/route \
  -H 'Content-Type: application/json' \
  -d '{"query":"select * from tpch.sf1.customer"}'
```

The response includes the policy cluster, the Gateway backend's routing group,
column names, and fetched rows. `tpch` selects policy cluster `unrestricted`
(mapped to backend `base` and its configured `adhoc` routing group). `trades_raw`
selects `georestricted` and is allowed only when `POC_LOCATION=US`:

```sh
curl -sS -X POST http://localhost:8080/route \
  -H 'Content-Type: application/json' \
  -d '{"query":"select * from trades_raw.market.trades"}'
```

Unknown catalogs, mixed-catalog queries, and policy denials are rejected.
Queries need catalog-qualified table references. The API currently fetches all
result rows into memory before returning the response, so it is intended for
POC-sized results. Run automated tests from the repository root with
`python -m pytest`.

## Gateway integration boundary

`/route` is now a client SQL-execution endpoint, not Trino Gateway's external
selector callback. Keep `routingRules.rulesEngineEnabled` disabled unless a
separate selector endpoint is implemented. This service must reach both the
Gateway management API and the selected coordinator URLs. See [POC
limitations](../POC_LIMITATIONS.md) before treating routing as authorization.
