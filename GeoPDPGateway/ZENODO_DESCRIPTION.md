# Zenodo description

## Title

Datasets and measurements for an identity-aware, location-based query routing proof of concept (Trino Gateway, Microsoft Entra ID)

## Description

This record accompanies a proof of concept (POC) in which a Trino Gateway routes SQL queries to one of two Trino clusters (`unrestricted` or `georestricted`) based on the authenticated user (Microsoft Entra ID bearer token) and a policy decision point (PDP) that evaluates the user's country against per-catalog rules. It contains (1) the sample input data queried during the POC and (2) the raw results of two experiments that evaluate the policy and its latency overhead.

**Important caveats**

- The user's country is a client-supplied value (HTTP header `X-Poc-User-Country`) used to *simulate* location. It is spoofable and does not establish where a user really is.
- The sample data was exported from Delta tables in Azure Data Lake Storage Gen2 (`bronze/trades`, `bronze/customer`) and is limited to the first 1000 rows of each table. The customer records appear to be synthetic (example.org e-mail addresses, generated names); they do not describe real people. Confirm this before publishing.
- Latencies were measured on a single local Kubernetes (kind) deployment and are indicative only.

## Policy under test

| Catalog | Allowed countries | Routing group |
|---|---|---|
| `tpch` | any non-empty country | `unrestricted` |
| `trades_raw` | `US`, `UK` | `georestricted` |
| `customer` | `US`, `DE` | `georestricted` |

An empty or missing country is denied for every catalog. A query spanning several catalogs is allowed only if all are permitted and share one routing group. The rules are defined in `pdp/policy.py`. Experiment A used `GB` (not `UK`) as the test country, so `GB` was denied for `trades_raw`.

## Files

### Sample data (`data/`)

Common conventions: UTF-8, comma-separated, one header row, no index column, no missing values.

#### `trades.csv`  (1000 rows, 9 columns)

Equity trades from partition `trade_date=2026-01-02` of the `trades` Delta table. In this sample every row belongs to one customer.

| Column | Type | Description |
|---|---|---|
| `trade_id` | integer | Unique trade identifier (primary key). |
| `customer_id` | integer | Customer that placed the trade; foreign key to `customer.customer_id`. |
| `trade_date` | date (YYYY-MM-DD) | Trade date (partition column); constant `2026-01-02` in this file. |
| `stock` | string | Company name of the traded instrument. |
| `stock_symbol` | string | Ticker symbol of the instrument. |
| `price` | integer | Unit price (currency not specified in the source). |
| `quantity` | integer | Number of units traded. |
| `total_value` | integer | `price * quantity`. |
| `country` | string | Country associated with the trade (full country name, 236 distinct values). Not the same as the simulated user country. |

#### `customer.csv`  (1000 rows, 11 columns)

Customer master data from the `customer` Delta table.

| Column | Type | Description |
|---|---|---|
| `customer_id` | integer | Unique customer identifier (primary key). |
| `first_name` | string | Given name. |
| `last_name` | string | Family name. |
| `email` | string | E-mail address. |
| `phone_number` | string | Free-form phone number (formats vary, may contain extensions). |
| `city` | string | City of residence. |
| `country` | string | Country code or name; 3 distinct values (e.g. `India`, `UK`, `USA`). |
| `age` | integer | Age in years. |
| `sex` | string | `M` or `F`. |
| `status` | string | Account status: `active` or `inactive`. |
| `created_at` | date (YYYY-MM-DD) | Record creation date. |

Join: `trades.customer_id = customer.customer_id`. Because the trades sample covers a single customer, a join of the two samples returns few rows unless that customer is in the customer sample.

### Experiment A: policy correctness (`results/`)

Each of the users `us_user1`, `gb_user1`, `de_user1`, `in_user1` (simulated countries US, GB, DE, IN) ran a `SELECT ... LIMIT 5` against each catalog, 30 repetitions per cell, via Gateway.

#### `experiment_a.csv`  (360 rows)

| Column | Type | Description |
|---|---|---|
| `user` | string | Test principal. |
| `country` | string | Simulated country sent in `X-Poc-User-Country` (`US`, `GB`, `DE`, `IN`). |
| `catalog` | string | Catalog queried (`tpch`, `trades_raw`, `customer`). |
| `expected` | string | Outcome the policy should produce: `allow` or `deny`. |
| `observed` | string | Outcome actually seen: `allow` or `deny`. |
| `seconds` | float | End-to-end time from request to last fetched row (or to the denial), in seconds. |
| `detail` | string | Empty on success; for denials, the HTTP 400 response ("Request denied by identity-aware routing policy"). |

A correct run has `expected == observed` on every row.

#### `experiment_a_latency_percentiles.csv`

Latency percentiles of `experiment_a.csv`, grouped by observed outcome and catalog.

| Column | Type | Description |
|---|---|---|
| `observed` | string | `allow` or `deny`. |
| `catalog` | string | Catalog queried. |
| `p50_ms`, `p90_ms`, `p95_ms` | float | 50th/90th/95th percentile latency in milliseconds. |
| `n` | integer | Number of samples in the group. |

### Experiment C: latency and authentication overhead (`results/`)

Query `SELECT * FROM tpch.sf1.customer LIMIT 5` with country `US`, 200 measured runs per path after warm-up runs.

#### `experiment_c.csv`  (400 rows)

| Column | Type | Description |
|---|---|---|
| `path` | string | `direct` (straight to the Trino coordinator) or `gateway` (via Gateway and selector). |
| `outcome` | string | `allow` for all rows. |
| `seconds` | float | Query time from request to last fetched row, in seconds. |
| `detail` | string | Empty unless an error occurred. |

#### `experiment_c_percentiles.csv`

| Column | Type | Description |
|---|---|---|
| `path` | string | `direct` or `gateway`. |
| `p50`, `p90`, `p95`, `p99` | float | Latency percentiles in **milliseconds**. |
| `n` | float | Number of measured runs. |

The difference between `gateway` and `direct` is the routing overhead.

#### `experiment_c_auth.csv`  (220 rows)

Time to acquire an Entra access token with MSAL, measured separately from queries.

| Column | Type | Description |
|---|---|---|
| `mode` | string | `cache` (token served from the MSAL cache) or `refresh` (forced network refresh). |
| `seconds` | float | Token acquisition time in seconds. |

Interactive sign-in is not included.

### Figures

PNG/PDF plots in `results/` (`experiment_a_heatmap`, `experiment_c_*`) are rendered from the CSVs above.

## Reproduction

Code and instructions are in the project repository (`experimentation.md`, `data/README.md`). Software: Trino with Delta Lake connector, Trino Gateway, FastAPI selector, Python (pandas, MSAL).

## Suggested metadata

- Resource type: Dataset
- Keywords: Trino, Trino Gateway, policy decision point, geo-fencing, data residency, Microsoft Entra ID, query routing, benchmark
- License: choose explicitly (e.g. CC-BY-4.0)
