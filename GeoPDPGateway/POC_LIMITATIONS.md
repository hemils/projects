# Geo-aware Trino Gateway POC

## Purpose

This project demonstrates geo-restriction-based policy evaluation and query execution for Trino. The policy evaluates the query's catalog and configured location, selects a destination cluster identifier, and executes through the corresponding Trino backend.

For this POC, cluster identifiers such as `georestricted` and `unrestricted` represent logical destinations. They demonstrate how policy decisions direct queries; they do not claim that the corresponding clusters are physically running in those geographic regions. The POC validates the policy-to-cluster selection flow without prescribing a cloud provider or infrastructure layout.

## POC behavior

- `trades_raw` selects the `georestricted` cluster identifier when the configured location is `US`.
- `tpch` selects the `unrestricted` cluster identifier for any configured location.
- The API resolves the selected identifier to a Trino Gateway backend and executes the query against its configured coordinator.
- The policy metadata and local API setup are described in the [trinoGateway run guide](trinoGateway/README.md).

## Applying this model to a deployment

The logical destinations can be connected to Kubernetes clusters on a cloud platform selected to meet business, residency, and operational requirements. In such a deployment, configure each destination's Gateway backend to point to the appropriate cluster and region. The policy-to-destination flow remains the same while the infrastructure determines where the workloads and data are hosted.

This repository is a proof of concept for demonstrating that flow; its configured cluster names and local setup are illustrative rather than a statement of physical data residency.
