from collections.abc import Mapping
from typing import Protocol

from config import Settings


class ZaloSignatureVerifier(Protocol):
    def verify(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        # TODO: Xác minh chữ ký theo contract Zalo OA hiện hành.
        raise NotImplementedError("Chưa triển khai contract xác minh chữ ký Zalo OA")


class ZaloMessagingClient(Protocol):
    async def send_text(self, user_id: str, text: str) -> None:
        # TODO: Gửi tin nhắn theo endpoint và schema Zalo OA đã xác minh.
        raise NotImplementedError("Chưa triển khai contract gửi tin nhắn Zalo OA")


class ConfiguredZaloClient:
    settings: Settings

    def __init__(self, settings: Settings) -> None:
        # TODO: Khởi tạo HTTP client và thông tin xác thực Zalo OA từ cấu hình.
        raise NotImplementedError("Chưa triển khai khởi tạo Zalo OA client")

    def verify(self, raw_body: bytes, headers: Mapping[str, str]) -> bool:
        # TODO: Xác minh chữ ký webhook theo contract Zalo OA đã được kiểm chứng.
        raise NotImplementedError("Chưa triển khai xác minh chữ ký webhook Zalo OA")

    async def send_text(self, user_id: str, text: str) -> None:
        # TODO: Gửi tin nhắn văn bản theo endpoint Zalo OA đã được kiểm chứng.
        raise NotImplementedError("Chưa triển khai gửi tin nhắn qua Zalo OA")
