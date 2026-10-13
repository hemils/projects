#!/usr/bin/env bash
set -euo pipefail

read -r -p "Entra OAuth application client ID: " TRINO_OAUTH_CLIENT_ID
read -r -s -p "Entra OAuth application client secret: " TRINO_OAUTH_CLIENT_SECRET
printf '\n'
if [[ -z "$TRINO_OAUTH_CLIENT_ID" || -z "$TRINO_OAUTH_CLIENT_SECRET" ]]; then
  echo "Entra client ID and secret are required." >&2
  exit 1
fi

umask 077
secret_file="$(mktemp)"
trap 'rm -f "$secret_file"; unset TRINO_OAUTH_CLIENT_SECRET' EXIT

for namespace in default georestricted; do
  TRINO_INTERNAL_SHARED_SECRET="$(openssl rand -base64 32)"
  printf '%s\n' \
    "TRINO_OAUTH_CLIENT_ID=${TRINO_OAUTH_CLIENT_ID}" \
    "TRINO_OAUTH_CLIENT_SECRET=${TRINO_OAUTH_CLIENT_SECRET}" \
    "TRINO_INTERNAL_SHARED_SECRET=${TRINO_INTERNAL_SHARED_SECRET}" > "$secret_file"

  kubectl create secret generic trino-oauth-secrets \
    --namespace "$namespace" \
    --from-env-file="$secret_file" \
    --dry-run=client \
    -o yaml | kubectl apply -f -
  unset TRINO_INTERNAL_SHARED_SECRET
done

unset TRINO_OAUTH_CLIENT_ID TRINO_OAUTH_CLIENT_SECRET
