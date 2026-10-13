# Experimentation

Two experiments measure the identity-aware, location-based routing policy. Both
run through Trino Gateway with an Entra bearer token acquired in-process.

| Experiment | Question | Script |
|---|---|---|
| A | Does the policy allow and deny correctly per country and catalog? | [scripts/experiment_a.py](scripts/experiment_a.py) |
| C | What latency does the path add, and how much is token acquisition? | [scripts/experiment_c.py](scripts/experiment_c.py) |

Shared code (MSAL token acquisition, Trino query runner) is in
[scripts/bench_common.py](scripts/bench_common.py).

## Policy under test

Defined in [pdp/policy.py](pdp/policy.py):

| Catalog | Allowed countries | Routing group |
|---|---|---|
| `tpch` | any non-empty country | `unrestricted` |
| `trades_raw` | `US` | `georestricted` |

- An empty or missing country is denied for every catalog (fail closed).
- A query touching several catalogs is allowed only if every catalog is permitted
  and all share one routing group. `tpch` + `trades_raw` is therefore denied.
- The country is supplied by the client through `X-Poc-User-Country`. It is
  spoofable and simulates location only (see [POC_LIMITATIONS.md](POC_LIMITATIONS.md)).

## Experiment A: policy correctness

- **Matrix:** countries `US, GB, DE, IN` and none, against `tpch` and `trades_raw`.
- **Query:** plain `SELECT ... LIMIT 5` per catalog.
- **Repetitions:** `--runs` per cell (default 30).
- **Expected result:** `tpch` allowed for any country, `trades_raw` allowed only
  for `US`, everything denied when no country is sent.
- **Metrics:** accuracy, false-allow count (should be 0), false-deny count, error count.

Outputs in `results/`:
- `experiment_a.csv`: country, catalog, expected, observed, seconds, detail.
- `experiment_a_heatmap.png`: fraction allowed per country and catalog.

## Experiment C: latency and auth overhead

- **Query:** `SELECT * FROM tpch.sf1.customer LIMIT 5`, sent with `--country` (default `US`).
- **Paths:** each `--target label=host:port` is one path, for example direct to
  Trino, Gateway without the selector, and Gateway with the selector.
- **Method:** `--warmup` discarded runs (default 10), then `--runs` measured runs
  (default 200). Each query is timed from request to the last fetched row.
- **Auth overhead:** token acquisition is timed separately, as `cache` (MSAL cache
  hit, `--runs` samples) and `refresh` (forced network refresh, up to 30 samples).
  The interactive sign-in is not timed because it includes user interaction.
- **Metrics:** p50, p95, p99 per path; median and p95 of token acquisition.

Outputs in `results/`:
- `experiment_c.csv`: path, outcome, seconds, detail.
- `experiment_c_auth.csv`: mode, seconds.
- `experiment_c_latency.png`: box plot and CDF per path.
- `experiment_c_overhead.png`: median query latency plus token cost per path.

## Prerequisites

1. Both Trino clusters, the selector and Gateway are deployed
   ([trinoGateway/README.md](trinoGateway/README.md), steps 1 to 7) with
   `TRINO_OAUTH_ENFORCED: "true"`.
2. Install dependencies from the repository root:
   ```sh
   python -m pip install -r requirements.txt
   ```
3. Port-forward the services you will measure, each in its own terminal:
   ```sh
   kubectl port-forward -n default svc/trino-gateway 9093:8080
   ```
   For a direct-to-Trino path, also forward that coordinator (use any free local port).
4. Set the Entra values:
   ```sh
   export ENTRA_TENANT_ID=<tenant id>
   export ENTRA_APP_CLIENT_ID=<application (client) id>
   export TRINO_HTTP_SCHEME=http
   ```
   Optional: `TRINO_USER` overrides the principal (default is the signed-in UPN);
   `ENTRA_CLIENT_ID` overrides the public client (default is the Azure CLI client
   `04b07795-8ddb-461a-bbee-02f9e1bf7b46`, which must be an authorized client app).

A browser window opens once per script run for the Entra sign-in.

## Running

```sh
# Experiment A
python scripts/experiment_a.py --gateway gateway=localhost:9093 --runs 30

# Experiment C
python scripts/experiment_c.py \
  --target direct=localhost:<direct port> \
  --target gateway=localhost:9093 \
  --runs 200 --warmup 10
```

Use `--out` to change the output prefix (defaults `results/experiment_a` and
`results/experiment_c`).

## Interpreting and reporting

- A denial is recognised by the text "denied by identity-aware routing policy" in
  the client error. Any other failure is recorded as `error`; inspect the `detail`
  column and fix the setup before using the numbers.
- Report the environment with the results: cluster type (kind), Trino and Gateway
  versions, CPU and RAM, and data size.
- Client, Gateway and Trino run on one machine, so absolute latencies are lower
  than a real network deployment. Compare paths relatively.
- Gateway without the selector needs a second Gateway instance or a temporary
  configuration with the selector disabled; it is not set up by these scripts.


Experiment. A

- User location is US
- common catalog like tpch is allowed
- But restricted catalog are permissible or allowed to access only if allowed by jurisdiction i.e US
- Policy fails for non US country as user is not in that location.

"GB": "poc-user_gb@<tenant-domain>",#Luda830846
    "DE": "poc-user_de@<tenant-domain>",#P1q2r3s4t5