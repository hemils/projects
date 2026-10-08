# Geo-restricted Trino cluster

This directory deploys a second Trino Helm release named `georestricted` into
its own Kubernetes namespace, also named `georestricted`. It creates its own
Trino coordinator/workers, Hive Metastore deployment/service, and Kubernetes
Secrets.

## Prerequisites

The base and restricted deployments can use the same PostgreSQL database and
credentials. Copy `GeoPDPGateway/.env.example` to `GeoPDPGateway/.env` and set
`AZURE_ACCESS_KEY` there, or let the restricted installer prompt for the
key. It stores the value in a Secret in its own namespace; `.env` is ignored by
Git and must not be committed. The installer also prompts for the PostgreSQL
password. PostgreSQL must allow connections from the local Kubernetes cluster
as described in `infra/trino-k8s-cluster/trino.md`.

## Install

Run from the repository root:

```sh
bash infra/trino-restricted/helm/install.sh
```

This release has its own Helm values, catalog configuration, coordinator,
workers, and Hive Metastore. Both metastore deployments point at the configured
PostgreSQL database. The catalog reads the ADLS key from its namespace-local
Kubernetes Secret using Trino's `${ENV:AZURE_ACCESS_KEY}` substitution.

Forward both coordinators in separate terminals:

```sh
kubectl port-forward --namespace default svc/trino 9091:8080
kubectl port-forward --namespace georestricted svc/georestricted-trino 9092:8080
```

The restricted coordinator is reachable at `http://localhost:9092`.

## Important POC limitation

The deployments have separate Kubernetes namespaces and separate Hive
Metastore pods, but both metastore instances point at the same PostgreSQL
database. They also currently use the same catalog/table locations and ADLS
account credentials. This creates separate Trino deployments, but does not by
itself enforce location-aware authorization or demonstrate geographic data
residency. For that, configure region-specific table locations and apply the
trusted user-location and data-residency decision in the gateway/PDP or Trino
access control. Both clusters still run locally, so this remains a policy-flow
simulation rather than proof of physical residency or regional isolation.

## Uninstall

```sh
bash infra/trino-restricted/helm/uninstall.sh
```

Uninstalling removes the restricted Trino deployment, metastore pods/service,
and namespace-local Secrets. It does not delete the external PostgreSQL
database or the base Trino deployment.