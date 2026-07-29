from domain.entity_normalization import normalize_entity, normalize_entity_text


def test_entity_aliases_are_catalog_driven_for_locations_and_context() -> None:
    assert normalize_entity("HCM", "location") == "ho chi minh"
    assert normalize_entity("Sài Gòn", "location") == "ho chi minh"
    assert normalize_entity("Công ty VNG", "organization") == "vng"
    assert normalize_entity("nhân viên VNG", "target_user") == "vng employee"


def test_entity_text_normalizes_a_location_inside_a_region_list() -> None:
    assert normalize_entity_text("Việt Nam; TP.HCM; Cần Thơ", "location") == (
        "viet nam ho chi minh can tho"
    )
