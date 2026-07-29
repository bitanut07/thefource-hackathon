from fastapi.testclient import TestClient
from pydantic import SecretStr

import main
from api.chatbot import _category_for_text, _structured_query
from config import Settings


def _client() -> TestClient:
    app = main.create_app(
        Settings(
            search_backend="json",
            allowed_launch_hosts="zalo.me",
            zalo_chatbot_token=SecretStr("test-chatbot-token"),
            public_base_url="https://navigator.example.com",
        )
    )
    return TestClient(app)


def test_dynamic_query_infers_broad_service_categories_without_an_llm() -> None:
    assert _category_for_text("Tìm chỗ ăn uống gần đây") == "food"
    assert _category_for_text("Dịch vụ giáo dục cho học sinh") == "education"
    assert _category_for_text("KFC") is None
    assert _structured_query("Tìm chỗ ăn uống gần đây").model_dump() == {
        "intent": "find_food_service",
        "category": "food",
        "service": None,
        "location": None,
        "time": None,
        "target_user": None,
        "organization": None,
        "needs_clarification": False,
        "clarification_field": None,
        "out_of_scope": False,
    }
    assert _structured_query("Nhà thuốc Long Châu").service == "Nhà thuốc Long Châu"


def test_dynamic_api_returns_a_clickable_list_for_a_query() -> None:
    response = _client().get(
        "/integrations/zalo/chatbot/dynamic",
        params={"q": "Edupia"},
        headers={"X-Chatbot-Token": "test-chatbot-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "chatbot"
    messages = payload["content"]["messages"]
    assert messages[0]["type"] == "text"
    assert messages[1]["type"] == "list"
    assert messages[1]["elements"][0]["image_url"] == (
        "https://navigator.example.com/integrations/zalo/chatbot/assets/"
        "service-directory.png"
    )
    assert messages[1]["elements"][0]["action"]["type"] == "url"
    assert messages[1]["elements"][0]["action"]["url"].startswith("https://zalo.me/")
    assert response.headers["cache-control"] == "no-store"


def test_generic_thumbnail_is_served_as_cacheable_png() -> None:
    response = _client().get(
        "/integrations/zalo/chatbot/assets/service-directory.png"
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "public, max-age=86400"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


def test_dynamic_api_accepts_alias_and_never_fails_for_missing_text() -> None:
    client = _client()
    headers = {"X-Chatbot-Token": "test-chatbot-token"}

    alias = client.get(
        "/integrations/zalo/chatbot/dynamic",
        params={"text": "Edupia"},
        headers=headers,
    )
    missing = client.get("/integrations/zalo/chatbot/dynamic", headers=headers)

    assert alias.status_code == 200
    assert alias.json()["version"] == "chatbot"
    assert missing.status_code == 200
    assert missing.json()["content"]["messages"][0]["type"] == "text"


def test_dynamic_api_requires_its_own_header_secret() -> None:
    response = _client().get("/integrations/zalo/chatbot/dynamic", params={"q": "Edupia"})

    assert response.status_code == 401
    assert response.json() == {"code": "UNAUTHORIZED"}
