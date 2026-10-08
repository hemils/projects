## Create k8s cluster

kind create cluster --name trino

## port forward to port x if you have other process running on 8080

kubectl port-forward svc/trino 9090:8080

## Install Trino with Delta Lake and Hive Metastore

The installer deploys the Hive Metastore in Kubernetes and connects it to the
existing PostgreSQL database `trinodb` using the `hiveuser` account. It prompts
for the PostgreSQL password without echoing it. To provide the ADLS access key
from a local ignored file, copy `GeoPDPGateway/.env.example` to
`GeoPDPGateway/.env` and set `AZURE_ACCESS_KEY` there. The installer loads that file
and stores the key in a Kubernetes Secret; it also prompts for the key without
echoing it if `AZURE_ACCESS_KEY` is not set. Never commit `.env`.
Run it from the repository root:

```sh
bash infra/trino-k8s-cluster/helm/install-trino.sh
```

The defaults are `host.docker.internal:5432`, database `trinodb`, and user
`hiveuser`. Override them with `HMS_DB_HOST`, `HMS_DB_PORT`, `HMS_DB_NAME`, and
`HMS_DB_USER` if needed. PostgreSQL must accept TCP connections from the kind
cluster; binding only to `localhost` is not sufficient. Configure PostgreSQL's
`listen_addresses` and `pg_hba.conf` to permit the Docker Desktop/kind network
and grant the Hive user access to the `trinodb` database before installing. If
the database uses PostgreSQL 15 or newer and `hiveuser` is not its owner, also
grant schema permissions inside `trinodb`:

```sql
GRANT USAGE, CREATE ON SCHEMA public TO hiveuser;
```

The ADLS account must have hierarchical namespace enabled. If the key that was
previously embedded in a catalog file was real, rotate it in Azure. The
catalogs now reference `AZURE_ACCESS_KEY` through Trino's environment
substitution; the installer stores the key in a Kubernetes Secret and does not
write it to catalog configuration.

After installation, connect to Trino on port 9090 and check the registered
schemas and tables:

```sql
SHOW SCHEMAS FROM trades_raw;
SHOW TABLES FROM trades_raw.<schema_name>;
```

Delta tables already in ADLS but absent from the metastore must be registered
with the Delta Lake connector's `system.register_table` procedure.

## Geo-restricted Trino release

The separate second-cluster setup is documented in
`infra/trino-restricted/README.md`.

