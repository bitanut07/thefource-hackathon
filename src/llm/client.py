from typing import Protocol

from config import Settings
from llm.schemas import StructuredQuery


class LLMClient(Protocol):
    async def extract_structured_query(self, text: str) -> StructuredQuery:
        # TODO: Gọi provider LLM với structured output và timeout phù hợp.
        raise NotImplementedError("Chưa triển khai contract trích xuất truy vấn")


class ConfiguredLLMClient:
    settings: Settings

    def __init__(self, settings: Settings) -> None:
        # TODO: Khởi tạo provider, model, timeout và thông tin xác thực LLM.
        raise NotImplementedError("Chưa triển khai khởi tạo LLM client")

    async def extract_structured_query(self, text: str) -> StructuredQuery:
        # TODO: Gọi LLM và kiểm tra kết quả theo schema truy vấn có cấu trúc.
        raise NotImplementedError("Chưa triển khai trích xuất truy vấn bằng LLM")
