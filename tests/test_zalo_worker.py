import asyncio

from worker.jobs import _send_navigation_response
from zalo.client import ZaloAPIError, ZaloListElement


class FakeZaloClient:
    def __init__(self, *, reject_list: bool = False) -> None:
        self.reject_list = reject_list
        self.list_calls: list[tuple[str, str, list[ZaloListElement]]] = []
        self.text_calls: list[tuple[str, str]] = []

    async def send_list(
        self,
        user_id: str,
        text: str,
        elements: list[ZaloListElement],
    ) -> None:
        self.list_calls.append((user_id, text, elements))
        if self.reject_list:
            raise ZaloAPIError("unsupported")

    async def send_text(self, user_id: str, text: str) -> None:
        self.text_calls.append((user_id, text))


CHOICES: list[dict[str, object]] = [
    {
        "name": "KFC Vietnam",
        "reason": "khớp dịch vụ KFC",
        "launch_url": "https://zalo.me/1089872550377351285",
        "avatar_url": "https://photo.zalo.me/kfc.png",
    },
    {
        "name": "Highlands Coffee",
        "reason": "phù hợp nhu cầu ăn uống",
        "launch_url": "https://zalo.me/1498942390064218601",
    },
]


def test_worker_sends_text_and_choices_as_one_list_template_message() -> None:
    client = FakeZaloClient()

    delivery = asyncio.run(
        _send_navigation_response(
            client,
            "user-1",
            "Mình tìm thấy 2 lựa chọn.",
            CHOICES,
            list_template_enabled=True,
            list_image_url="https://example.com/service.png",
        )
    )

    assert delivery == "list"
    assert client.text_calls == []
    assert len(client.list_calls) == 1
    _, text, elements = client.list_calls[0]
    assert text == "Mình tìm thấy 2 lựa chọn."
    assert [element.title for element in elements] == ["KFC Vietnam", "Highlands Coffee"]
    assert [element.image_url for element in elements] == [
        "https://photo.zalo.me/kfc.png",
        "https://example.com/service.png",
    ]


def test_worker_falls_back_to_plaintext_when_legacy_list_is_rejected() -> None:
    client = FakeZaloClient(reject_list=True)

    delivery = asyncio.run(
        _send_navigation_response(
            client,
            "user-1",
            "Mình tìm thấy 2 lựa chọn.",
            CHOICES,
            list_template_enabled=True,
        )
    )

    assert delivery == "text"
    assert len(client.list_calls) == 1
    assert client.text_calls == [
        (
            "user-1",
            "Mình tìm thấy 2 lựa chọn.\n"
            "Gợi ý phù hợp:\n"
            "1. KFC Vietnam\nhttps://zalo.me/1089872550377351285\n"
            "2. Highlands Coffee\nhttps://zalo.me/1498942390064218601",
        )
    ]
