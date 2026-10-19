# GeoPDPGateway

GeoPDPGateway is a proof of concept for identity-aware SQL routing with Trino
Gateway. A FastAPI selector validates an OIDC access token, asks the policy
decision point (PDP) to evaluate the request's catalog and supplied country,
then returns a Gateway routing group or a denial. The selector chooses a
destination; it does not execute SQL.

The project includes local Kubernetes deployment guides for Trino Gateway and
two Trino clusters, sample data, and experiments covering policy outcomes and
request latency.

> **POC security and residency note:** the country value is supplied by the
> client and is spoofable. Routing groups and separate local clusters do not
> establish a user's physical location or prove data residency. Trino-side
> authentication, TLS, authorization, trusted location signals, and protected
> coordinator access are required for a production system. See
> [POC limitations](POC_LIMITATIONS.md).

## Documentation

### Application and policy

- [End-to-end application guide](trinoGateway/README.md) — configures OIDC,
	deploys the selector, enables OAuth and Gateway routing, and walks through
	sample queries. The selector implementation is in `trinoGateway/`; identity
	verification and catalog policy are in `pdp/`.
- [POC limitations](POC_LIMITATIONS.md) — explains the prototype's assumptions,
	security boundaries, and what is needed to adapt the routing model to a real
	deployment.

### Infrastructure deployment

- [Base Trino cluster deployment](infra/trino-k8s-cluster/trino.md) — sets up
	the local Kubernetes cluster, Trino, Hive Metastore, PostgreSQL, and ADLS
	catalog configuration.
- [Trino Gateway deployment](infra/trino-gateway/README.md) — installs Gateway,
	registers Trino backends, and documents the external identity-aware selector
	integration.
- [Geo-restricted Trino deployment](infra/trino-restricted/README.md) — deploys
	a second Trino release in its own namespace and describes its POC limitations.

### Data and experiments

- [Sample data guide](data/README.md) — describes the CSV samples and how to
	export them from ADLS.
- [Experiment guide](experimentation.md) — documents policy-correctness and
	latency/authentication experiments, prerequisites, commands, and outputs in
	`results/`.
- [Zenodo dataset description](ZENODO_DESCRIPTION.md) — provides dataset,
	experiment-result, and reproducibility metadata.

## Repository map

| Path | Purpose |
|---|---|
| `trinoGateway/` | FastAPI external selector called by Trino Gateway. |
| `pdp/` | OIDC identity verification and catalog/location routing policy. |
| `infra/` | Helm values, Kubernetes manifests, and deployment scripts for Gateway and Trino clusters. |
| `scripts/` | Gateway query client, data export, and experiment runners. |
| `data/` | Sample CSV inputs used by the POC. |
| `results/` | Experiment measurements and derived results. |
| `tests/` | Unit and API tests for identity handling, policy, and selector behavior. |

## Quick start

1. Review the [end-to-end application guide](trinoGateway/README.md) and
	 configure the OIDC provider values for your environment.
2. Deploy the base and restricted clusters using the
	 [base cluster guide](infra/trino-k8s-cluster/trino.md) and
	 [restricted cluster guide](infra/trino-restricted/README.md).
3. Install and configure Gateway using the
	 [Gateway deployment guide](infra/trino-gateway/README.md), then follow the
	 application guide to deploy and enable the selector.
4. Install Python dependencies from `requirements.txt`, then run the tests from
	 the repository root:

	 ```sh
	 python -m pip install -r requirements.txt
	 python -m pytest
	 ```

For experiment setup and execution, see [experimentation.md](experimentation.md).
