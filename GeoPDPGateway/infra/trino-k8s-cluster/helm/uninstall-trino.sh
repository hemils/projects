#!/usr/bin/env bash
set -euo pipefail

helm uninstall trino --ignore-not-found
kubectl delete deployment/hive-metastore service/hive-metastore \
	secret/hive-metastore-db-secret secret/trino-adls-credentials \
	--ignore-not-found