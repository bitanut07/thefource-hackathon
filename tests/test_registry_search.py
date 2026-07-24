import asyncio
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from domain.registry import JsonServiceRegistry
from domain.search import LaunchUrlPolicy, ScoreComponents, SearchService, final_score
from llm.schemas import StructuredQuery


def _service(
    service_id: str,
    *,
    name: str,
    active: bool = True,
    category: str = "healthcare",
    region: str = "Quận 5, TP.HCM",
    launch_url: str = "https://example.com/service",
    priority: int = 0,
    target_user: str = "general",
    organization: str | None = None,
    intent: str = "find_medical_service",
) -> dict[str, object]:
    return {
        "id": service_id,
        "name": name,
        "provider": "Test provider",
        "service_type": "website",
        "category": category,
        "description": f"Dịch vụ {name}",
        "launch_url": launch_url,
        "region": region,
        "target_user": target_user,
        "organization": organization,
        "active": active,
        "owner": "test",
        "last_verified_at": "2026-07-23T00:00:00+07:00",
        "service_priority": priority,
        "aliases": [name.casefold()],
        "intents": [
            {
                "intent": intent,
                "example_query": f"Tìm {name} ở Quận 5",
            }
        ],
    }


def _write_registry(tmp_path: Path, services: list[dict[str, object]]) -> Path:
    path = tmp_path / "services.json"
    path.write_text(
        json.dumps({"schema_version": "1.0", "services": services}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_registry_loads_once_and_only_returns_active_services(tmp_path: Path) -> None:
    active_id = "00000000-0000-4000-8000-000000000001"
    inactive_id = "00000000-0000-4000-8000-000000000002"
    path = _write_registry(
        tmp_path,
        [
            _service(active_id, name="Khám mắt"),
            _service(inactive_id, name="Khám tai", active=False),
        ],
    )
    registry = JsonServiceRegistry(path)
    path.unlink()

    assert registry.active_count == 1
    assert asyncio.run(registry.get_active(UUID(active_id))) is not None
    assert asyncio.run(registry.get_active(UUID(inactive_id))) is None
    assert [
        service.id
        for service in asyncio.run(
            registry.search(StructuredQuery(intent="find_medical_service", category="healthcare"))
        )
    ] == [UUID(active_id)]


def test_registry_hard_filters_and_orders_deterministically(tmp_path: Path) -> None:
    preferred_id = "00000000-0000-4000-8000-000000000010"
    other_id = "00000000-0000-4000-8000-000000000011"
    registry = JsonServiceRegistry(
        _write_registry(
            tmp_path,
            [
                _service(other_id, name="Phòng khám tổng quát", priority=1),
                _service(preferred_id, name="Khám mắt", priority=5),
                _service(
                    "00000000-0000-4000-8000-000000000012",
                    name="Học toán",
                    category="education",
                ),
            ],
        )
    )
    query = StructuredQuery(
        intent="find_medical_service",
        category="healthcare",
        service="khám mắt",
        location="quan 5",
        target_user="general",
    )

    results = asyncio.run(registry.search(query))

    assert [service.id for service in results] == [UUID(preferred_id), UUID(other_id)]
    assert asyncio.run(registry.search(query, limit=0)) == []


def test_registry_prioritizes_matching_organization_context(tmp_path: Path) -> None:
    vng_id = "00000000-0000-4000-8000-000000000013"
    registry = JsonServiceRegistry(
        _write_registry(
            tmp_path,
            [
                _service(
                    "00000000-0000-4000-8000-000000000014",
                    name="Quầy đồ ăn chung",
                    category="shopping_delivery",
                    target_user="vng_employee",
                    intent="find_food_service",
                    priority=100,
                ),
                _service(
                    vng_id,
                    name="Ba Sao",
                    category="shopping_delivery",
                    region="VNG Campus, TP.HCM",
                    target_user="vng_employee",
                    organization="VNG",
                    intent="find_food_service",
                    priority=1,
                ),
                _service(
                    "00000000-0000-4000-8000-000000000015",
                    name="Canteen công ty khác",
                    category="shopping_delivery",
                    target_user="vng_employee",
                    organization="Công ty khác",
                    intent="find_food_service",
                ),
            ],
        )
    )
    query = StructuredQuery(
        intent="find_food_service",
        category="shopping_delivery",
        service="đồ ăn",
        target_user="vng_employee",
        organization="VNG",
    )

    results = asyncio.run(registry.search(query))

    assert [service.id for service in results] == [UUID(vng_id)]


def test_registry_hard_filters_do_not_match_substrings_or_missing_company(
    tmp_path: Path,
) -> None:
    registry = JsonServiceRegistry(
        _write_registry(
            tmp_path,
            [
                _service(
                    "00000000-0000-4000-8000-000000000016",
                    name="Quận 1 VNG",
                    region="Quận 1; TP.HCM",
                    organization="VNG",
                ),
                _service(
                    "00000000-0000-4000-8000-000000000017",
                    name="Quận 10 VNGX",
                    region="Quận 10; TP.HCM",
                    organization="VNGX",
                ),
                _service(
                    "00000000-0000-4000-8000-000000000018",
                    name="Không có công ty",
                    region="Quận 1; TP.HCM",
                    organization=None,
                ),
            ],
        )
    )

    results = asyncio.run(
        registry.search(
            StructuredQuery(
                intent="find_medical_service",
                category="healthcare",
                location="Quận 1",
                organization="VNG",
            )
        )
    )

    assert [service.name for service in results] == ["Quận 1 VNG"]

    synonym_results = asyncio.run(
        registry.search(
            StructuredQuery(
                intent="find_medical_service",
                category="healthcare",
                location="Hồ Chí Minh",
                organization="Công ty VNG",
            )
        )
    )

    assert [service.name for service in synonym_results] == ["Quận 1 VNG"]


def test_registry_rejects_duplicate_ids_and_invalid_records(tmp_path: Path) -> None:
    service_id = "00000000-0000-4000-8000-000000000001"
    duplicate_path = _write_registry(
        tmp_path,
        [_service(service_id, name="A"), _service(service_id, name="B")],
    )
    with pytest.raises(ValueError, match="duplicate service id"):
        JsonServiceRegistry(duplicate_path)

    invalid_path = _write_registry(
        tmp_path,
        [_service("not-a-uuid", name="Invalid")],
    )
    with pytest.raises(ValidationError):
        JsonServiceRegistry(invalid_path)

    missing_verification = _service(
        "00000000-0000-4000-8000-000000000003",
        name="Missing verification",
    )
    missing_verification["last_verified_at"] = None
    with pytest.raises(ValidationError, match="requires last_verified_at"):
        JsonServiceRegistry(_write_registry(tmp_path, [missing_verification]))

    naive_verification = _service(
        "00000000-0000-4000-8000-000000000004",
        name="Naive verification",
    )
    naive_verification["last_verified_at"] = "2026-07-23T00:00:00"
    with pytest.raises(ValidationError, match="include a timezone"):
        JsonServiceRegistry(_write_registry(tmp_path, [naive_verification]))


def test_final_score_clamps_each_component_before_weighting() -> None:
    assert final_score(ScoreComponents(1.0, 1.0, 1.0, 1.0, 1.0)) == 1.0
    assert final_score(ScoreComponents(2.0, -1.0, 0.5, 0.5, 0.5)) == pytest.approx(0.55)
    assert final_score(ScoreComponents(float("nan"), 0.0, 0.0, 0.0, 0.0)) == 0.0


def test_launch_url_policy_requires_https_and_an_exact_normalized_host() -> None:
    policy = LaunchUrlPolicy(frozenset({" Example.COM. ", "dịch-vụ.vn"}))
    idna_host = "dịch-vụ.vn".encode("idna").decode("ascii")

    assert policy.allowed_hosts == frozenset({"example.com", idna_host})
    assert policy.is_allowed("https://EXAMPLE.com/path")
    assert policy.is_allowed("https://dịch-vụ.vn/path")
    assert not policy.is_allowed("http://example.com/path")
    assert not policy.is_allowed("https://sub.example.com/path")
    assert not policy.is_allowed("https://example.com.evil.test/path")
    assert not policy.is_allowed("https://user@example.com/path")


def test_search_service_filters_urls_ranks_and_respects_limit(tmp_path: Path) -> None:
    best_id = "00000000-0000-4000-8000-000000000020"
    registry = JsonServiceRegistry(
        _write_registry(
            tmp_path,
            [
                _service(
                    "00000000-0000-4000-8000-000000000021",
                    name="Khám mắt bị chặn",
                    launch_url="https://blocked.test/service",
                    priority=100,
                ),
                _service(best_id, name="Khám mắt", priority=10),
                _service(
                    "00000000-0000-4000-8000-000000000022",
                    name="Phòng khám tổng quát",
                    priority=1,
                ),
            ],
        )
    )
    search = SearchService(
        registry,
        LaunchUrlPolicy(frozenset({"example.com"})),
    )
    query = StructuredQuery(
        intent="find_medical_service",
        category="healthcare",
        service="khám mắt",
        location="Quận 5",
        target_user="general",
    )

    candidates = asyncio.run(search.search(query, limit=1))

    assert len(candidates) == 1
    assert candidates[0].service_id == UUID(best_id)
    assert 0.0 <= candidates[0].score <= 1.0
    assert str(candidates[0].launch_url).startswith("https://example.com/")
    assert asyncio.run(search.search(query, limit=0)) == []
    assert asyncio.run(search.search(query.model_copy(update={"out_of_scope": True}))) == []
