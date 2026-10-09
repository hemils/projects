"""Small, deterministic catalog/location policy for the POC.

This module is independent of FastAPI and Trino Gateway. It returns a policy
cluster name; the application resolves that name against Gateway's backend
inventory.
"""

from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True)
class CatalogPolicy:
    """Static policy metadata describing its eligible cluster."""

    allowed_locations: frozenset[str] | None
    cluster_name: str


# ``None`` means every non-empty configured location is allowed.
CATALOG_POLICIES: dict[str, CatalogPolicy] = {
    "trades_raw": CatalogPolicy(
        allowed_locations=frozenset({"US"}),
        cluster_name="georestricted",
    ),
    "tpch": CatalogPolicy(
        allowed_locations=None,
        cluster_name="unrestricted",
    ),
}


@dataclass(frozen=True)
class PolicyDecision:
    """Policy result consumed by the query-routing application."""

    permit: bool
    cluster_name: str | None
    reason: str


def decide(
    *,
    subject: str,
    location: str | None,
    catalogs: set[str],
    catalog_policies: Mapping[str, CatalogPolicy] = CATALOG_POLICIES,
) -> PolicyDecision:
    """Decide access for one catalog using a server-configured POC context.

    ``location`` is supplied by the service configuration, never by request
    headers. Queries referencing zero or multiple catalogs are denied for this
    first milestone so an incomplete catalog classification cannot grant access.
    """

    if not subject.strip():
        return PolicyDecision(False, None, "POC subject is not configured")

    normalized_location = location.strip().upper() if location else ""
    if not normalized_location:
        return PolicyDecision(False, None, "POC location is not configured")

    normalized_catalogs = {catalog.strip().lower() for catalog in catalogs if catalog.strip()}
    if len(normalized_catalogs) != 1:
        return PolicyDecision(False, None, "Exactly one analyzed catalog is required")

    catalog = next(iter(normalized_catalogs))
    policies_by_catalog = {
        name.strip().lower(): metadata
        for name, metadata in catalog_policies.items()
        if name.strip()
    }
    metadata = policies_by_catalog.get(catalog)
    if metadata is None:
        return PolicyDecision(False, None, f"Catalog is not covered by the POC policy: {catalog}")

    if metadata.allowed_locations is not None:
        allowed_locations = {region.strip().upper() for region in metadata.allowed_locations}
        if normalized_location not in allowed_locations:
            return PolicyDecision(False, None, f"Location {normalized_location} is not permitted for catalog {catalog}")

    return PolicyDecision(True, metadata.cluster_name, f"Catalog {catalog} is permitted from {normalized_location}")
