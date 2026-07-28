import asyncio
import json
from pathlib import Path

from domain.registry import JsonServiceRegistry
from domain.search import LaunchUrlPolicy, SearchService
from llm.schemas import StructuredQuery


def test_explicit_service_name_returns_only_that_service(tmp_path: Path) -> None:
    path = tmp_path / "services.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "services": [
                    {
                        "id": "00000000-0000-4000-8000-000000000001",
                        "name": "Nhà thuốc Long Châu",
                        "provider": "FPT Long Châu",
                        "service_type": "oa",
                        "category": "health",
                        "description": "Nhà thuốc và tư vấn sức khỏe.",
                        "launch_url": "https://zalo.me/3822805105108870889",
                        "owner": "test",
                        "active": True,
                        "last_verified_at": "2026-07-24T00:00:00+07:00",
                        "aliases": ["Long Chau"],
                        "intents": [
                            {
                                "intent": "find_pharmacy",
                                "example_query": "Tìm Long Châu",
                            }
                        ],
                    },
                    {
                        "id": "00000000-0000-4000-8000-000000000002",
                        "name": "Bệnh viện Mắt",
                        "provider": "Test",
                        "service_type": "website",
                        "category": "health",
                        "description": "Khám mắt.",
                        "launch_url": "https://example.com/eye",
                        "owner": "test",
                        "active": True,
                        "last_verified_at": "2026-07-24T00:00:00+07:00",
                        "intents": [
                            {
                                "intent": "find_medical_service",
                                "example_query": "Tìm bệnh viện mắt",
                            }
                        ],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    search = SearchService(
        JsonServiceRegistry(path),
        LaunchUrlPolicy(frozenset({"zalo.me", "example.com"})),
    )

    results = asyncio.run(
        search.search(
            StructuredQuery(
                intent="Find Long Chau pharmacy",
                category="health",
                service="Long Chau pharmacy",
            )
        )
    )

    assert [result.name for result in results] == ["Nhà thuốc Long Châu"]
