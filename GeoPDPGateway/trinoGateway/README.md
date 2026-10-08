# Run the local Trino Gateway POC API

The FastAPI adapter lives in `trinoGateway.app`. Run the commands below from the repository root so the Python import for the sibling `pdp` package resolves.

## Install dependencies

```sh
python -m pip install -r requirements.txt
```

## Start the API

Set the fixed, server-side POC location when starting Uvicorn. The supported demo cases are `US` and `UK`; the value applies to every request handled by this process.

```sh
POC_USER=poc-user POC_LOCATION=US uvicorn trinoGateway.app:app --host 0.0.0.0 --port 8080
```

To exercise the UK policy case, stop the server and start it again with `POC_LOCATION=UK`. If `POC_USER` is omitted, it defaults to `poc-user`. Do not supply user/location values through consumer request headers; the API intentionally ignores those as trusted claims.

## Call the API

Check readiness:

```sh
curl -sS http://localhost:8080/health
```

Exercise a catalog decision directly:

```sh
curl -sS -X POST http://localhost:8080/route \
  -H 'Content-Type: application/json' \
  -d '{"trinoQueryProperties":{"catalogs":["trades_raw"]}}'
```

With `POC_LOCATION=US`, this returns a Gateway routing response with `routingGroup` set to `georestricted`. With `POC_LOCATION=UK`, it returns an empty `routingGroup` and a non-empty `errors` array. The `tpch` catalog is allowed for any configured non-empty location and routes to `adhoc`:

```sh
curl -sS -X POST http://localhost:8080/route \
  -H 'Content-Type: application/json' \
  -d '{"trinoQueryProperties":{"catalogs":["tpch"]}}'
```

This direct API call checks the routing decision contract; it does not submit SQL to Trino. Run automated tests from the repository root with `python -m pytest`.

## Current integration boundary

This API is currently run locally and is not deployed as a Kubernetes service. The Gateway Helm values still have external routing disabled and point at a placeholder in-cluster service URL. Therefore, starting Uvicorn alone does not connect the Kubernetes Gateway to this API. See [POC limitations](../POC_LIMITATIONS.md) before treating any decision as an authorization control.
