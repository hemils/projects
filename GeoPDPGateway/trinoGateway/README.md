# Identity-aware Trino Gateway POC (local Trino + Microsoft Entra ID)

Entra authenticates the user. For this POC, the client explicitly supplies a
country value to simulate location changes; the selector uses it to choose a
Gateway routing group. This input is spoofable and is not live-location
enforcement. See [POC limitations](../POC_LIMITATIONS.md).

```
client (Entra bearer token) -> Gateway -> routing-api selector (validates token, PDP)
                                       -> Trino coordinator (validates token again)
```

## Setup

### 1. Register Entra for authentication

1. Entra admin center -> App registrations -> New registration (single tenant).
   Note the **Application (client) ID** and **Directory (tenant) ID**.
2. Certificates & secrets -> New client secret. Copy the value securely; do
   not paste it into this repository. If a secret was committed or shared,
   revoke it and create a replacement.
3. Manifest -> set `requestedAccessTokenVersion` (under `api`) to `2`, so tokens
   have `iss = https://login.microsoftonline.com/<TENANT_ID>/v2.0` and
   `aud = <APP_CLIENT_ID>`.
4. Expose an API -> set Application ID URI to `api://<APP_CLIENT_ID>` and add a
   delegated scope named `access`.
5. In **Expose an API** -> **Authorized client applications**, add the Azure
   CLI client `04b07795-8ddb-461a-bbee-02f9e1bf7b46` and select `access`.

Do not configure Country/Region or app roles for location. Entra supplies the
verified user identity only; the user sets a simulated country for this POC.

### 2. Set Entra values in the repo

Replace `<TENANT_ID>` and `<APP_CLIENT_ID>`:

- [routing-api.yaml](../infra/trino-gateway/routing-api.yaml): `OIDC_ISSUER`,
  `OIDC_AUDIENCE`, and `OIDC_JWKS_URL`.
  Leave `TRINO_OAUTH_ENFORCED: "false"` for now.
- [oauth2-local.example.yaml](../infra/trino-k8s-cluster/values/oauth2-local.example.yaml):
  the `issuer` line.

### 3. Deploy the Trino clusters

```sh
kubectl config current-context
bash infra/trino-k8s-cluster/helm/install-trino.sh
bash infra/trino-restricted/helm/install.sh
```

### 4. Create the OAuth secrets

```sh
bash infra/trino-k8s-cluster/helm/create-oauth-secrets.sh
```

Enter the Application (client) ID and client secret from step 1. The script also
prompts for the Trino internal shared secret. It creates the secret in both
namespaces.

### 5. Enable OAuth on both Trino releases

```sh
helm upgrade --install trino trino/trino \
   --namespace default \
   -f infra/trino-k8s-cluster/values/values-local.yaml \
   -f infra/trino-k8s-cluster/values/catalog.yaml \
   -f infra/trino-k8s-cluster/values/oauth2-local.example.yaml \
   --wait --timeout 10m

helm upgrade --install georestricted trino/trino \
   --namespace georestricted \
   -f infra/trino-restricted/values/values.yaml \
   -f infra/trino-restricted/values/catalog.yaml \
   -f infra/trino-k8s-cluster/values/oauth2-local.example.yaml \
   --wait --timeout 10m
```

### 6. Build and deploy the selector

```sh
docker build -f Dockerfile.routing-api -t geo-pdp-routing-api:dev .
kind load docker-image geo-pdp-routing-api:dev --name trino
kubectl apply -f infra/trino-gateway/routing-api.yaml
kubectl rollout status deployment/routing-api -n default --timeout=2m
kubectl exec deploy/routing-api -- python -c 'import os,urllib.request; print(urllib.request.urlopen(os.environ["OIDC_JWKS_URL"], timeout=10).status)'
```

The last command should print `200`.

### 7. Connect Gateway and enable routing

Follow the Gateway install guide only if Gateway is not installed yet:
[infra/trino-gateway/README.md](../infra/trino-gateway/README.md). Register its
two backends there: base coordinator -> `unrestricted`; restricted coordinator ->
`georestricted`. In [Gateway values](../infra/trino-gateway/values.yaml), set
`rulesEngineEnabled: true` and keep the external selector URL unchanged. Do not
exclude the `Authorization` header. Then enable the selector and apply both
updates:

```sh
# First verify both Trino coordinators require OAuth and can accept Entra tokens.
# Then set TRINO_OAUTH_ENFORCED: "true" in routing-api.yaml.
kubectl apply -f infra/trino-gateway/routing-api.yaml
kubectl rollout restart deployment/routing-api
```

Re-run the Gateway Helm upgrade command from its install guide so its database
credentials continue to be supplied, and wait for Gateway to become ready.

### 8. Get a token and simulate a country

```sh
kubectl port-forward -n default svc/trino-gateway 18080:8080
```

In another terminal:

```sh
az login --tenant "24454ef6-5e74-4b73-8910-0d8f3e32d649" --scope "api://887aa013-8646-4f77-944f-6d0922eabbed/access" 
export TRINO_ACCESS_TOKEN=$(az account get-access-token \
  --scope api://887aa013-8646-4f77-944f-6d0922eabbed/access --query accessToken -o tsv)
export TRINO_USER=<user UPN> P1q2r3s4
export TRINO_HTTP_SCHEME=http
export TRINO_POC_COUNTRY=US

python scripts/query_gateway.py 'SELECT * FROM tpch.sf1.customer LIMIT 5'
python scripts/query_gateway.py 'select c.*, t.* from trades_raw.trades_schema.customer c INNER JOIN trades_raw.trades_schema.trades t on c.customer_id = t.customer_id limit 5'
```

Expected: the first query routes to `unrestricted`; `trades_raw` routes to
`georestricted` while `TRINO_POC_COUNTRY=US`. Simulate a trip by changing it to
`GB` and rerunning the `trades_raw` query; the policy should deny it. The client
adds `X-Poc-User-Country` to the Gateway request, Gateway forwards it to the
selector, and the selector returns the chosen routing group or a denial.

Decode the token at https://jwt.ms to check `iss`, `aud`, and
`preferred_username` if anything is rejected. Country is deliberately not taken
from this token. Tokens expire after about an hour;
re-run the `export` line to refresh.

## Notes

- `routing-api.yaml` holds the selector's environment variables (ConfigMap) plus
  its Deployment and Service. The selector is the service Gateway calls to get a
  routing group.
- Trino rejects authenticated requests over plain HTTP by default.
  `allow-insecure-over-http=true` in the overlay is for local use only. Use TLS
  for anything shared.
- `scripts/query_gateway.py` sends the Entra token as a bearer header. The
   current local HTTP-only Trino chart setting is for development; the trusted
   ingress and production use must provide HTTPS.
- To add a routing group: register a backend in Gateway with that
  `routingGroup`, add a `CatalogPolicy` in [pdp/policy.py](../pdp/policy.py)
  with the same group name, add tests, and rebuild the selector.
- `TRINO_POC_COUNTRY` is caller-controlled and trivially spoofed. It demonstrates
   policy evaluation and routing only; it does not establish where a user is.
   Real live-location enforcement requires a trusted IP-aware ingress that
   overwrites the country header. Do not log bearer tokens.

Run unit tests from the repository root with `python -m pytest`.
