import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

from domain.registry import JsonServiceRegistry
from domain.urls import is_canonical_zalo_oa_url
from llm.schemas import StructuredQuery

REAL_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "registry" / "services.real.json"
)

EXPECTED_LAUNCH_URLS = {
    "https://zalo.me/3359099682314876895",
    "https://zalo.me/3822805105108870889",
    "https://zalo.me/1628468992301153938",
    "https://zalo.me/2823598328947213047",
    "https://zalo.me/3725994261701149374",
}

EXPECTED_HOSTS = {"zalo.me"}
OFFICIAL_ZALO_CATEGORIES = {
    "food",
    "education",
    "shopping",
    "finance",
    "utilities",
    "health",
    "government",
    "other",
}


def test_real_registry_loads_with_zalo_native_services_only() -> None:
    registry = JsonServiceRegistry(REAL_REGISTRY_PATH)

    assert registry.active_count == 5

    services = asyncio.run(registry.search(StructuredQuery(intent="discover_service"), limit=20))
    assert len(services) == 5
    assert all(service.active for service in services)
    assert all(service.service_type.value in {"oa", "mini_app"} for service in services)


def test_real_registry_uses_only_reviewed_public_launch_urls() -> None:
    document = json.loads(REAL_REGISTRY_PATH.read_text(encoding="utf-8"))
    launch_urls = {service["launch_url"] for service in document["services"]}
    hosts = {urlparse(url).hostname for url in launch_urls}

    assert launch_urls == EXPECTED_LAUNCH_URLS
    assert hosts == EXPECTED_HOSTS
    assert all(urlparse(url).scheme == "https" for url in launch_urls)
    assert all("example.com" not in url.casefold() for url in launch_urls)
    assert all(service["service_type"] in {"oa", "mini_app"} for service in document["services"])
    assert all(is_canonical_zalo_oa_url(service["launch_url"]) for service in document["services"])
    assert {service["category"] for service in document["services"]} <= OFFICIAL_ZALO_CATEGORIES
    long_chau = next(
        service for service in document["services"] if service["name"] == "Nhà thuốc Long Châu"
    )
    assert long_chau["launch_url"] == "https://zalo.me/3822805105108870889"


def test_real_registry_notice_preserves_verification_limits() -> None:
    document = json.loads(REAL_REGISTRY_PATH.read_text(encoding="utf-8"))
    notice = document["notice"].casefold()

    assert "đã được rà soát" in notice
    assert "dấu xác minh oa" in notice
    assert "có thể vẫn chưa được xác minh" in notice
