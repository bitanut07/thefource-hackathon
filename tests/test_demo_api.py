from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from config import Settings
from main import create_app

DEMO_REGISTRY = Path("data/demo/services.local.json")


def demo_settings(*, app_env: str = "local") -> Settings:
    return Settings(
        app_env=app_env,
        registry_data_path=DEMO_REGISTRY,
        allowed_launch_hosts="example.com",
        llm_provider="fake",
    )


def test_direct_demo_query_returns_registry_candidate() -> None:
    app = create_app(demo_settings())

    response = TestClient(app).post(
        "/demo/query",
        json={"text": "Tôi muốn đóng tiền điện ở TP.HCM."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"]
    assert payload["choices"][0]["name"] == "Thanh toán tiện ích Demo"
    assert payload["choices"][0]["launch_url"].startswith("https://example.com/")


def test_demo_query_rejects_out_of_scope_action() -> None:
    app = create_app(demo_settings())

    response = TestClient(app).post(
        "/demo/query",
        json={"text": "Đặt cho tôi vé máy bay sang Nhật."},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"] == []
    assert payload["handoff_to_human"] is False


def test_demo_routes_are_disabled_in_production() -> None:
    app = create_app(demo_settings(app_env=" Production "))

    response = TestClient(app).post("/demo/query", json={"text": "Tìm chỗ khám mắt."})

    assert response.status_code == 404


class HealthyRedis:
    def ping(self) -> bool:
        return True


class UnavailableRedis:
    def ping(self) -> bool:
        raise RedisConnectionError("offline")


def test_readiness_checks_redis() -> None:
    app = create_app(demo_settings())
    app.state.redis_connection = cast(Redis, HealthyRedis())

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_fails_when_redis_is_unavailable() -> None:
    app = create_app(demo_settings())
    app.state.redis_connection = cast(Redis, UnavailableRedis())

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Redis chưa sẵn sàng."
