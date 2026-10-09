from pdp.policy import CatalogPolicy, decide


def test_trades_raw_allowed_from_us_and_selects_georestricted_cluster() -> None:
    result = decide(subject="poc-user", location="US", catalogs={"trades_raw"})

    assert result.permit is True
    assert result.cluster_name == "georestricted"


def test_trades_raw_denied_from_uk() -> None:
    result = decide(subject="poc-user", location="UK", catalogs={"trades_raw"})

    assert result.permit is False
    assert result.cluster_name is None


def test_tpch_allowed_from_any_configured_region_and_selects_unrestricted_cluster() -> None:
    result = decide(subject="poc-user", location="UK", catalogs={"tpch"})

    assert result.permit is True
    assert result.cluster_name == "unrestricted"


def test_unknown_or_multiple_catalogs_are_denied() -> None:
    unknown = decide(subject="poc-user", location="US", catalogs={"secret"})
    multiple = decide(subject="poc-user", location="US", catalogs={"tpch", "trades_raw"})

    assert unknown.permit is False
    assert multiple.permit is False


def test_missing_location_is_denied() -> None:
    result = decide(subject="poc-user", location=None, catalogs={"tpch"})

    assert result.permit is False


def test_policy_uses_metadata_for_catalogs_not_hard_coded_catalog_branches() -> None:
    result = decide(
        subject="poc-user",
        location="UK",
        catalogs={"finance"},
        catalog_policies={
            "finance": CatalogPolicy(
                allowed_locations=frozenset({"UK"}),
                cluster_name="uk-data",
            )
        },
    )

    assert result.permit is True
    assert result.cluster_name == "uk-data"
