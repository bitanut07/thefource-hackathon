import json
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

CATALOG_PATH = Path("data/research/oa-candidates.json")
EXPECTED_CATEGORIES = {
    "utilities",
    "healthcare",
    "education",
    "transport_travel",
    "public_admin",
    "finance_banking",
    "shopping_delivery",
    "entertainment",
}
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_services() -> list[dict[str, Any]]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "0.1"
    assert payload["source_scope"] == "public_first_party_only"
    return cast(list[dict[str, Any]], payload["services"])


def test_research_catalog_covers_mockup_categories() -> None:
    services = load_services()

    assert len(services) >= 30
    assert {service["category"] for service in services} == EXPECTED_CATEGORIES
    assert sum(service["channel_type"] == "oa" for service in services) >= 10


def test_research_candidates_remain_inactive_and_unique() -> None:
    services = load_services()
    candidate_ids = [service["candidate_id"] for service in services]

    assert len(candidate_ids) == len(set(candidate_ids))
    assert all(isinstance(candidate_id, str) for candidate_id in candidate_ids)
    assert all(ID_PATTERN.fullmatch(candidate_id) for candidate_id in candidate_ids)
    assert all(service["active"] is False for service in services)
    assert all(service["review_status"] == "candidate" for service in services)


def test_research_candidates_have_card_search_and_provenance_fields() -> None:
    for service in load_services():
        for field in ("name", "provider", "description", "launch_url", "cta_label"):
            assert service[field]
        for field in ("regions", "target_users", "capabilities", "aliases", "intents"):
            assert service[field]
        assert isinstance(service["organization_contexts"], list)

        launch_url = urlparse(service["launch_url"])
        assert launch_url.scheme in {"http", "https"}
        assert launch_url.netloc

        evidence_items = service["evidence"]
        assert evidence_items
        for evidence in evidence_items:
            assert evidence["publisher"]
            assert evidence["supports"]
            assert evidence["checked_at"] == "2026-07-23"


def test_research_logo_references_are_never_qr_codes() -> None:
    for service in load_services():
        logo_url = service["logo_url"]
        assert service["logo_usage"] == "reference_only_needs_review"
        if logo_url is not None:
            assert "qr.zalo.me" not in logo_url


def test_oa_badges_are_not_inferred_from_public_pages() -> None:
    oa_services = [service for service in load_services() if service["channel_type"] == "oa"]

    assert oa_services
    assert all(service["verification"]["oa_badge_status"] == "unknown" for service in oa_services)


def test_vng_campus_food_pending_data_never_invents_oa_urls() -> None:
    path = Path("data/research/pending/vng-campus-food.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    reported = payload["user_reported_candidates"]
    assert [item["name"] for item in reported] == ["Ba Sao", "Danh Hoa"]
    assert all(item["launch_url"] is None for item in reported)
    assert all(item["needs_official_url"] is True for item in reported)
    assert all(item["active"] is False for item in reported)
    assert payload["catalog_decision"]["active_records"] == []

    references = payload["public_mini_app_references"]
    assert {item["name"] for item in references} == {
        "Highlands Rewards",
        "Phúc Long Rewards",
    }
    assert all(item["vng_campus_presence"] == "unverified" for item in references)
