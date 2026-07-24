import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

from domain.registry import JsonServiceRegistry
from llm.schemas import StructuredQuery

REAL_REGISTRY_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "registry" / "services.real.json"
)

EXPECTED_LAUNCH_URLS = {
    "https://zalo.me/3359099682314876895",
    "https://www.vio.edu.vn/",
    "https://zalo.me/3822805105108870889",
    "https://www.matsaigon.com/he-thong-benh-vien/",
    "https://zalo.me/coopmart",
    "https://zalo.me/2823598328947213047",
    "https://oa.zalo.me/vinaphone",
    "https://cskh.evnhcmc.vn/",
}

EXPECTED_HOSTS = {
    "zalo.me",
    "www.vio.edu.vn",
    "www.matsaigon.com",
    "oa.zalo.me",
    "cskh.evnhcmc.vn",
}


def test_real_registry_loads_with_eight_active_services() -> None:
    registry = JsonServiceRegistry(REAL_REGISTRY_PATH)

    assert registry.active_count == 8

    services = asyncio.run(registry.search(StructuredQuery(intent="discover_service"), limit=20))
    assert len(services) == 8
    assert all(service.active for service in services)


def test_real_registry_uses_only_reviewed_public_launch_urls() -> None:
    document = json.loads(REAL_REGISTRY_PATH.read_text(encoding="utf-8"))
    launch_urls = {service["launch_url"] for service in document["services"]}
    hosts = {urlparse(url).hostname for url in launch_urls}

    assert launch_urls == EXPECTED_LAUNCH_URLS
    assert hosts == EXPECTED_HOSTS
    assert all(urlparse(url).scheme == "https" for url in launch_urls)
    assert all("example.com" not in url.casefold() for url in launch_urls)


def test_real_registry_notice_preserves_verification_limits() -> None:
    document = json.loads(REAL_REGISTRY_PATH.read_text(encoding="utf-8"))
    notice = document["notice"].casefold()

    assert "đã được rà soát" in notice
    assert "dấu xác minh oa" in notice
    assert "có thể vẫn chưa được xác minh" in notice
