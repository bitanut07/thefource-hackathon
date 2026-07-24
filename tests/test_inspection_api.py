from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

import main
from config import Settings
from domain.rag_store import RagDocument, SqliteRagStore
from llm.schemas import StructuredQuery

API_HEADERS = {"X-API-Key": "test-navigator-key"}
REAL_ALLOWED_HOSTS = "zalo.me,oa.zalo.me,www.vio.edu.vn,www.matsaigon.com,cskh.evnhcmc.vn"


class StubIntentExtractor:
    def __init__(self, result: StructuredQuery) -> None:
        self.result = result
        self.received_texts: list[str] = []

    async def extract_structured_query(self, text: str) -> StructuredQuery:
        self.received_texts.append(text)
        return self.result


class InspectionNavigator:
    def __init__(self, extractor: StubIntentExtractor) -> None:
        self.intent_extractor = extractor


def _build_rag_database(path: Path) -> None:
    document = RagDocument(
        document_id="pending:vng-campus-food-ba-sao",
        name="Ba Sao",
        content="Nhân viên VNG tìm đồ ăn tại VNG Campus.",
        source_path="pending.json",
        source_type="user_reported",
        category="shopping_delivery",
        channel_type="unknown",
        active=False,
        launchable=False,
        review_status="pending_verification",
        verification_status="needs_official_url",
        metadata={"private_debug_value": "must-not-leak"},
    )
    with SqliteRagStore(path) as store:
        store.replace_documents([document])


def _create_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[FastAPI, StubIntentExtractor]:
    rag_path = tmp_path / "rag.sqlite3"
    _build_rag_database(rag_path)
    extractor = StubIntentExtractor(
        StructuredQuery(
            intent="find_food_service",
            category="shopping_delivery",
            service="đồ ăn",
            target_user="vng_employee",
            organization="VNG",
        )
    )
    navigator = InspectionNavigator(extractor)
    monkeypatch.setattr(
        main,
        "build_navigator",
        lambda _settings, **_kwargs: navigator,
    )
    settings = Settings(
        llm_provider="gemini",
        gemini_api_key=SecretStr("test-only"),
        navigator_api_key=SecretStr("test-navigator-key"),
        allowed_launch_hosts=REAL_ALLOWED_HOSTS,
        rag_data_path=rag_path,
    )
    return main.create_app(settings), extractor


def test_intent_extraction_api_returns_validated_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, extractor = _create_app(monkeypatch, tmp_path)

    response = TestClient(app).post(
        "/api/v1/intents/extract",
        json={"text": "  Là nhân viên VNG, tôi cần mua đồ ăn.  "},
        headers=API_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {
        "intent": "find_food_service",
        "category": "shopping_delivery",
        "service": "đồ ăn",
        "location": None,
        "time": None,
        "target_user": "vng_employee",
        "organization": "VNG",
        "needs_clarification": False,
        "clarification_field": None,
        "out_of_scope": False,
    }
    assert extractor.received_texts == ["Là nhân viên VNG, tôi cần mua đồ ăn."]


def test_registry_list_and_detail_only_return_runtime_public_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _extractor = _create_app(monkeypatch, tmp_path)
    client = TestClient(app)

    all_services = client.get("/api/v1/services", headers=API_HEADERS)
    education = client.get(
        "/api/v1/services",
        params={"category": "education"},
        headers=API_HEADERS,
    )

    assert all_services.status_code == 200
    assert all_services.json()["total"] == 8
    assert education.status_code == 200
    assert education.json()["total"] == 2
    first = all_services.json()["items"][0]
    assert "owner" not in first
    assert "service_priority" not in first
    assert "score" not in first

    detail = client.get(
        f"/api/v1/services/{first['service_id']}",
        headers=API_HEADERS,
    )
    missing = client.get(
        f"/api/v1/services/{UUID('00000000-0000-4000-8000-000000000099')}",
        headers=API_HEADERS,
    )

    assert detail.status_code == 200
    assert detail.json()["service_id"] == first["service_id"]
    assert missing.status_code == 404


def test_research_search_is_explicitly_non_launchable_and_does_not_leak_raw_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _extractor = _create_app(monkeypatch, tmp_path)

    response = TestClient(app).post(
        "/api/v1/research/search",
        json={
            "text": 'Ba Sao" OR * nhân viên VNG',
            "category": "shopping_delivery",
            "limit": 5,
        },
        headers=API_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0] == {
        "rank": 1,
        "document_id": "pending:vng-campus-food-ba-sao",
        "name": "Ba Sao",
        "category": "shopping_delivery",
        "channel_type": "unknown",
        "source_type": "user_reported",
        "review_status": "pending_verification",
        "verification_status": "needs_official_url",
        "launchable": False,
        "matched_terms": ["ba", "sao", "nhan", "vien", "vng"],
        "usage": "research_only",
    }
    assert set(payload["items"][0]).isdisjoint(
        {
            "launch_url",
            "official_url",
            "metadata",
            "source_path",
            "content",
        }
    )
    serialized = response.text
    for forbidden in ("private_debug_value",):
        assert forbidden not in serialized


def test_inspection_apis_require_auth_and_missing_rag_returns_503(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _extractor = _create_app(monkeypatch, tmp_path)
    client = TestClient(app)

    assert client.get("/api/v1/services").status_code == 401
    assert (
        client.post(
            "/api/v1/intents/extract",
            json={"text": "Tìm dịch vụ"},
        ).status_code
        == 401
    )

    settings = app.state.settings.model_copy(update={"rag_data_path": tmp_path / "missing.sqlite3"})
    app.state.settings = settings
    missing_rag = client.post(
        "/api/v1/research/search",
        json={"text": "Ba Sao"},
        headers=API_HEADERS,
    )
    assert missing_rag.status_code == 503


def test_openapi_lists_the_complete_test_surface(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app, _extractor = _create_app(monkeypatch, tmp_path)
    schema = TestClient(app).get("/openapi.json").json()

    expected_paths = {
        "/api/v1/intents/extract",
        "/api/v1/navigate",
        "/api/v1/research/search",
        "/api/v1/services",
        "/api/v1/services/{service_id}",
        "/health/live",
        "/health/ready",
        "/webhooks/zalo",
    }
    assert set(schema["paths"]) == expected_paths
    for path in (
        "/api/v1/intents/extract",
        "/api/v1/navigate",
        "/api/v1/research/search",
        "/api/v1/services",
        "/api/v1/services/{service_id}",
    ):
        operation = next(iter(schema["paths"][path].values()))
        assert {"NavigatorApiKey": []} in operation["security"]
