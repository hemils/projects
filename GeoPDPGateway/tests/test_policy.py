from pdp.policy import CatalogPolicy, decide


def test_trades_raw_allowed_from_us_and_selects_georestricted_group() -> None:
    result = decide(subject="poc-user", location="US", catalogs={"trades_raw"})

    assert result.permit is True
    assert result.routing_group == "georestricted"


def test_trades_raw_denied_from_de() -> None:
    result = decide(subject="poc-user", location="DE", catalogs={"trades_raw"})

    assert result.permit is False
    assert result.routing_group is None


def test_tpch_allowed_from_any_configured_region_and_selects_unrestricted_group() -> None:
    result = decide(subject="poc-user", location="UK", catalogs={"tpch"})

    assert result.permit is True
    assert result.routing_group == "unrestricted"


def test_unknown_or_empty_catalogs_are_denied() -> None:
    unknown = decide(subject="poc-user", location="US", catalogs={"secret"})
    empty = decide(subject="poc-user", location="US", catalogs=set())

    assert unknown.permit is False
    assert empty.permit is False


def test_catalogs_in_different_routing_groups_are_denied() -> None:
    result = decide(subject="poc-user", location="US", catalogs={"tpch", "trades_raw"})

    assert result.permit is False


def test_multiple_catalogs_in_one_group_are_allowed_when_each_is_permitted() -> None:
    policies = [
        CatalogPolicy(frozenset({"trades_raw", "positions_raw"}), frozenset({"US"}), "georestricted"),
    ]
    allowed = decide(
        subject="poc-user", location="US",
        catalogs={"trades_raw", "positions_raw"}, catalog_policies=policies,
    )
    denied = decide(
        subject="poc-user", location="GB",
        catalogs={"trades_raw", "positions_raw"}, catalog_policies=policies,
    )

    assert allowed.permit is True
    assert allowed.routing_group == "georestricted"
    assert denied.permit is False


def test_missing_location_is_denied() -> None:
    result = decide(subject="poc-user", location=None, catalogs={"tpch"})

    assert result.permit is False


def test_policy_uses_metadata_for_catalogs_not_hard_coded_catalog_branches() -> None:
    result = decide(
        subject="poc-user",
        location="UK",
        catalogs={"finance"},
        catalog_policies=[
            CatalogPolicy(
                catalogs=frozenset({"finance"}),
                allowed_locations=frozenset({"UK"}),
                routing_group="uk-data",
            )
        ],
    )

    assert result.permit is True
    assert result.routing_group == "uk-data"
