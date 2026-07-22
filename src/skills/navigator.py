from typing import Protocol

from domain.search import SearchService
from llm.schemas import AgentResponse, ServiceCandidate, StructuredQuery


class IntentExtractor(Protocol):
    async def extract_structured_query(self, text: str) -> StructuredQuery:
        # TODO: Trích xuất truy vấn có cấu trúc bằng LLM client đã cấu hình.
        raise NotImplementedError("Chưa triển khai contract trích xuất ý định")


class ResponseComposer(Protocol):
    async def compose(
        self,
        query: StructuredQuery,
        candidates: list[ServiceCandidate],
    ) -> AgentResponse:
        # TODO: Soạn phản hồi chỉ từ candidate đã được backend phê duyệt.
        raise NotImplementedError("Chưa triển khai contract soạn phản hồi")


class NavigatorSkill:
    intent_extractor: IntentExtractor
    search_service: SearchService
    response_composer: ResponseComposer

    def __init__(
        self,
        intent_extractor: IntentExtractor,
        search_service: SearchService,
        response_composer: ResponseComposer,
    ) -> None:
        # TODO: Gắn các contract trích xuất, tìm kiếm và soạn phản hồi.
        raise NotImplementedError("Chưa triển khai khởi tạo kỹ năng điều hướng")

    async def process_text(self, text: str) -> AgentResponse:
        # TODO: Điều phối trích xuất, tìm candidate và soạn phản hồi an toàn.
        raise NotImplementedError("Chưa triển khai xử lý truy vấn văn bản")
