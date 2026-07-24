import asyncio
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

import main
from config import Settings
from llm.client import LLMProviderError, LLMUnavailableError
from llm.schemas import AgentResponse

API_HEADERS = {"X-API-Key": "test-navigator-key"}
REAL_ALLOWED_HOSTS = "zalo.me,oa.zalo.me,www.vio.edu.vn,www.matsaigon.com,cskh.evnhcmc.vn"


class StubNavigator:
    def __init__(self) -> None:
        self.received_texts: list[str] = []

    async def process_text(self, text: str) -> AgentResponse:
        self.received_texts.append(text)
        return AgentResponse(message=f"Đã nhận: {text}")


class FailingNavigator:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def process_text(self, text: str) -> AgentResponse:
        del text
        raise self._error


def create_test_app(
    monkeypatch: pytest.MonkeyPatch,
    *,
    app_env: str = "local",
) -> tuple[FastAPI, StubNavigator]:
    navigator = StubNavigator()
    monkeypatch.setattr(
        main,
        "build_navigator",
        lambda _settings, **_kwargs: navigator,
    )
    settings = Settings(
        app_env=app_env,
        llm_provider="gemini",
        gemini_api_key=SecretStr("test-only"),
        navigator_api_key=SecretStr("test-navigator-key"),
        allowed_launch_hosts=REAL_ALLOWED_HOSTS,
    )
    return main.create_app(settings), navigator


def test_navigation_forwards_validated_text_and_returns_agent_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, navigator = create_test_app(monkeypatch)

    response = TestClient(app).post(
        "/api/v1/navigate",
        json={"text": "  Tôi muốn đóng tiền điện ở TP.HCM.  "},
        headers=API_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "Đã nhận: Tôi muốn đóng tiền điện ở TP.HCM.",
        "choices": [],
        "clarification_question": None,
        "handoff_to_human": False,
    }
    assert navigator.received_texts == ["Tôi muốn đóng tiền điện ở TP.HCM."]


def test_navigation_is_available_but_docs_are_disabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, navigator = create_test_app(monkeypatch, app_env=" Production ")
    client = TestClient(app)

    response = client.post(
        "/api/v1/navigate",
        json={"text": "Tìm chỗ khám mắt."},
        headers=API_HEADERS,
    )

    assert response.status_code == 200
    assert navigator.received_texts == ["Tìm chỗ khám mắt."]
    assert client.get("/docs").status_code == 404


def test_swagger_exposes_api_key_authorization_and_request_examples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _navigator = create_test_app(monkeypatch)
    schema = TestClient(app).get("/openapi.json").json()

    security_scheme = schema["components"]["securitySchemes"]["NavigatorApiKey"]
    operation = schema["paths"]["/api/v1/navigate"]["post"]
    request_schema = schema["components"]["schemas"]["NavigateRequest"]

    assert security_scheme == {
        "type": "apiKey",
        "description": ("Nhập NAVIGATOR_API_KEY để gọi API điều hướng và dữ liệu kiểm thử."),
        "in": "header",
        "name": "X-API-Key",
    }
    assert {"NavigatorApiKey": []} in operation["security"]
    assert request_schema["examples"][0]["text"] == ("Tôi muốn đóng tiền điện ở TP.HCM.")


def test_legacy_demo_and_job_routes_are_retired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _navigator = create_test_app(monkeypatch)
    client = TestClient(app)

    assert client.post("/demo/query", json={"text": "Tìm chỗ khám mắt."}).status_code == 404
    assert client.post("/demo/queue", json={"text": "Tìm chỗ khám mắt."}).status_code == 404
    assert client.get("/demo/jobs/example").status_code == 404


def test_navigation_request_rejects_blank_or_extra_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, navigator = create_test_app(monkeypatch)
    client = TestClient(app)

    blank = client.post(
        "/api/v1/navigate",
        json={"text": "   "},
        headers=API_HEADERS,
    )
    extra = client.post(
        "/api/v1/navigate",
        json={"text": "Tìm chỗ khám mắt.", "launch_url": "https://evil.example"},
        headers=API_HEADERS,
    )

    assert blank.status_code == 422
    assert extra.status_code == 422
    assert navigator.received_texts == []


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (LLMUnavailableError("missing credential"), 503),
        (LLMProviderError("invalid provider response"), 502),
    ],
)
def test_navigation_maps_provider_failures_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_status: int,
) -> None:
    navigator = FailingNavigator(error)
    monkeypatch.setattr(
        main,
        "build_navigator",
        lambda _settings, **_kwargs: navigator,
    )
    app = main.create_app(
        Settings(
            navigator_api_key=SecretStr("test-navigator-key"),
            allowed_launch_hosts=REAL_ALLOWED_HOSTS,
        )
    )

    response = TestClient(app).post(
        "/api/v1/navigate",
        json={"text": "Tìm dịch vụ"},
        headers=API_HEADERS,
    )

    assert response.status_code == expected_status
    assert "missing credential" not in response.text
    assert "invalid provider response" not in response.text


