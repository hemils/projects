#!/usr/bin/env bash
set -euo pipefail

# Remove this namespace's Trino release, Hive Metastore, and namespace-local
# secrets. The PostgreSQL database itself is external and is not removed.
helm uninstall georestricted --namespace georestricted --ignore-not-found
kubectl delete deployment/hive-metastore service/hive-metastore \
	secret/hive-metastore-db-secret secret/trino-adls-credentials \
	--namespace georestricted \
	--ignore-not-found