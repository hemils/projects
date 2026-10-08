#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VALUES_DIR="${SCRIPT_DIR}/../values"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"

if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${PROJECT_ROOT}/.env"
  set +a
fi

if [[ -z "${AZURE_ACCESS_KEY:-}" ]]; then
  read -r -s -p "ADLS Gen2 storage account access key: " AZURE_ACCESS_KEY
  printf '\n'
fi
if [[ -z "$AZURE_ACCESS_KEY" ]]; then
  echo "ADLS access key cannot be empty." >&2
  exit 1
fi

DB_HOST="${HMS_DB_HOST:-host.docker.internal}"
DB_PORT="${HMS_DB_PORT:-5432}"
DB_NAME="${HMS_DB_NAME:-trinodb}"
DB_USER="${HMS_DB_USER:-hiveuser}"

read -r -s -p "PostgreSQL password for ${DB_USER}@${DB_HOST}/${DB_NAME}: " DB_PASSWORD
printf '\n'
if [[ -z "$DB_PASSWORD" ]]; then
  echo "PostgreSQL password cannot be empty." >&2
  exit 1
fi

umask 077
secret_file="$(mktemp)"
trap 'rm -f "$secret_file"' EXIT

apply_secret() {
  local name="$1"
  shift
  printf '%s\n' "$@" > "$secret_file"
  kubectl create secret generic "$name" \
    --from-env-file="$secret_file" \
    --dry-run=client \
    -o yaml | kubectl apply -f -
}

apply_secret hive-metastore-db-secret \
  "DB_HOST=${DB_HOST}" \
  "DB_PORT=${DB_PORT}" \
  "DB_NAME=${DB_NAME}" \
  "DB_USER=${DB_USER}" \
  "DB_PASSWORD=${DB_PASSWORD}"

apply_secret trino-adls-credentials \
  "AZURE_ACCESS_KEY=${AZURE_ACCESS_KEY}"

unset DB_PASSWORD AZURE_ACCESS_KEY

kubectl apply -f "${VALUES_DIR}/hive-metastore.yaml"
kubectl rollout status deployment/hive-metastore --timeout=5m

helm repo add trino https://trinodb.github.io/charts --force-update
helm repo update
helm upgrade --install trino trino/trino \
  -f "${VALUES_DIR}/values-local.yaml" \
  -f "${VALUES_DIR}/catalog.yaml" \
  --wait \
  --timeout 10m