def test_navigation_exposes_retry_after_for_temporary_gemini_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigator = FailingNavigator(LLMUnavailableError("quota", retry_after_seconds=7))
    monkeypatch.setattr(
        main,
        "build_navigator",
        lambda _settings, **_kwargs: navigator,
    )
    app = main.create_app(
        Settings(
            gemini_api_key=SecretStr("test-only"),
            navigator_api_key=SecretStr("test-navigator-key"),
            allowed_launch_hosts=REAL_ALLOWED_HOSTS,
        )
    )

    response = TestClient(app).post(
        "/api/v1/navigate",
        json={"text": "Tìm dịch vụ"},
        headers=API_HEADERS,
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "7"
    assert "quota" not in response.text


class HealthyRedis:
    def ping(self) -> bool:
        return True


class UnavailableRedis:
    def ping(self) -> bool:
        raise RedisConnectionError("offline")


def test_readiness_checks_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _navigator = create_test_app(monkeypatch)
    app.state.redis_connection = cast(Redis, HealthyRedis())

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_fails_when_redis_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _navigator = create_test_app(monkeypatch)
    app.state.redis_connection = cast(Redis, UnavailableRedis())

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Redis chưa sẵn sàng."


def test_readiness_fails_when_gemini_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigator = StubNavigator()
    monkeypatch.setattr(
        main,
        "build_navigator",
        lambda _settings, **_kwargs: navigator,
    )
    app = main.create_app(
        Settings(
            llm_provider="gemini",
            gemini_api_key=None,
            navigator_api_key=SecretStr("test-navigator-key"),
            allowed_launch_hosts=REAL_ALLOWED_HOSTS,
        )
    )
    app.state.redis_connection = cast(Redis, HealthyRedis())

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Gemini chưa được cấu hình."


def test_navigation_requires_a_separate_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, navigator = create_test_app(monkeypatch)
    client = TestClient(app)

    missing = client.post("/api/v1/navigate", json={"text": "Tìm dịch vụ"})
    invalid = client.post(
        "/api/v1/navigate",
        json={"text": "Tìm dịch vụ"},
        headers={"X-API-Key": "wrong"},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert navigator.received_texts == []


def test_navigation_rejects_excess_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, navigator = create_test_app(monkeypatch)
    app.state.navigator_semaphore = asyncio.Semaphore(0)

    response = TestClient(app).post(
        "/api/v1/navigate",
        json={"text": "Tìm dịch vụ"},
        headers=API_HEADERS,
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"
    assert navigator.received_texts == []


def test_readiness_fails_for_missing_or_weak_api_key_and_incomplete_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigator = StubNavigator()
    monkeypatch.setattr(
        main,
        "build_navigator",
        lambda _settings, **_kwargs: navigator,
    )

    missing_key = main.create_app(
        Settings(
            gemini_api_key=SecretStr("test-only"),
            navigator_api_key=None,
            allowed_launch_hosts=REAL_ALLOWED_HOSTS,
        )
    )
    missing_key.state.redis_connection = cast(Redis, HealthyRedis())

    weak_key = main.create_app(
        Settings(
            gemini_api_key=SecretStr("test-only"),
            navigator_api_key=SecretStr("short"),
            allowed_launch_hosts=REAL_ALLOWED_HOSTS,
        )
    )
    weak_key.state.redis_connection = cast(Redis, HealthyRedis())

    incomplete_allowlist = main.create_app(
        Settings(
            gemini_api_key=SecretStr("test-only"),
            navigator_api_key=SecretStr("test-navigator-key"),
            allowed_launch_hosts="zalo.me",
        )
    )
    incomplete_allowlist.state.redis_connection = cast(Redis, HealthyRedis())

    missing_response = TestClient(missing_key).get("/health/ready")
    weak_response = TestClient(weak_key).get("/health/ready")
    allowlist_response = TestClient(incomplete_allowlist).get("/health/ready")

    assert missing_response.status_code == 503
    assert weak_response.status_code == 503
    assert missing_response.json()["detail"] == ("Khóa truy cập Navigator API chưa được cấu hình.")
    assert weak_response.json()["detail"] == missing_response.json()["detail"]
    assert allowlist_response.status_code == 503
    assert allowlist_response.json()["detail"] == (
        "Allowlist URL chưa bao phủ Service Registry đang hoạt động."
    )
