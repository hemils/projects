"""Small, deterministic catalog/location policy for the POC.

This module is independent of FastAPI and Trino Gateway. Policy metadata
returns the Gateway routing-group name selected for an allowed request.
"""

from dataclasses import dataclass
from collections.abc import Sequence


@dataclass(frozen=True)
class CatalogPolicy:
    """Locations and Gateway group shared by a set of catalogs."""

    catalogs: frozenset[str]
    allowed_locations: frozenset[str] | None
    routing_group: str


# ``None`` means every non-empty configured location is allowed.
CATALOG_POLICIES: list[CatalogPolicy] = [
    CatalogPolicy(
        catalogs=frozenset({"trades_raw"}),
        allowed_locations=frozenset({"US"}),
        routing_group="georestricted",
    ),
    CatalogPolicy(
            catalogs=frozenset({"trades_raw"}),
            allowed_locations=frozenset({"UK"}),
            routing_group="georestricted",
        ),
    CatalogPolicy(
                catalogs=frozenset({"customer"}),
                allowed_locations=frozenset({"US"}),
                routing_group="georestricted",
            ),
    CatalogPolicy(
                catalogs=frozenset({"customer"}),
                allowed_locations=frozenset({"DE"}),
                routing_group="georestricted",
        ),
    CatalogPolicy(
        catalogs=frozenset({"tpch"}),
        allowed_locations=None,
        routing_group="unrestricted",
    ),
]


@dataclass(frozen=True)
class PolicyDecision:
    """Policy result consumed by the Gateway external selector."""

    permit: bool
    routing_group: str | None
    reason: str


def decide(
    *,
    subject: str,
    location: str | None,
    catalogs: set[str],
    catalog_policies: Sequence[CatalogPolicy] = CATALOG_POLICIES,
) -> PolicyDecision:
    """Decide access for the catalogs of one query using an authenticated context.

    The caller must provide identity and location only after validating their
    trusted sources (OIDC and a network-location edge); never pass unverified
    request headers. Every catalog must be covered and permitted, and all must
    share one routing group, since a query cannot span Gateway backends.
    """

    if not subject.strip():
        return PolicyDecision(False, None, "POC subject is not configured")

    normalized_location = location.strip().upper() if location else ""
    if not normalized_location:
        return PolicyDecision(False, None, "POC location is not configured")

    normalized_catalogs = {catalog.strip().lower() for catalog in catalogs if catalog.strip()}
    if not normalized_catalogs:
        return PolicyDecision(False, None, "At least one analyzed catalog is required")

    policies_by_catalog: dict[str, list[CatalogPolicy]] = {}
    for policy in catalog_policies:
        for name in policy.catalogs:
            if name.strip():
                policies_by_catalog.setdefault(name.strip().lower(), []).append(policy)

    # A catalog may have several entries; any entry permitting the location grants it.
    common_groups: set[str] | None = None
    for catalog in sorted(normalized_catalogs):
        entries = policies_by_catalog.get(catalog)
        if not entries:
            return PolicyDecision(False, None, f"Catalog is not covered by the POC policy: {catalog}")
        groups = {
            entry.routing_group
            for entry in entries
            if entry.allowed_locations is None
            or normalized_location in {r.strip().upper() for r in entry.allowed_locations}
        }
        if not groups:
            return PolicyDecision(False, None, f"Location {normalized_location} is not permitted for catalog {catalog}")
        common_groups = groups if common_groups is None else common_groups & groups

    if not common_groups or len(common_groups) != 1:
        return PolicyDecision(False, None, "Catalogs do not resolve to exactly one routing group")

    return PolicyDecision(
        True,
        next(iter(common_groups)),
        f"Catalogs {', '.join(sorted(normalized_catalogs))} are permitted from {normalized_location}",
    )
