import asyncio
import hashlib
import json

import httpx
from pydantic import SecretStr

from config import Settings
from zalo.client import ConfiguredZaloClient, ZaloListElement, ZaloTokens


class MemoryTokenStore:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, ZaloTokens]] = {}

    def load(self, key: str, seed_digest: str) -> ZaloTokens | None:
        value = self.values.get(key)
        if value is None or value[0] != seed_digest:
            return None
        return value[1]

    def save(self, key: str, seed_digest: str, tokens: ZaloTokens) -> None:
        self.values[key] = (seed_digest, tokens)


def test_zalo_signature_uses_exact_raw_body_and_secret() -> None:
    settings = Settings(zalo_webhook_secret=SecretStr("test-oa-secret"))
    body = json.dumps(
        {"app_id": "app-1", "timestamp": "123", "event_name": "user_send_text"},
        separators=(",", ":"),
    ).encode()
    signature = hashlib.sha256(b"app-1" + body + b"123" + b"test-oa-secret").hexdigest()

    assert ConfiguredZaloClient(settings).verify(body, {"x-zevent-signature": signature})
    assert ConfiguredZaloClient(settings).verify(body, {"x-zevent-signature": f"mac={signature}"})
    assert not ConfiguredZaloClient(settings).verify(body, {"x-zevent-signature": "bad"})


def test_zalo_client_refreshes_expired_token_then_retries_message() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v3.0/oa/message/cs":
            if request.headers["access_token"] == "expired-access":
                return httpx.Response(
                    200, json={"error": -216, "message": "Access token has expired"}
                )
            assert request.headers["access_token"] == "new-access"
            return httpx.Response(200, json={"error": 0, "data": {}})
        assert request.url == httpx.URL("https://oauth.zaloapp.com/v4/oa/access_token")
        assert request.headers["secret_key"] == "app-secret"
        assert request.content == (
            b"app_id=app-1&refresh_token=initial-refresh&grant_type=refresh_token"
        )
        return httpx.Response(
            200, json={"access_token": "new-access", "refresh_token": "new-refresh"}
        )

    settings = Settings(
        zalo_app_id="app-1",
        zalo_app_secret=SecretStr("app-secret"),
        zalo_access_token=SecretStr("expired-access"),
        zalo_refresh_token=SecretStr("initial-refresh"),
    )
    store = MemoryTokenStore()
    client = ConfiguredZaloClient(
        settings, transport=httpx.MockTransport(handler), token_store=store
    )

    asyncio.run(client.send_text("user-1", "Xin chao"))

    assert [request.url.path for request in requests] == [
        "/v3.0/oa/message/cs",
        "/v4/oa/access_token",
        "/v3.0/oa/message/cs",
    ]


def test_zalo_client_sends_legacy_list_template_with_at_most_five_elements() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"error": 0, "data": {"message_id": "message-1"}})

    settings = Settings(
        zalo_access_token=SecretStr("access-token"),
        zalo_refresh_token=SecretStr("refresh-token"),
    )
    client = ConfiguredZaloClient(
        settings,
        transport=httpx.MockTransport(handler),
        token_store=MemoryTokenStore(),
    )
    elements = [
        ZaloListElement(
            title=f"Dịch vụ {index}",
            subtitle="Phù hợp với nhu cầu",
            url=f"https://zalo.me/{index:010d}",
            image_url="https://example.com/service.png",
        )
        for index in range(1, 7)
    ]

    asyncio.run(client.send_list("user-1", "Mình tìm thấy các lựa chọn.", elements))

    assert len(requests) == 1
    assert requests[0].url.path == "/v2.0/oa/message"
    body = json.loads(requests[0].content)
    assert body["recipient"] == {"user_id": "user-1"}
    assert body["message"]["text"] == "Mình tìm thấy các lựa chọn."
    payload = body["message"]["attachment"]["payload"]
    assert payload["template_type"] == "list"
    assert len(payload["elements"]) == 5
    assert payload["elements"][0] == {
        "title": "Dịch vụ 1",
        "subtitle": "Phù hợp với nhu cầu",
        "image_url": "https://example.com/service.png",
        "default_action": {
            "type": "oa.open.url",
            "url": "https://zalo.me/0000000001",
        },
    }
